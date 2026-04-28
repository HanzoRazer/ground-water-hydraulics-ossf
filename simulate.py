#!/usr/bin/env python3
"""
simulate.py — Groundwater Screening Toolkit CLI entry point.

Usage
-----
    python simulate.py config/site_example.json

Outputs (written to output/<site_id>_results.json and
         output/<site_id>_report.txt):

- Structured JSON results file with all intermediate values.
- Human-readable text report suitable for inclusion in a TCEQ Ch. 285
  setback waiver submittal or engineering report appendix.

Methodology
-----------
One-dimensional, steady-state, saturated-zone advection–retardation–decay
screening consistent with the EPA Soil Screening Guidance (1996).

References
----------
USEPA (1996). Soil Screening Guidance: Technical Background Document.
    EPA/540/R-95/128.
Carsel, R.F. & Parrish, R.S. (1988). Developing joint probability
    distributions of soil water retention characteristics.
    Water Resources Research 24(5):755–769.
Pang, L. (2009). Microbial removal rates in subsurface media estimated
    from published studies. Journal of Environmental Quality 38:1531–1559.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Resolve paths relative to this file so the script can be invoked from any
# working directory.
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).parent.resolve()
_DATA_DIR = _HERE / "data"
_OUTPUT_DIR = _HERE / "output"


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_json(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_databases() -> tuple[dict, dict]:
    """Return (soils_db, constituents_db)."""
    soils_db = _load_json(_DATA_DIR / "soils.json")
    constituents_db = _load_json(_DATA_DIR / "constituents.json")
    return soils_db, constituents_db


# ---------------------------------------------------------------------------
# Core screening calculation
# ---------------------------------------------------------------------------

def _analyse_receptor(
    receptor: dict[str, Any],
    vs_m_per_day: float,
    soil_props: dict[str, Any],
    constituent_names: list[str],
    effluent_concs: dict[str, Any],
    constituents_db: dict[str, Any],
) -> dict[str, Any]:
    """Run the full screening calculation for one receptor.

    Returns a dictionary containing travel time and per-constituent results.
    """
    from core import transport

    name = receptor["name"]
    dist = float(receptor["distance_m"])

    t_adv = transport.advective_travel_time(dist, vs_m_per_day)

    constituent_rows: list[dict] = []
    for cname in constituent_names:
        cprops = constituents_db[cname]
        K_oc = float(cprops["K_oc_mL_per_g"])
        lam = float(cprops["lambda_per_day"])
        limit = float(cprops["limit"])
        unit = cprops["limit_unit"]

        # Source concentration — site config overrides DB default
        if cname in effluent_concs:
            C0 = float(effluent_concs[cname]["C0"])
        else:
            C0 = float(cprops["C0_default"])

        K_d = transport.distribution_coefficient(K_oc, float(soil_props["f_oc"]))
        R = transport.retardation_factor(
            float(soil_props["rho_b_g_per_cm3"]),
            float(soil_props["n_e"]),
            K_d,
        )
        t_r = transport.retarded_travel_time(t_adv, R)
        af = transport.attenuation_factor(lam, t_r)
        C_rec = transport.receptor_concentration(C0, lam, t_r)

        constituent_rows.append(
            {
                "constituent": cname,
                "C0": C0,
                "unit": unit,
                "K_oc_mL_per_g": K_oc,
                "K_d_mL_per_g": K_d,
                "R": R,
                "t_r_days": t_r,
                "lambda_per_day": lam,
                "attenuation_factor": af,
                "C_receptor": C_rec,
                "limit": limit,
                "passes": C_rec <= limit if limit > 0 else C_rec == 0.0,
            }
        )

    return {
        "receptor_name": name,
        "distance_m": dist,
        "t_adv_days": t_adv,
        "constituents": constituent_rows,
    }


def run_screening(config: dict[str, Any]) -> dict[str, Any]:
    """Execute the full screening workflow for the given site config.

    Parameters
    ----------
    config:
        Parsed site configuration dictionary (from JSON).

    Returns
    -------
    dict
        Structured results dictionary (also serialised to JSON output).
    """
    from core import darcy as darcy_mod

    soils_db, constituents_db = _load_databases()

    # ------------------------------------------------------------------ inputs
    soil_class = config["soil_class"]
    gradient = float(config["hydraulic_gradient"])
    receptors = config["receptors"]
    constituent_names: list[str] = config["constituents"]
    comp_soil_class: str | None = config.get("comparison_soil")
    effluent_concs: dict = config.get("effluent_concentrations", {})

    # Validate soil class
    if soil_class not in soils_db:
        raise KeyError(
            f"Soil class '{soil_class}' not found in soils database. "
            f"Available: {sorted(k for k in soils_db if not k.startswith('_'))}"
        )
    # Validate constituent names
    for cname in constituent_names:
        if cname not in constituents_db:
            raise KeyError(
                f"Constituent '{cname}' not found in constituents database. "
                f"Available: {sorted(k for k in constituents_db if not k.startswith('_'))}"
            )

    site_soil = soils_db[soil_class]
    K_site = float(site_soil["K_m_per_day"])
    ne_site = float(site_soil["n_e"])

    # -------------------------------------------------------------- site Darcy
    q_site = darcy_mod.darcy_flux(K_site, gradient)
    vs_site = darcy_mod.seepage_velocity(q_site, ne_site)

    darcy_site = {"q_m_per_day": q_site, "vs_m_per_day": vs_site}

    # ---------------------------------------------------------- site receptors
    receptor_results = [
        _analyse_receptor(
            rec, vs_site, site_soil, constituent_names, effluent_concs, constituents_db
        )
        for rec in receptors
    ]

    # --------------------------------------------------- comparison soil Darcy
    darcy_comp: dict | None = None
    comp_soil_props: dict | None = None
    comparison_results: list | None = None

    if comp_soil_class:
        if comp_soil_class not in soils_db:
            raise KeyError(
                f"Comparison soil class '{comp_soil_class}' not found in soils database."
            )
        comp_soil_props = soils_db[comp_soil_class]
        K_comp = float(comp_soil_props["K_m_per_day"])
        ne_comp = float(comp_soil_props["n_e"])
        q_comp = darcy_mod.darcy_flux(K_comp, gradient)
        vs_comp = darcy_mod.seepage_velocity(q_comp, ne_comp)
        darcy_comp = {"q_m_per_day": q_comp, "vs_m_per_day": vs_comp}

        comparison_results = [
            _analyse_receptor(
                rec,
                vs_comp,
                comp_soil_props,
                constituent_names,
                effluent_concs,
                constituents_db,
            )
            for rec in receptors
        ]

    # --------------------------------------------------------- assemble result
    results: dict[str, Any] = {
        "meta": {
            "toolkit": "Groundwater Screening Toolkit v1.0",
            "methodology": "EPA Soil Screening Guidance (1996), 1-D steady-state advection-retardation-decay",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        },
        "site": {
            "site_id": config.get("site_id", "unknown"),
            "description": config.get("description", ""),
            "soil_class": soil_class,
            "hydraulic_gradient": gradient,
            "treatment_type": config.get("treatment_type", ""),
            "comparison_soil": comp_soil_class,
        },
        "site_soil_properties": site_soil,
        "comparison_soil_properties": comp_soil_props,
        "darcy_site": darcy_site,
        "darcy_comparison": darcy_comp,
        "receptor_results": receptor_results,
        "comparison_results": comparison_results,
    }
    return results


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_outputs(results: dict[str, Any]) -> tuple[pathlib.Path, pathlib.Path]:
    """Write JSON and text-report files to the output directory.

    Returns
    -------
    (json_path, txt_path)
    """
    from core.report import build_report

    _OUTPUT_DIR.mkdir(exist_ok=True)
    site_id = results["site"]["site_id"]

    json_path = _OUTPUT_DIR / f"{site_id}_results.json"
    txt_path = _OUTPUT_DIR / f"{site_id}_report.txt"

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)

    report_text = build_report(results)
    with txt_path.open("w", encoding="utf-8") as fh:
        fh.write(report_text)
        fh.write("\n")

    return json_path, txt_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Groundwater Screening Toolkit — OSSF setback evaluation.\n\n"
            "Computes Darcy flux, seepage velocity, advective travel times, "
            "retardation factors, and first-order decay for each effluent "
            "constituent at each receptor, then compares site soil against a "
            "high-permeability reference soil."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "config",
        metavar="CONFIG_JSON",
        help="Path to site configuration JSON file (e.g. config/site_example.json).",
    )
    args = parser.parse_args(argv)

    config_path = pathlib.Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 1

    print(f"Loading config: {config_path}")
    config = _load_json(config_path)

    print(f"Running screening for site: {config.get('site_id', '?')}")
    try:
        results = run_screening(config)
    except (KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    json_path, txt_path = _write_outputs(results)
    print(f"Results JSON : {json_path}")
    print(f"Text report  : {txt_path}")

    # Print a brief summary to stdout
    print()
    print("─" * 60)
    all_pass = True
    for rec in results["receptor_results"]:
        for c in rec["constituents"]:
            status = "PASS" if c["passes"] else "FAIL"
            if not c["passes"]:
                all_pass = False
            print(
                f"  {rec['receptor_name']:<35} "
                f"{c['constituent']:<12} {status}"
            )
    print("─" * 60)
    print("Overall:", "ALL PASS" if all_pass else "ONE OR MORE FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
