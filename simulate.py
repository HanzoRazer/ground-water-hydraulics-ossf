"""
simulate.py
===========

Governed driver for the OSSF groundwater screening tool.

Pipeline (OSSF-GW-002):

    1. Load raw site JSON + databases.
    2. Detect the input schema. A ``schema_version`` of
       ``ossf-site-case-1.0.0`` is parsed and validated into an immutable
       ``SiteCaseV1``; an unversioned config is routed through the explicit
       legacy converter. Malformed / ambiguous / physically invalid input is
       rejected here with actionable, field-pathed errors and never reaches
       preflight, authorization, or physics.
    3. Run preflight (Site Appropriateness Determination). A ``refuse``
       disposition is a denied authorization: write a refusal artifact, exit 2.
    4. Mint a ``ScreeningAuthorization`` bound to the canonical ``SiteCaseV1``
       hash.
    5. Dispatch the selected physics engine through the governed registry for
       every constituent at every active receptor.
    6. Emit an attested output (JSON + text report) stamping the input schema
       version, normalized site-config hash, database hashes, and authorization.

Exit codes:
    0  success (proceed or warn, authorized and evaluated)
    1  error (config not found / not JSON / invalid or unsupported contract /
       runtime error)
    2  refused (preflight refused; screening not authorizable)

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
from core.contracts import (
    SCHEMA_VERSION,
    ConstituentRole,
    ContractError,
    ContractValidationError,
    SiteCaseV1,
    UnsupportedSchemaVersionError,
    active_receptors,
    convert_legacy_site_config_to_v1,
    detect_schema_version,
    effective_source_concentration,
    parse_site_case_dict,
    site_case_hash,
)


HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DEFAULT_OUTPUT_DIR = HERE / "output"


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

def build_refusal_artifact(case: SiteCaseV1, sad, denial: Exception | None = None) -> dict:
    normalized = normalize_findings(sad.findings)
    return {
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
    args = parser.parse_args(argv)

    try:
        raw = load_json(args.config)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: Config file is not valid JSON ({args.config}): "
            f"{exc.msg} at line {exc.lineno}, column {exc.colno}.",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"ERROR: Could not read config file {args.config}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(raw, dict):
        print(
            f"ERROR: Config root must be a JSON object; got "
            f"{type(raw).__name__}.",
            file=sys.stderr,
        )
        return 1

    soils, pathogens, soil_path, path_path = load_databases()

    # --- Parse + validate the versioned input contract (before preflight) ---
    try:
        case = load_site_case(raw, soils, pathogens)
    except UnsupportedSchemaVersionError as exc:
        print(f"ERROR: unsupported input schema: {exc}", file=sys.stderr)
        return 1
    except ContractValidationError as exc:
        _print_contract_errors(exc)
        return 1
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    site_id = case.site_id
    DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)
    out_json = args.output or (DEFAULT_OUTPUT_DIR / f"{site_id}_results.json")
    out_txt = args.text or (DEFAULT_OUTPUT_DIR / f"{site_id}_report.txt")

    # --- Preflight ---
    sad = run_preflight(case)

    # --- Authorization (refusal is a denied authorization) ---
    try:
        authorization = authorize_screening(case, sad)
    except AuthorizationDeniedError as denial:
        artifact = build_refusal_artifact(case, sad, denial)
        text = render_refusal_text(artifact)
        with out_json.open("w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        with out_txt.open("w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        print(f"\n[wrote] {out_json}")
        print(f"[wrote] {out_txt}")
        return 2

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
        )
    except (ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    artifact = {
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
