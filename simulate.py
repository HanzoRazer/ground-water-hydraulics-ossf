"""
simulate.py
===========

Governed driver for the OSSF groundwater screening tool.

Pipeline (OSSF-GW-002 / OSSF-GW-003 / OSSF-GW-004 / OSSF-GW-005):

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
    3. Run preflight (Site Appropriateness Determination). A ``refuse``
       disposition is a denied authorization: write a refusal artifact, exit 2.
    4. Mint a ``ScreeningAuthorization`` bound to the canonical ``SiteCaseV1``
       hash, ``evidence_digest``, and ``readiness_digest``.
    5. Dispatch the selected physics engine through the governed registry for
       every constituent at every active receptor.
    6. Emit an attested output (JSON + text report) stamping the input schema
       version, normalized site-config hash, evidence digest, readiness
       digest, database hashes, and authorization.
    7. Emit a CaseHistory artifact (OSSF-GW-005) on authorization refusal and
       authorized pass/fail only — never on contract/evidence/readiness
       failures. Optional ``--prior-history`` appends explicitly.

Exit codes (ADR-0004 / ``core.result_contract``):
    0  pass     — authorized; every gating criterion met
    1  error    — config not found / not JSON / invalid contract / evidence /
                  readiness failure / runtime error
    2  refused  — preflight refused; screening not authorizable
    3  fail     — authorized; one or more gating criteria not met

Usage:
    python simulate.py config/site_example.json
    python simulate.py config/site_example.json --prior-history output/EX-001_history.json
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
    PREFLIGHT_RULESET_VERSION,
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
    embed_history_summary,
    embed_readiness_block,
    exit_code_for,
    resolve_status,
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
from core.history import (
    HistoryEventType,
    HistoryValidationError,
    append_to_history,
    build_case_history,
    build_execution,
    build_revision,
    decision_for_event,
    derive_revision_id,
    history_summary_dict,
    load_case_history_json,
    write_case_history_json,
)


HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DEFAULT_OUTPUT_DIR = HERE / "output"


def _rel_repo_path(path: Path) -> str:
    """Prefer a repo-relative path for artifact bindings in history."""
    try:
        return str(path.resolve().relative_to(HERE))
    except ValueError:
        return str(path)


def build_and_write_case_history(
    *,
    site_id: str,
    case_hash: str,
    evidence_digest: str,
    readiness_digest: str | None,
    authorization_id: str | None,
    decisions,
    result_status: str | None = None,
    engine_name: str | None = None,
    result_artifact: str | None = None,
    report_artifact: str | None = None,
    prior_history_path: Path | None = None,
    history_out: Path | None = None,
):
    """Build (or append) CaseHistory, write ``output/<site_id>_history.json``.

    Never auto-discovers prior history and never overwrites a prior file in
    place as mutation — always writes a new history artifact path.
    """
    out_path = history_out or (DEFAULT_OUTPUT_DIR / f"{site_id}_history.json")
    history_artifact_rel = _rel_repo_path(out_path)

    executions = []
    if result_status is not None:
        if not engine_name or not result_artifact:
            raise HistoryValidationError(
                "engine_name and result_artifact are required for an "
                "authorized execution history record."
            )

    if prior_history_path is None:
        revision = build_revision(
            revision_number=1,
            previous_revision_id=None,
            case_hash=case_hash,
            evidence_digest=evidence_digest,
            readiness_digest=readiness_digest,
            authorization_id=authorization_id,
        )
        if result_status is not None:
            executions.append(
                build_execution(
                    revision_id=revision.revision_id,
                    engine_name=engine_name,
                    result_status=result_status,
                    result_artifact=result_artifact,
                    report_artifact=report_artifact,
                )
            )
        history = build_case_history(
            revisions=[revision],
            decisions=decisions,
            executions=executions,
        )
    else:
        prior = load_case_history_json(prior_history_path)
        next_number = prior.latest_revision.revision_number + 1
        new_revision_id = derive_revision_id(
            revision_number=next_number,
            previous_revision_id=prior.latest_revision_id,
            case_hash=case_hash,
            evidence_digest=evidence_digest,
            readiness_digest=readiness_digest,
            authorization_id=authorization_id,
        )
        if result_status is not None:
            executions.append(
                build_execution(
                    revision_id=new_revision_id,
                    engine_name=engine_name,
                    result_status=result_status,
                    result_artifact=result_artifact,
                    report_artifact=report_artifact,
                )
            )
        history = append_to_history(
            prior,
            case_hash=case_hash,
            evidence_digest=evidence_digest,
            readiness_digest=readiness_digest,
            authorization_id=authorization_id,
            decisions=decisions,
            executions=executions,
        )

    write_case_history_json(history, out_path)
    summary = history_summary_dict(
        history, history_artifact=history_artifact_rel
    )
    return history, out_path, summary


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
        "--prior-history",
        type=Path,
        default=None,
        help=(
            "Optional prior CaseHistory JSON to validate and append "
            "(never auto-discovered; new history is written to "
            "output/<site_id>_history.json)."
        ),
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
        print(text)
        print(f"\n[wrote] {fail_json}")
        print(f"[wrote] {fail_txt}")
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
        try:
            _, hist_path, hist_summary = build_and_write_case_history(
                site_id=site_id,
                case_hash=site_case_hash(case),
                evidence_digest=evidence_result.evidence_digest,
                readiness_digest=readiness_result.readiness_digest,
                authorization_id=None,
                decisions=[
                    decision_for_event(
                        HistoryEventType.AUTHORIZATION_DENIED,
                        summary=str(denial),
                    )
                ],
                prior_history_path=args.prior_history,
                history_out=out_json.parent / f"{site_id}_history.json",
            )
        except (HistoryValidationError, OSError) as exc:
            print(f"ERROR: case history emission failed: {exc}", file=sys.stderr)
            return EXIT_ERROR
        embed_history_summary(artifact, hist_summary)
        text = render_refusal_text(artifact)
        with out_json.open("w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        with out_txt.open("w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        print(f"\n[wrote] {out_json}")
        print(f"[wrote] {out_txt}")
        print(f"[wrote] {hist_path}")
        return exit_code_for(artifact["status"])

    # --- Physics (governed: every call revalidates the authorization) ---
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

    try:
        _, hist_path, hist_summary = build_and_write_case_history(
            site_id=site_id,
            case_hash=site_case_hash(case),
            evidence_digest=evidence_result.evidence_digest,
            readiness_digest=readiness_result.readiness_digest,
            authorization_id=authorization.authorization_id,
            decisions=[
                decision_for_event(HistoryEventType.AUTHORIZATION_GRANTED),
                decision_for_event(HistoryEventType.SCREENING_EXECUTED),
            ],
            result_status=status,
            engine_name=physics_result["engine"],
            result_artifact=_rel_repo_path(out_json),
            report_artifact=_rel_repo_path(out_txt),
            prior_history_path=args.prior_history,
            history_out=out_json.parent / f"{site_id}_history.json",
        )
    except (HistoryValidationError, OSError) as exc:
        print(f"ERROR: case history emission failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    embed_history_summary(artifact, hist_summary)

    # Render before opening any file so a rendering failure cannot leave a
    # partial artifact on disk.
    text = render_report_text(artifact)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)
    with out_txt.open("w", encoding="utf-8") as f:
        f.write(text)

    print(text)
    print(f"\n[wrote] {out_json}")
    print(f"[wrote] {out_txt}")
    print(f"[wrote] {hist_path}")
    return exit_code_for(status)


if __name__ == "__main__":
    sys.exit(main())
