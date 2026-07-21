"""
simulate.py
===========

Governed driver for the OSSF groundwater screening tool.

Pipeline (OSSF-GW-002 / OSSF-GW-003 / OSSF-GW-004):

    1. Load raw site JSON + databases.
    2. Detect the input schema. A ``schema_version`` of
       ``ossf-site-case-1.1.0`` is parsed and validated into an immutable
       ``SiteCaseV1``; an unversioned config is routed through the explicit
       legacy converter. ``ossf-site-case-1.0.0`` is rejected with an
       explicit migration message. Malformed / ambiguous / physically
       invalid input is rejected here with actionable, field-pathed errors
       and never reaches preflight, authorization, or physics.
    2b. Validate the evidence layer (completeness, contradiction, review
        gate). Critical failures write an evidence-failure artifact and
        exit 1 before readiness/preflight.
    2c. Assess practitioner readiness (OSSF-GW-004). ``not_ready`` writes a
        readiness-failure artifact and exits 1 before preflight.
    2d. Emit / append CaseHistory (OSSF-GW-005) for readiness not_ready,
        authorization denied, and authorized executions. Evidence-layer
        failures do not emit history.
    3. Run preflight (Site Appropriateness Determination). A ``refuse``
       disposition is a denied authorization: write a refusal artifact, exit 2.
    4. Mint a ``ScreeningAuthorization`` bound to the canonical ``SiteCaseV1``
       hash, ``evidence_digest``, and ``readiness_digest``.
    5. Dispatch the selected physics engine through the governed registry for
       every constituent at every active receptor.
    6. Emit an attested output (JSON + text report) stamping the input schema
       version, normalized site-config hash, evidence digest, readiness
       digest, database hashes, and authorization.

Exit codes (ADR-0004 / ``core.result_contract``):
    0  pass     — authorized; every gating criterion met
    1  error    — config not found / not JSON / invalid contract / evidence /
                  readiness failure / runtime error
    2  refused  — preflight refused; screening not authorizable
    3  fail     — authorized; one or more gating criteria not met

Usage:
    python simulate.py config/site_example.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.darcy import evaluate_flow, m_per_s_to_cm_per_hr
from core.attenuation import classify_permeability
from core.governance import (
    build_attestation,
    verify_seal_inputs,
    PREFLIGHT_RULESET_VERSION,
    sha256_of_file,
)
from core.preflight import evaluate_site as run_preflight
from core.physics_registry import get_engine, run_authorized_engine
from core.authorization import (
    AUTHORIZATION_SCHEMA_VERSION,
    AuthorizationDeniedError,
    authorize_screening,
    authorization_to_dict,
    findings_digest,
    normalize_findings,
)
from core.result_contract import (
    RESULT_SCHEMA_VERSION,
    EXIT_ERROR,
    embed_evidence_block,
    embed_history_block,
    embed_readiness_block,
    exit_code_for,
    history_result_summary_dict,
    resolve_status,
)
from core.history import (
    AuthorizationDenial,
    CreatedReason,
    ExecutionOutcome,
    ExecutionStatus,
    HistoryValidationError,
    build_history,
    compute_result_digest,
    load_and_validate_history,
    write_history,
)
from core.contracts import (
    SCHEMA_VERSION,
    ConstituentRole,
    ContractError,
    ContractValidationError,
    EvidenceValidationError,
    SiteCaseV1,
    UnsupportedSchemaVersionError,
    active_receptors,
    convert_legacy_site_config_to_v1,
    detect_schema_version,
    effective_source_concentration,
    evidence_failure_artifact,
    evidence_result_summary_dict,
    parse_site_case_dict,
    site_case_hash,
    validate_evidence_layer,
)
from core.readiness import (
    assess_readiness,
    readiness_failure_artifact,
    readiness_result_summary_dict,
)


HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DEFAULT_OUTPUT_DIR = HERE / "output"


def _repo_relative(path: Path) -> str:
    """Normalized relative path from the repository root (forward slashes)."""
    try:
        return path.resolve().relative_to(HERE.resolve()).as_posix()
    except ValueError:
        return path.name


def _file_digest(path: Path) -> str:
    return sha256_of_file(path)


def _infer_created_reason(*, prior, site_digest: str, disposition: str | None,
                          denied: bool) -> CreatedReason:
    if prior is None:
        return CreatedReason.INITIAL_RUN
    last = prior.revisions[-1]
    if site_digest != last.site_digest:
        return CreatedReason.CASE_UPDATE
    if disposition == "not_ready":
        return CreatedReason.READINESS_REASSESSMENT
    if denied:
        return CreatedReason.AUTHORIZATION_REASSESSMENT
    return CreatedReason.RERUN


def _emit_history(
    *,
    case,
    prior_history,
    evidence_result,
    readiness_result,
    history_path: Path,
    authorization_result=None,
    authorization_denial=None,
    execution_result=None,
    generated_artifacts=(),
    created_reason: CreatedReason,
):
    """Build and atomically write the case-history artifact."""
    history = build_history(
        case=case,
        prior_history=prior_history,
        evidence_summary=evidence_result,
        readiness_result=readiness_result,
        authorization_result=authorization_result,
        authorization_denial=authorization_denial,
        execution_result=execution_result,
        generated_artifacts=generated_artifacts,
        created_reason=created_reason,
    )
    write_history(history, history_path)
    return history


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_databases() -> tuple[dict, dict, Path, Path]:
    soil_path = DATA_DIR / "soil_database.json"
    path_path = DATA_DIR / "pathogens.json"
    soils = load_json(soil_path)["soils"]
    pathogens = load_json(path_path)["constituents"]
    return soils, pathogens, soil_path, path_path


def load_site_case(raw: dict, soils: dict, pathogens: dict) -> SiteCaseV1:
    """Turn raw input into a validated ``SiteCaseV1``.

    A declared schema version is parsed/validated directly. An unversioned
    config takes the explicit, bounded legacy-conversion path. Either way the
    result is a fully validated, immutable contract."""
    version = detect_schema_version(raw)
    if version is None:
        return convert_legacy_site_config_to_v1(
            raw, soil_database=soils, constituent_database=pathogens
        )
    return parse_site_case_dict(
        raw, soil_database=soils, constituent_database=pathogens
    )


def _project_block(case: SiteCaseV1) -> dict:
    """Report-facing project block (keeps the historical key names)."""
    return {
        "name": case.project.name,
        "site_id": case.site_id,
        "engineer": case.project.engineer,
        "tceq_authority": case.project.regulatory_authority,
    }


# ---------------------------------------------------------------------------
# Refusal artifact
# ---------------------------------------------------------------------------

def _all_gating_criteria_met(physics_result: dict) -> bool:
    """True iff every gating constituent passes. ``passes_screening is None``
    means reference-only (non-gating) and does not force fail (ADR-0004)."""
    for receptor in physics_result.get("receptors", []):
        for c in receptor.get("constituents", []):
            passes = c.get("passes_screening")
            if passes is None:
                continue
            if passes is False:
                return False
    return True


def build_refusal_artifact(
    case: SiteCaseV1,
    sad,
    denial: Exception | None = None,
    evidence_result=None,
    readiness_result=None,
) -> dict:
    normalized = normalize_findings(sad.findings)
    artifact = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": resolve_status(authorized=False, all_criteria_met=None),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disposition": "refuse",
        "input_schema_version": case.schema_version,
        "project": _project_block(case),
        # Provenance for a refused site. This carries enough to reproduce and
        # audit the refusal, but deliberately NO engine result and NO
        # methodology attestation: a refusal is not an attested physics
        # result. ``authorized`` is false and ``authorization_id`` is null
        # because a refused site is not authorizable (no token is minted).
        "authorization": {
            "authorized": False,
            "authorization_id": None,
            "schema_version": AUTHORIZATION_SCHEMA_VERSION,
            "ruleset_version": PREFLIGHT_RULESET_VERSION,
            "preflight_disposition": sad.disposition,
            "site_config_hash": site_case_hash(case),
            "findings_digest": findings_digest(normalized),
            "evidence_digest": (
                getattr(evidence_result, "evidence_digest", None)
                if evidence_result is not None else None
            ),
            "readiness_digest": (
                getattr(readiness_result, "readiness_digest", None)
                if readiness_result is not None else None
            ),
            "warning_count": len(sad.warnings()),
            "refusal_count": len(sad.refusal_reasons()),
            "reason": (
                str(denial) if denial is not None
                else "Preflight refused the site; screening is not authorizable."
            ),
        },
        "findings_all": [
            {
                "rule_id": f.rule_id,
                "disposition": f.disposition,
                "message": f.message,
                "authority": f.authority,
            }
            for f in normalized
        ],
        "refusal_reasons": [
            {
                "rule_id": f.rule_id,
                "message": f.message,
                "authority": f.authority,
            }
            for f in sad.refusal_reasons()
        ],
        "warnings": [
            {
                "rule_id": f.rule_id,
                "message": f.message,
                "authority": f.authority,
            }
            for f in sad.warnings()
        ],
        "notice": (
            "This site was refused by the preflight Site Appropriateness "
            "Determination. The screening physics engine did not run. "
            "This screening tool is not appropriate for this site; the "
            "engineer of record should escalate to a numerical model "
            "(HYDRUS-1D, MODFLOW+MT3DMS) or apply the WPAP process as "
            "cited in the refusal reasons above."
        ),
    }
    if evidence_result is not None:
        embed_evidence_block(artifact, evidence_result_summary_dict(evidence_result))
    if readiness_result is not None:
        embed_readiness_block(
            artifact, readiness_result_summary_dict(readiness_result)
        )
    return artifact


# ---------------------------------------------------------------------------
# Physics dispatch
# ---------------------------------------------------------------------------

def run_physics(case: SiteCaseV1, soils: dict, pathogens: dict, authorization) -> dict:
    """Run the selected physics engine against every constituent at every
    receptor, using validated, typed site-case values. Returns the results
    dict for embedding in the attested output.

    Every engine invocation flows through ``run_authorized_engine``, which
    revalidates the authorization against the validated case before dispatch.
    The engine is never called directly here."""
    engine_name = case.physics.engine
    dispersivity_method = case.physics.dispersivity_method.value
    # Metadata inspection only (name/version/scope for the report headline).
    engine = get_engine(engine_name)

    soil = soils[case.subsurface.soil_id]
    gradient = case.groundwater.hydraulic_gradient

    # Darcy flow (kept explicit for the report headline)
    flow = evaluate_flow(
        K_sat=soil["K_sat_m_per_s"],
        gradient=gradient,
        effective_porosity=soil["effective_porosity"],
    )

    receptor_results = []
    for receptor in active_receptors(case):
        constituent_results = []
        for sel in case.constituents:
            cprops = pathogens[sel.constituent_id]
            C0 = effective_source_concentration(sel, cprops)
            run = run_authorized_engine(
                engine_name,
                case,
                authorization,
                dict(
                    C0=C0,
                    lam_per_day=cprops["lambda_per_day"],
                    Kd_L_per_kg=cprops["Kd_L_per_kg"],
                    bulk_density_kg_m3=soil["bulk_density_kg_per_m3"],
                    effective_porosity=soil["effective_porosity"],
                    K_sat_m_per_s=soil["K_sat_m_per_s"],
                    hydraulic_gradient=gradient,
                    distance_m=receptor.distance_m,
                    dispersivity_method=dispersivity_method,
                ),
            )
            r = run.result
            # Reporting role: reference-only constituents (e.g. nitrate under
            # advective-reference reporting) never gate the outcome.
            is_reference = sel.role == ConstituentRole.REFERENCE_ONLY
            report_as = "advective_reference_only" if is_reference else "pass_fail"
            passes = (
                None if is_reference
                else r.C_receptor_steady_state <= cprops["regulatory_limit"]
            )
            constituent_results.append({
                "constituent": sel.constituent_id,
                "C0": C0,
                "C0_units": cprops["C0_units"],
                "regulatory_limit": cprops["regulatory_limit"],
                "C_receptor_steady_state": r.C_receptor_steady_state,
                "retardation_factor": r.retardation_factor,
                "dispersivity_m": r.dispersivity_m,
                "seepage_velocity_m_per_day": r.seepage_velocity_m_per_day,
                "reporting_mode": report_as,
                "passes_screening": passes,
                "reporting_note": (
                    "Advective transport only; nitrogen mass balance "
                    "(area loading, plant uptake, denitrification) is "
                    "addressed separately per Ch. 285.33 and is NOT "
                    "represented by this number."
                    if sel.constituent_id == "nitrate_as_N" else None
                ),
            })
        receptor_results.append({
            "name": receptor.display_name,
            "type": receptor.receptor_type.value,
            "distance_m": receptor.distance_m,
            "constituents": constituent_results,
        })

    # Comparison scenarios (illustrative "contrast" clause). Governed V1 field.
    comparisons = []
    nearest = min(active_receptors(case), key=lambda r: r.distance_m)
    for alt_key in case.reporting.comparison_soil_ids:
        alt = soils[alt_key]
        alt_flow = evaluate_flow(
            K_sat=alt["K_sat_m_per_s"],
            gradient=gradient,
            effective_porosity=alt["effective_porosity"],
        )
        comparisons.append({
            "soil_type": alt_key,
            "K_sat_m_per_s": alt["K_sat_m_per_s"],
            "K_sat_cm_per_hr": m_per_s_to_cm_per_hr(alt["K_sat_m_per_s"]),
            "permeability_class": classify_permeability(alt["K_sat_m_per_s"]),
            "seepage_velocity_ft_per_day": alt_flow.seepage_velocity_ft_per_day,
            "advective_travel_time_to_nearest_receptor_days":
                alt_flow.travel_time_days(nearest.distance_m),
        })

    return {
        "engine": engine.name,
        "engine_version": engine.version,
        "engine_scope_notes": engine.scope_notes,
        "flow": {
            "darcy_flux_m_per_s": flow.darcy_flux_m_per_s,
            "seepage_velocity_m_per_day": flow.seepage_velocity_m_per_day,
            "seepage_velocity_ft_per_day": flow.seepage_velocity_ft_per_day,
        },
        "subsurface": {
            "soil_type": case.subsurface.soil_id,
            "soil_thickness_m": case.subsurface.soil_thickness_m,
            "depth_to_water_table_m": case.groundwater.depth_to_groundwater_m,
            "hydraulic_gradient": gradient,
            "soil_properties": soil,
            "K_sat_cm_per_hr": m_per_s_to_cm_per_hr(soil["K_sat_m_per_s"]),
            "permeability_class": classify_permeability(soil["K_sat_m_per_s"]),
        },
        "receptors": receptor_results,
        "comparison_scenarios": comparisons,
    }


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------

def render_refusal_text(artifact: dict) -> str:
    L = []
    L.append("=" * 78)
    L.append("SCREENING TOOL - SITE REFUSED (preflight)")
    L.append("=" * 78)
    P = artifact.get("project", {})
    L.append(f"Project   : {P.get('name', '-')}  (ID: {P.get('site_id','-')})")
    L.append(f"Generated : {artifact['generated_utc']}")
    L.append("")
    auth = artifact.get("authorization", {})
    L.append("AUTHORIZATION: DENIED")
    L.append("-" * 78)
    L.append(f"  schema_version   : {auth.get('schema_version', '-')}")
    L.append(f"  ruleset_version  : {auth.get('ruleset_version', '-')}")
    L.append(f"  preflight        : {auth.get('preflight_disposition', '-')}")
    L.append(f"  site_config_hash : {auth.get('site_config_hash', '-')}")
    L.append(f"  findings_digest  : {auth.get('findings_digest', '-')}")
    L.append(f"  refusal_count    : {auth.get('refusal_count', '-')}")
    L.append(f"  reason           : {auth.get('reason', '-')}")
    L.append("")
    L.append("REFUSAL REASONS")
    L.append("-" * 78)
    for r in artifact["refusal_reasons"]:
        L.append(f"  [{r['rule_id']}] {r['message']}")
        L.append(f"    Authority: {r['authority']}")
        L.append("")
    if artifact["warnings"]:
        L.append("WARNINGS (would have been issued if proceeding)")
        L.append("-" * 78)
        for w in artifact["warnings"]:
            L.append(f"  [{w['rule_id']}] {w['message']}")
            L.append("")
    L.append("-" * 78)
    L.append(artifact["notice"])
    L.append("=" * 78)
    return "\n".join(L)


def render_report_text(artifact: dict) -> str:
    L = []
    P = artifact["project"]
    L.append("=" * 78)
    L.append("GROUNDWATER IMPACT EVALUATION - SCREENING REPORT")
    L.append("=" * 78)
    L.append(f"Project        : {P['name']}  (ID: {P.get('site_id','-')})")
    L.append(f"Engineer       : {P['engineer']}")
    L.append(f"Authority      : {P['tceq_authority']}")
    L.append(f"Generated (UTC): {artifact['attestation']['generated_utc']}")
    L.append("")
    L.append("ATTESTATION")
    L.append("-" * 78)
    for k, v in artifact["attestation"].items():
        L.append(f"  {k:<28}: {v}")
    L.append("")
    auth = artifact.get("authorization", {})
    L.append("AUTHORIZATION")
    L.append("-" * 78)
    L.append(f"  {'authorization_id':<28}: {auth.get('authorization_id', '-')}")
    L.append(f"  {'schema_version':<28}: {auth.get('schema_version', '-')}")
    L.append(f"  {'disposition':<28}: {auth.get('disposition', '-')}")
    L.append(f"  {'findings_digest':<28}: {auth.get('findings_digest', '-')}")
    L.append(f"  {'granted_utc':<28}: {auth.get('granted_utc', '-')}")
    L.append("")
    if artifact["preflight"]["warnings"]:
        L.append("PREFLIGHT WARNINGS")
        L.append("-" * 78)
        for w in artifact["preflight"]["warnings"]:
            L.append(f"  [{w['rule_id']}] {w['message']}")
            L.append(f"    Authority: {w['authority']}")
        L.append("")
    L.append("SUBSURFACE / FLOW")
    L.append("-" * 78)
    sub = artifact["physics"]["subsurface"]
    f = artifact["physics"]["flow"]
    L.append(f"  Soil type          : {sub['soil_type']} "
             f"({sub['permeability_class']})")
    L.append(f"  K_sat              : "
             f"{sub['soil_properties']['K_sat_m_per_s']:.2e} m/s "
             f"({sub['K_sat_cm_per_hr']:.3f} cm/hr)")
    L.append(f"  Effective porosity : {sub['soil_properties']['effective_porosity']:.3f}")
    L.append(f"  Gradient           : {sub['hydraulic_gradient']:.4f}")
    L.append(f"  Water table depth  : {sub.get('depth_to_water_table_m', '-')} m")
    L.append(f"  Seepage velocity   : {f['seepage_velocity_m_per_day']*1000:.4f} mm/day"
             f"  ({f['seepage_velocity_ft_per_day']:.5f} ft/day)")
    L.append("")
    L.append(f"PHYSICS ENGINE: {artifact['physics']['engine']} "
             f"v{artifact['physics']['engine_version']}")
    L.append("-" * 78)
    L.append(f"  Scope: {artifact['physics']['engine_scope_notes']}")
    L.append("")
    L.append("RECEPTOR EVALUATION")
    L.append("-" * 78)
    for r in artifact["physics"]["receptors"]:
        L.append(f"\n  Receptor: {r['name']}  [{r['type']}]")
        L.append(f"    distance : {r['distance_m']:.2f} m "
                 f"({r['distance_m']/0.3048:.1f} ft)")
        L.append(f"    {'constituent':<20}{'C0':>14}"
                 f"{'C_receptor_ss':>18}{'limit':>14}  result")
        for c in r["constituents"]:
            cval = f"{c['C_receptor_steady_state']:.3e}"
            if c["reporting_mode"] == "advective_reference_only":
                result = "REF-ONLY"
            else:
                result = "PASS" if c["passes_screening"] else "FAIL"
            L.append(f"    {c['constituent']:<20}"
                     f"{c['C0']:>14.3g}"
                     f"{cval:>18}"
                     f"{c['regulatory_limit']:>14.3g}"
                     f"  {result}")
        for c in r["constituents"]:
            if c.get("reporting_note"):
                L.append(f"    note ({c['constituent']}): {c['reporting_note']}")
                break
    L.append("")
    if artifact["physics"]["comparison_scenarios"]:
        L.append("COMPARISON SCENARIOS (higher-permeability soils)")
        L.append("-" * 78)
        L.append(f"  {'soil':<14}{'K_sat (m/s)':>14}"
                 f"{'class':>20}{'v (ft/day)':>14}{'t to nearest (d)':>20}")
        for c in artifact["physics"]["comparison_scenarios"]:
            L.append(f"  {c['soil_type']:<14}"
                     f"{c['K_sat_m_per_s']:>14.2e}"
                     f"{c['permeability_class']:>20}"
                     f"{c['seepage_velocity_ft_per_day']:>14.4f}"
                     f"{c['advective_travel_time_to_nearest_receptor_days']:>20.2f}")
        L.append("")
    L.append("=" * 78)
    L.append(
        "This report was produced by a governed screening tool. See the "
        "attestation block for provenance and version stamps. Screening "
        "results are not a substitute for site-specific numerical modeling "
        "when required by the preflight scope-of-applicability rules."
    )
    L.append("=" * 78)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _print_contract_errors(exc: ContractValidationError) -> None:
    print("ERROR: site case failed validation:", file=sys.stderr)
    for e in exc.errors:
        print(f"  - {e.path}: {e.message} [{e.code}]", file=sys.stderr)


def _print_evidence_errors(exc: EvidenceValidationError) -> None:
    print("ERROR: evidence layer validation failed:", file=sys.stderr)
    for e in exc.errors:
        print(f"  - {e.path}: {e.message} [{e.code}]", file=sys.stderr)


def _print_readiness_blocks(assessment) -> None:
    print("ERROR: practitioner readiness is not_ready:", file=sys.stderr)
    for f in assessment.blocks():
        path = f" ({f.path})" if f.path else ""
        print(
            f"  - [{f.finding_id}] {f.message} [{f.code}]{path}",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the governed OSSF groundwater screening tool."
    )
    parser.add_argument("config", type=Path,
                        help="Path to site configuration JSON")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output JSON path")
    parser.add_argument("--text", type=Path, default=None,
                        help="Output text report path")
    parser.add_argument(
        "--prior-history", type=Path, default=None,
        help="Optional prior CaseHistory JSON to append (OSSF-GW-005)",
    )
    args = parser.parse_args(argv)

    try:
        raw = load_json(args.config)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        return EXIT_ERROR
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: Config file is not valid JSON ({args.config}): "
            f"{exc.msg} at line {exc.lineno}, column {exc.colno}.",
            file=sys.stderr,
        )
        return EXIT_ERROR
    except OSError as exc:
        print(f"ERROR: Could not read config file {args.config}: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if not isinstance(raw, dict):
        print(
            f"ERROR: Config root must be a JSON object; got "
            f"{type(raw).__name__}.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    soils, pathogens, soil_path, path_path = load_databases()

    # --- Parse + validate the versioned input contract (before evidence/preflight) ---
    try:
        case = load_site_case(raw, soils, pathogens)
    except UnsupportedSchemaVersionError as exc:
        print(f"ERROR: unsupported input schema: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except ContractValidationError as exc:
        _print_contract_errors(exc)
        return EXIT_ERROR
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    site_id = case.site_id
    DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)
    out_json = args.output or (DEFAULT_OUTPUT_DIR / f"{site_id}_results.json")
    out_txt = args.text or (DEFAULT_OUTPUT_DIR / f"{site_id}_report.txt")
    history_path = DEFAULT_OUTPUT_DIR / f"{site_id}_history.json"
    history_rel = _repo_relative(history_path)

    prior_history = None
    if args.prior_history is not None:
        try:
            prior_history = load_and_validate_history(
                args.prior_history, expected_site_id=site_id
            )
        except HistoryValidationError as exc:
            print(f"ERROR: invalid --prior-history: {exc}", file=sys.stderr)
            return EXIT_ERROR

    # --- Evidence layer (OSSF-GW-003): before readiness/preflight ---
    try:
        evidence_result = validate_evidence_layer(case)
    except EvidenceValidationError as exc:
        _print_evidence_errors(exc)
        artifact = evidence_failure_artifact(
            case, exc,
            generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        with out_json.open("w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        notice = artifact.get("notice", "")
        print(notice)
        print(f"\n[wrote] {out_json}")
        # Evidence failures do not emit CaseHistory (GW-003 owns the artifact).
        return EXIT_ERROR

    # --- Practitioner readiness (OSSF-GW-004): before preflight ---
    readiness_result = assess_readiness(case, evidence_result)
    if not readiness_result.permits_authorization:
        _print_readiness_blocks(readiness_result)
        fail_json = (
            args.output
            if args.output is not None
            else (DEFAULT_OUTPUT_DIR / f"{site_id}_readiness_failure.json")
        )
        fail_txt = (
            args.text
            if args.text is not None
            else (DEFAULT_OUTPUT_DIR / f"{site_id}_readiness_failure.txt")
        )
        artifact = readiness_failure_artifact(
            case,
            readiness_result,
            generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        text = (
            "SCREENING TOOL - PRACTITIONER READINESS FAILURE\n"
            f"{artifact['notice']}\n"
            f"disposition: {readiness_result.disposition}\n"
            f"readiness_digest: {readiness_result.readiness_digest}\n"
        )
        for f in readiness_result.findings:
            text += f"  [{f.finding_id}/{f.severity}] {f.message}\n"
        with fail_json.open("w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        with fail_txt.open("w", encoding="utf-8") as f:
            f.write(text)
        bindings = [
            {
                "artifact_type": "readiness_failure_json",
                "relative_path": _repo_relative(fail_json),
                "sha256": _file_digest(fail_json),
            },
            {
                "artifact_type": "readiness_failure_text",
                "relative_path": _repo_relative(fail_txt),
                "sha256": _file_digest(fail_txt),
            },
        ]
        history = _emit_history(
            case=case,
            prior_history=prior_history,
            evidence_result=evidence_result,
            readiness_result=readiness_result,
            history_path=history_path,
            generated_artifacts=bindings,
            created_reason=_infer_created_reason(
                prior=prior_history,
                site_digest=site_case_hash(case),
                disposition=readiness_result.disposition,
                denied=False,
            ),
        )
        embed_history_block(
            artifact,
            history_result_summary_dict(history, history_artifact=history_rel),
        )
        with fail_json.open("w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        print(text)
        print(f"\n[wrote] {fail_json}")
        print(f"[wrote] {fail_txt}")
        print(f"[wrote] {history_path}")
        return EXIT_ERROR

    # --- Preflight ---
    sad = run_preflight(case)

    # --- Authorization (refusal is a denied authorization) ---
    try:
        authorization = authorize_screening(
            case, sad, evidence_result, readiness_result
        )
    except AuthorizationDeniedError as denial:
        artifact = build_refusal_artifact(
            case, sad, denial, evidence_result, readiness_result
        )
        text = render_refusal_text(artifact)
        with out_json.open("w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        with out_txt.open("w", encoding="utf-8") as f:
            f.write(text)
        bindings = [
            {
                "artifact_type": "result_json",
                "relative_path": _repo_relative(out_json),
                "sha256": _file_digest(out_json),
            },
            {
                "artifact_type": "report_text",
                "relative_path": _repo_relative(out_txt),
                "sha256": _file_digest(out_txt),
            },
        ]
        history = _emit_history(
            case=case,
            prior_history=prior_history,
            evidence_result=evidence_result,
            readiness_result=readiness_result,
            history_path=history_path,
            authorization_denial=AuthorizationDenial(
                findings=tuple(sad.findings),
                message=str(denial) or "Authorization denied",
            ),
            generated_artifacts=bindings,
            created_reason=_infer_created_reason(
                prior=prior_history,
                site_digest=site_case_hash(case),
                disposition=readiness_result.disposition,
                denied=True,
            ),
        )
        embed_history_block(
            artifact,
            history_result_summary_dict(history, history_artifact=history_rel),
        )
        with out_json.open("w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        print(text)
        print(f"\n[wrote] {out_json}")
        print(f"[wrote] {out_txt}")
        print(f"[wrote] {history_path}")
        return exit_code_for(artifact["status"])

    # --- Pre-physics seal-input check (avoid compute-then-fail) ---
    try:
        verify_seal_inputs(
            case, authorization, evidence_result, readiness_result
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # --- Physics (governed: every call revalidates the authorization) ---
    started_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        physics_result = run_physics(case, soils, pathogens, authorization)
        engine = get_engine(case.physics.engine)
        attestation = build_attestation(
            physics_engine=engine.name,
            physics_engine_version=engine.version,
            soil_db_path=soil_path,
            pathogens_db_path=path_path,
            site_case=case,
            authorization=authorization,
            warning_count=len(sad.warnings()),
            refusal_count=len(sad.refusal_reasons()),
            evidence_result=evidence_result,
            readiness_result=readiness_result,
        )
    except (ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    completed_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    status = resolve_status(
        authorized=True,
        all_criteria_met=_all_gating_criteria_met(physics_result),
    )
    artifact = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": status,
        "project": _project_block(case),
        "attestation": attestation.as_dict(),
        "authorization": authorization_to_dict(authorization),
        "preflight": {
            "disposition": sad.disposition,
            "warnings": [
                {"rule_id": f.rule_id, "message": f.message,
                 "authority": f.authority}
                for f in sad.warnings()
            ],
            "findings_all": [
                {"rule_id": f.rule_id, "disposition": f.disposition,
                 "message": f.message, "authority": f.authority}
                for f in sad.findings
            ],
        },
        "physics": physics_result,
    }
    embed_evidence_block(artifact, evidence_result_summary_dict(evidence_result))
    embed_readiness_block(artifact, readiness_result_summary_dict(readiness_result))

    # Digest the semantic result before history references are added.
    result_digest = compute_result_digest(artifact)

    # Render and write pre-history artifacts so bindings can hash file bytes.
    text = render_report_text(artifact)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)
    with out_txt.open("w", encoding="utf-8") as f:
        f.write(text)

    bindings = [
        {
            "artifact_type": "result_json",
            "relative_path": _repo_relative(out_json),
            "sha256": _file_digest(out_json),
        },
        {
            "artifact_type": "report_text",
            "relative_path": _repo_relative(out_txt),
            "sha256": _file_digest(out_txt),
        },
    ]
    exe_status = (
        ExecutionStatus.PASSED if status == "pass" else ExecutionStatus.FAILED
    )
    history = _emit_history(
        case=case,
        prior_history=prior_history,
        evidence_result=evidence_result,
        readiness_result=readiness_result,
        history_path=history_path,
        authorization_result=authorization,
        execution_result=ExecutionOutcome(
            status=exe_status,
            result_digest=result_digest,
            started_utc=started_utc,
            completed_utc=completed_utc,
        ),
        generated_artifacts=bindings,
        created_reason=_infer_created_reason(
            prior=prior_history,
            site_digest=site_case_hash(case),
            disposition=readiness_result.disposition,
            denied=False,
        ),
    )
    embed_history_block(
        artifact,
        history_result_summary_dict(history, history_artifact=history_rel),
    )
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    print(text)
    print(f"\n[wrote] {out_json}")
    print(f"[wrote] {out_txt}")
    print(f"[wrote] {history_path}")
    return exit_code_for(status)


if __name__ == "__main__":
    sys.exit(main())
