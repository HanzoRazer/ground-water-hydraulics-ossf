"""
Human-readable text report formatter for OSSF groundwater screening.

The generated report maps each clause of a typical OSSF setback waiver
narrative to an explicit equation and computed value so that an outside
reviewer can reproduce every number without additional data sources.
"""

from __future__ import annotations

import textwrap
from typing import Any

_WIDTH = 80
_SEP = "=" * _WIDTH
_DASH = "-" * _WIDTH


def _hr(char: str = "-") -> str:
    return char * _WIDTH


def _center(text: str) -> str:
    return text.center(_WIDTH)


def _kv(label: str, value: str, width: int = 30) -> str:
    return f"  {label:<{width}}{value}"


def _pass_fail(c: float, limit: float, lower_is_better: bool = True) -> str:
    """Return a PASS / FAIL tag and margin description."""
    if limit == 0.0:
        if c == 0.0:
            return "PASS  (concentration effectively zero)"
        return f"FAIL  ({c:.3e} > limit of {limit})"
    if lower_is_better:
        if c <= limit:
            pct = (1.0 - c / limit) * 100.0
            return f"PASS  ({pct:.1f}% below limit of {limit})"
        else:
            pct = (c / limit - 1.0) * 100.0
            return f"FAIL  ({pct:.1f}% above limit of {limit})"
    return "N/A"


