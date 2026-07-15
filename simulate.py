"""
simulate.py
===========

Main entry point. Reads a site configuration JSON, runs Darcy + transport
+ attenuation calculations against the soil and pathogen databases, and
writes a structured JSON result plus a human-readable text report.

Usage
-----
    python simulate.py config/site_example.json

Or, for a custom site:
    python simulate.py path/to/your_site.json --output output/your_site_results.json

The output JSON is structured to be both human-readable and machine-parseable
so it can be embedded into an engineering report or a downstream review
pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.darcy import evaluate_flow, m_per_s_to_cm_per_hr
from core.transport import evaluate_transport
from core.attenuation import (
    ReceptorEvaluation,
    narrative_attestation,
    classify_permeability,
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


def load_databases() -> tuple[dict, dict]:
    soils = load_json(DATA_DIR / "soil_database.json")["soils"]
    pathogens = load_json(DATA_DIR / "pathogens.json")["constituents"]
    return soils, pathogens


# ---------------------------------------------------------------------------
# Simulation core
# ---------------------------------------------------------------------------

def simulate_site(site_cfg: dict, soils: dict, pathogens: dict) -> dict:
    """Run a full evaluation for one site configuration."""
    soil_key = site_cfg["subsurface"]["soil_type"]
    if soil_key not in soils:
        raise KeyError(f"Unknown soil_type '{soil_key}'. Choices: {list(soils)}")
    soil = soils[soil_key]

    gradient = site_cfg["subsurface"]["hydraulic_gradient"]
    flow = evaluate_flow(
        K_sat=soil["K_sat_m_per_s"],
        gradient=gradient,
        effective_porosity=soil["effective_porosity"],
    )

    constituents = site_cfg["constituents_to_evaluate"]
    overrides = site_cfg["source"].get("C0_overrides", {})

    # Evaluate every receptor against every constituent
    receptor_evals: list[ReceptorEvaluation] = []
    for receptor in site_cfg["receptors"]:
        ev = ReceptorEvaluation(
            receptor_name=receptor["name"],
            receptor_type=receptor["type"],
            distance_m=receptor["distance_m"],
            flow=flow,
        )
        for cname in constituents:
            if cname not in pathogens:
                raise KeyError(f"Unknown constituent '{cname}'.")
            tr = evaluate_transport(
                constituent_name=cname,
                constituent_props=pathogens[cname],
                soil_props=soil,
                flow=flow,
                distance_m=receptor["distance_m"],
                C0_override=overrides.get(cname),
            )
            ev.transport_results.append(tr)
        receptor_evals.append(ev)

    # Comparison scenarios (alternate soils to demonstrate the contrast clause)
    comparisons = []
    for alt_soil_key in site_cfg.get("comparison_scenarios", {}).get("soils", []):
        if alt_soil_key not in soils:
            continue
        alt_soil = soils[alt_soil_key]
        alt_flow = evaluate_flow(
            K_sat=alt_soil["K_sat_m_per_s"],
            gradient=gradient,
            effective_porosity=alt_soil["effective_porosity"],
        )
        # Use nearest receptor for comparison
        nearest = min(site_cfg["receptors"], key=lambda r: r["distance_m"])
        comparisons.append({
            "soil_type": alt_soil_key,
            "K_sat_m_per_s": alt_soil["K_sat_m_per_s"],
            "K_sat_cm_per_hr": m_per_s_to_cm_per_hr(alt_soil["K_sat_m_per_s"]),
            "permeability_class": classify_permeability(alt_soil["K_sat_m_per_s"]),
            "seepage_velocity_m_per_day": alt_flow.seepage_velocity_m_per_day,
            "seepage_velocity_ft_per_day": alt_flow.seepage_velocity_ft_per_day,
            "advective_travel_time_to_nearest_receptor_days": alt_flow.travel_time_days(
                nearest["distance_m"]
            ),
        })

    attestation = narrative_attestation(
        soil_type=soil_key,
        K_sat_m_per_s=soil["K_sat_m_per_s"],
        flow=flow,
        receptor_evals=receptor_evals,
    )

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": site_cfg["project"],
        "subsurface": {
            **site_cfg["subsurface"],
            "soil_properties": soil,
            "K_sat_cm_per_hr": m_per_s_to_cm_per_hr(soil["K_sat_m_per_s"]),
            "permeability_class": classify_permeability(soil["K_sat_m_per_s"]),
        },
        "flow": {
            "darcy_flux_m_per_s": flow.darcy_flux_m_per_s,
            "seepage_velocity_m_per_s": flow.seepage_velocity_m_per_s,
            "seepage_velocity_m_per_day": flow.seepage_velocity_m_per_day,
            "seepage_velocity_ft_per_day": flow.seepage_velocity_ft_per_day,
        },
        "receptors": [
            {
                "name": r.receptor_name,
                "type": r.receptor_type,
                "distance_m": r.distance_m,
                "advective_travel_time_days": r.flow.travel_time_days(r.distance_m),
                "advective_travel_time_years": r.flow.travel_time_years(r.distance_m),
                "all_constituents_pass": r.all_constituents_pass,
                "minimum_log_removal": r.minimum_log_removal,
                "constituents": [
                    {
                        "name": t.constituent,
                        "C0": t.C0,
                        "C0_units": t.C0_units,
                        "retardation_factor": t.retardation_factor,
                        "solute_travel_time_days": t.solute_travel_time_days,
                        "C_receptor": t.C_receptor,
                        "log_removal": t.log_removal,
                        "regulatory_limit": t.regulatory_limit,
                        "passes_screening": t.passes_screening,
                    }
                    for t in r.transport_results
                ],
            }
            for r in receptor_evals
        ],
        "comparison_scenarios": comparisons,
        "attestation": attestation,
    }


# ---------------------------------------------------------------------------
# Text-report rendering
# ---------------------------------------------------------------------------

def render_text_report(results: dict) -> str:
    L = []
    P = results["project"]
    L.append("=" * 78)
    L.append("GROUNDWATER IMPACT EVALUATION - SCREENING REPORT")
    L.append("=" * 78)
    L.append(f"Project   : {P['name']}  (ID: {P.get('site_id','-')})")
    L.append(f"Engineer  : {P['engineer']}")
    L.append(f"Authority : {P['tceq_authority']}")
    L.append(f"Generated : {results['generated_utc']}")
    L.append("")
    L.append("-" * 78)
    L.append("SUBSURFACE CONDITIONS")
    L.append("-" * 78)
    sub = results["subsurface"]
    L.append(f"Soil type           : {sub['soil_type']}")
    L.append(f"Permeability class  : {sub['permeability_class']}")
    L.append(f"K_sat               : {sub['soil_properties']['K_sat_m_per_s']:.2e} m/s "
             f"({sub['K_sat_cm_per_hr']:.3f} cm/hr)")
    L.append(f"Effective porosity  : {sub['soil_properties']['effective_porosity']:.3f}")
    L.append(f"Bulk density        : {sub['soil_properties']['bulk_density_kg_per_m3']} kg/m^3")
    L.append(f"Hydraulic gradient  : {sub['hydraulic_gradient']:.4f}")
    L.append(f"Depth to water table: {sub.get('depth_to_water_table_m','-')} m")
    L.append("")
    L.append("-" * 78)
    L.append("DARCY FLOW")
    L.append("-" * 78)
    f = results["flow"]
    L.append(f"Darcy flux q       : {f['darcy_flux_m_per_s']:.3e} m/s")
    L.append(f"Seepage velocity   : {f['seepage_velocity_m_per_day']*1000:.4f} mm/day"
             f"  ({f['seepage_velocity_ft_per_day']:.5f} ft/day)")
    L.append("")
    L.append("-" * 78)
    L.append("RECEPTOR EVALUATION")
    L.append("-" * 78)
    for r in results["receptors"]:
        L.append(f"\n  Receptor: {r['name']}  [{r['type']}]")
        L.append(f"    distance              : {r['distance_m']:.2f} m "
                 f"({r['distance_m']/0.3048:.1f} ft)")
        L.append(f"    advective travel time : {r['advective_travel_time_days']:.1f} days "
                 f"({r['advective_travel_time_years']:.2f} yr)")
        L.append(f"    minimum log removal   : "
                 f"{r['minimum_log_removal']:.2f}" if r['minimum_log_removal'] != float('inf')
                 else "    minimum log removal   : >15 (effectively complete)")
        L.append(f"    all pass screening    : {r['all_constituents_pass']}")
        L.append(f"    {'constituent':<20}{'C0':>14}{'C_receptor':>16}{'limit':>14}  pass")
        for c in r["constituents"]:
            cval = f"{c['C_receptor']:.3e}" if c['C_receptor'] > 0 else "0.000e+00"
            L.append(f"    {c['name']:<20}"
                     f"{c['C0']:>14.3g}"
                     f"{cval:>16}"
                     f"{c['regulatory_limit']:>14.3g}"
                     f"  {'YES' if c['passes_screening'] else 'NO '}")
    L.append("")
    if results["comparison_scenarios"]:
        L.append("-" * 78)
        L.append("COMPARISON: HIGHER-PERMEABILITY SOILS (illustrative)")
        L.append("-" * 78)
        L.append(f"  {'soil':<14}{'K_sat (m/s)':>14}{'class':>20}"
                 f"{'v (ft/day)':>14}{'t to nearest (d)':>20}")
        for c in results["comparison_scenarios"]:
            L.append(f"  {c['soil_type']:<14}"
                     f"{c['K_sat_m_per_s']:>14.2e}"
                     f"{c['permeability_class']:>20}"
                     f"{c['seepage_velocity_ft_per_day']:>14.4f}"
                     f"{c['advective_travel_time_to_nearest_receptor_days']:>20.2f}")
        L.append("")
    L.append("-" * 78)
    L.append("NARRATIVE ATTESTATION (maps to standard waiver language)")
    L.append("-" * 78)
    for k, v in results["attestation"].items():
        L.append(f"  [{k}]")
        L.append(f"    {v}")
        L.append("")
    L.append("=" * 78)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run groundwater impact screening simulation."
    )
    parser.add_argument("config", type=Path,
                        help="Path to site configuration JSON")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output JSON path (default: output/<site_id>_results.json)")
    parser.add_argument("--text", type=Path, default=None,
                        help="Output text-report path")
    args = parser.parse_args(argv)

    site_cfg = load_json(args.config)
    soils, pathogens = load_databases()
    results = simulate_site(site_cfg, soils, pathogens)

    DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)
    site_id = site_cfg["project"].get("site_id", "site")

    out_json = args.output or (DEFAULT_OUTPUT_DIR / f"{site_id}_results.json")
    out_txt = args.text or (DEFAULT_OUTPUT_DIR / f"{site_id}_report.txt")

    with out_json.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    with out_txt.open("w", encoding="utf-8") as f:
        f.write(render_text_report(results))

    print(render_text_report(results))
    print(f"\n[wrote] {out_json}")
    print(f"[wrote] {out_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