def build_report(results: dict[str, Any]) -> str:
    """Render *results* (as produced by simulate.py) into a text report.

    Parameters
    ----------
    results:
        The dictionary returned by ``run_screening()``.

    Returns
    -------
    str
        Multi-line text suitable for writing to a ``.txt`` file.
    """
    lines: list[str] = []

    def L(s: str = "") -> None:
        lines.append(s)

    site = results["site"]
    site_soil = results["site_soil_properties"]
    comp_soil = results.get("comparison_soil_properties")
    darcy_site = results["darcy_site"]
    receptor_results = results["receptor_results"]
    darcy_comp = results.get("darcy_comparison")
    comparison_results = results.get("comparison_results")

    # ------------------------------------------------------------------ header
    L(_SEP)
    L(_center("GROUNDWATER SCREENING ANALYSIS"))
    L(_center("OSSF Setback Evaluation — EPA Soil Screening Framework (1996)"))
    L(_SEP)
    L()

    # --------------------------------------------------------- site parameters
    L("SITE PARAMETERS")
    L(_hr())
    L(_kv("Site ID", site["site_id"]))
    L(_kv("Description", site.get("description", "—")))
    L(_kv("Site Soil Class", site["soil_class"]))
    L(_kv("Hydraulic Gradient i", f"{site['hydraulic_gradient']:.4f}  [m/m]"))
    L(_kv("Treatment Type", site.get("treatment_type", "—")))
    L(_kv("Comparison Soil Class", site.get("comparison_soil", "—")))
    L()

    # ------------------------------------------------------ soil properties
    L("SOIL HYDRAULIC PROPERTIES  (Carsel & Parrish, 1988)")
    L(_hr())

    col_w = 22
    hdr_fmt = f"  {{:<30}}{{:>{col_w}}}{{:>{col_w}}}"
    row_fmt = f"  {{:<30}}{{:>{col_w}}}{{:>{col_w}}}"

    comp_name = site.get("comparison_soil", "Comparison")
    L(hdr_fmt.format("Parameter", site["soil_class"], comp_name))
    L(hdr_fmt.format("", "(site soil)", "(high-K reference)"))
    L(f"  {_hr('-')[:76]}")

    def prop_row(label: str, site_val: str, comp_val: str) -> None:
        L(row_fmt.format(label, site_val, comp_val))

    comp_props = comp_soil if comp_soil else {}
    prop_row(
        "K  (sat. hyd. conductivity)",
        f"{site_soil['K_m_per_day']:.4f} m/day",
        f"{comp_props.get('K_m_per_day', '—'):.4f} m/day"
        if comp_props else "—",
    )
    prop_row(
        "n_e  (effective porosity)",
        f"{site_soil['n_e']:.3f}",
        f"{comp_props.get('n_e', '—'):.3f}" if comp_props else "—",
    )
    prop_row(
        "ρ_b  (bulk density)",
        f"{site_soil['rho_b_g_per_cm3']:.2f} g/cm³",
        f"{comp_props.get('rho_b_g_per_cm3', '—'):.2f} g/cm³"
        if comp_props else "—",
    )
    prop_row(
        "f_oc  (org. carbon fraction)",
        f"{site_soil['f_oc']:.4f}",
        f"{comp_props.get('f_oc', '—'):.4f}" if comp_props else "—",
    )
    L()

    # ---------------------------------------------- Darcy transport — site
    L(f"DARCY TRANSPORT — SITE SOIL ({site['soil_class'].upper()})")
    L(_hr())
    L(f"  q  = K × i  =  {site_soil['K_m_per_day']:.4f} m/day × "
      f"{site['hydraulic_gradient']:.4f}  =  {darcy_site['q_m_per_day']:.4e} m/day")
    L(f"  vs = q / n_e =  {darcy_site['q_m_per_day']:.4e} / "
      f"{site_soil['n_e']:.3f}  =  {darcy_site['vs_m_per_day']:.4e} m/day")
    L()

    if darcy_comp:
        L(f"DARCY TRANSPORT — COMPARISON SOIL ({comp_name.upper()})")
        L(_hr())
        if comp_props:
            L(f"  q  = K × i  =  {comp_props['K_m_per_day']:.4f} m/day × "
              f"{site['hydraulic_gradient']:.4f}  =  {darcy_comp['q_m_per_day']:.4e} m/day")
            L(f"  vs = q / n_e =  {darcy_comp['q_m_per_day']:.4e} / "
              f"{comp_props['n_e']:.3f}  =  {darcy_comp['vs_m_per_day']:.4e} m/day")
        speed_ratio = darcy_comp["vs_m_per_day"] / darcy_site["vs_m_per_day"]
        L(f"  → Seepage velocity in {comp_name} is {speed_ratio:.0f}× faster than "
          f"in {site['soil_class']}.")
        L()

    # ------------------------------------------- receptor analysis — site
    L("RECEPTOR ANALYSIS — SITE SOIL")
    L(_SEP)

    for rec in receptor_results:
        L()
        L(f"  Receptor : {rec['receptor_name']}  "
          f"(L = {rec['distance_m']:.1f} m)")
        L(f"  {'Advective travel time':<30}"
          f"{rec['t_adv_days']:>14,.1f} days  "
          f"({rec['t_adv_days'] / 365.25:,.1f} yr)")
        L()

        for c in rec["constituents"]:
            L(f"    ── {c['constituent']} ──")
            L(f"       C₀                  = {c['C0']:.3g} {c['unit']}")
            L(f"       K_oc                = {c['K_oc_mL_per_g']:.1f} mL/g")
            L(f"       K_d  = K_oc × f_oc = {c['K_oc_mL_per_g']:.1f} × "
              f"{site_soil['f_oc']:.4f} = {c['K_d_mL_per_g']:.4f} mL/g")
            L(f"       R    = 1 + (ρ_b/n_e) × K_d  = {c['R']:.3f}")
            L(f"       Retarded travel time         = {rec['t_adv_days']:.1f} × "
              f"{c['R']:.3f} = {c['t_r_days']:>14,.1f} days")
            L(f"       λ (decay constant)           = {c['lambda_per_day']:.3f} /day")
            L(f"       Attenuation factor AF        = exp(−{c['lambda_per_day']:.3f} × "
              f"{c['t_r_days']:.1f}) = {c['attenuation_factor']:.3e}")
            L(f"       Receptor concentration C     = {c['C0']:.3g} × "
              f"{c['attenuation_factor']:.3e} = {c['C_receptor']:.3e} {c['unit']}")
            L(f"       Regulatory limit             = {c['limit']} {c['unit']}")
            L(f"       Result : {_pass_fail(c['C_receptor'], c['limit'])}")
            L()

        L(f"  {_hr('-')[:76]}")

    # ------------------------------------------ comparison soil analysis
    if comparison_results:
        L()
        L(f"RECEPTOR ANALYSIS — COMPARISON SOIL ({comp_name.upper()})")
        L(_SEP)
        L("  (Demonstrates that higher-permeability soils provide substantially")
        L("   less attenuation — supporting the waiver narrative.)")
        L()

        for rec in comparison_results:
            L(f"  Receptor : {rec['receptor_name']}  "
              f"(L = {rec['distance_m']:.1f} m)")
            L(f"  {'Advective travel time':<30}"
              f"{rec['t_adv_days']:>14,.1f} days  "
              f"({rec['t_adv_days'] / 365.25:,.1f} yr)")
            L()

            for c in rec["constituents"]:
                L(f"    ── {c['constituent']} ──")
                L(f"       AF = exp(−{c['lambda_per_day']:.3f} × {c['t_r_days']:.1f}) "
                  f"= {c['attenuation_factor']:.3e}")
                L(f"       C  = {c['C0']:.3g} × {c['attenuation_factor']:.3e} "
                  f"= {c['C_receptor']:.3e} {c['unit']}")
                L(f"       Result : {_pass_fail(c['C_receptor'], c['limit'])}")
                L()

            L(f"  {_hr('-')[:76]}")

    # ---------------------------------------------------------------- conclusion
    L()
    L(_SEP)
    L(_center("CONCLUSION"))
    L(_SEP)
    L()

    site_passes = _all_pass(receptor_results)
    comp_fails = comparison_results and not _all_pass(comparison_results)

    if site_passes:
        L(textwrap.fill(
            f"All constituents at all receptors meet regulatory screening limits "
            f"for the site soil ({site['soil_class']}). The low saturated hydraulic "
            f"conductivity of this native soil class (K = "
            f"{site_soil['K_m_per_day']:.4f} m/day) combined with first-order "
            f"decay over the extended travel times produces adequate attenuation "
            f"at each receptor considered.",
            width=_WIDTH, initial_indent="  ", subsequent_indent="  ",
        ))
    else:
        L(textwrap.fill(
            f"One or more constituents exceed regulatory screening limits for the "
            f"site soil ({site['soil_class']}). Review source concentrations, "
            f"receptor distances, and treatment assumptions before relying on this "
            f"screening result.",
            width=_WIDTH, initial_indent="  ", subsequent_indent="  ",
        ))
    L()

    if comp_fails and site_passes:
        L(textwrap.fill(
            f"In contrast, the high-permeability {comp_name} soil produces "
            f"significantly shorter travel times and higher receptor concentrations, "
            f"demonstrating that the low-K native soil is a critical factor "
            f"in achieving adequate attenuation. Sites with more permeable soils "
            f"would require either greater setback distances or higher treatment "
            f"levels.",
            width=_WIDTH, initial_indent="  ", subsequent_indent="  ",
        ))
        L()

    L(textwrap.fill(
        "DISCLAIMER: This screening analysis is provided as a technical aid. "
        "Results support — but do not replace — the professional judgment of a "
        "licensed P.E. familiar with the specific site, its soils, and the "
        "applicable regulatory framework. Use of this toolkit does not constitute "
        "nor imply a regulatory determination by TCEQ or any other authority.",
        width=_WIDTH, initial_indent="  ", subsequent_indent="  ",
    ))
    L()
    L(_SEP)

    return "\n".join(lines)


def _all_pass(receptor_results: list[dict]) -> bool:
    """Return True if every constituent at every receptor passes its limit."""
    for rec in receptor_results:
        for c in rec["constituents"]:
            limit = c["limit"]
            conc = c["C_receptor"]
            if limit == 0.0:
                if conc > 0.0:
                    return False
            elif conc > limit:
                return False
    return True
