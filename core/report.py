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


def _pass_fail(c_row: dict[str, Any]) -> str:
    """Return a PASS / FAIL tag and margin description for a constituent row.

    Uses the ``passes`` flag already computed by the screening engine (single
    source of truth) and describes the margin honestly:

    * Numeric limit: percent below/above the limit.
    * Non-detect target (limit == 0): the achieved log-removal against the
      documented target. A modeled concentration that has underflowed to zero
      is reported as being below the *computational floor* — explicitly a
      screening artifact, not a measured absence.
    """
    conc = c_row["C_receptor"]
    limit = c_row["limit"]
    passes = c_row["passes"]

    if c_row.get("limit_is_nondetect", limit == 0.0):
        target = c_row.get("nondetect_log_removal_target", 4.0)
        lr = c_row.get("log_removal", float("inf"))
        if lr == float("inf"):
            floor_note = (
                f"modeled C below computational floor \u2014 screening artifact, "
                f"not measured absence; treated as \u2265 {target:.0f}-log non-detect target"
            )
            return f"PASS  ({floor_note})" if passes else f"FAIL  ({floor_note})"
        if passes:
            return f"PASS  ({lr:.1f}-log removal \u2265 {target:.0f}-log non-detect target)"
        return f"FAIL  ({lr:.1f}-log removal < {target:.0f}-log non-detect target)"

    # Positive numeric limit
    if limit <= 0:
        return "N/A"
    if passes:
        pct = (1.0 - conc / limit) * 100.0
        return f"PASS  ({pct:.1f}% below limit of {limit})"
    pct = (conc / limit - 1.0) * 100.0
    return f"FAIL  ({pct:.1f}% above limit of {limit})"


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

    # ------------------------------------------------ model scope & limitations
    L("MODEL SCOPE & LIMITATIONS")
    L(_hr())
    L(textwrap.fill(
        "This is a coarse SCREENING model. It assumes one-dimensional, "
        "steady-state, saturated-zone flow through a single homogeneous soil, "
        "with linear-equilibrium sorption and first-order decay. It does NOT "
        "represent layered soils, unsaturated (vadose) transport, transient "
        "flow, preferential/fracture flow, or karst. Results are screening "
        "estimates, not site-specific predictions, and do not constitute a "
        "regulatory determination. Do not apply this tool to sites whose "
        "conditions violate the assumptions above without independent analysis.",
        width=_WIDTH, initial_indent="  ", subsequent_indent="  ",
    ))
    L()

    # --------------------------------------------------------- site parameters
    L("SITE PARAMETERS")
    L(_hr())
    L(_kv("Site ID", site["site_id"]))
    L(_kv("Description", site.get("description", "—")))
    L(_kv("Site Soil Class", site["soil_class"]))
    L(_kv("Hydraulic Gradient i", f"{site['hydraulic_gradient']:.4f}  [m/m]"))
    L(_kv("Treatment Type", f"{site.get('treatment_type', '—')}  (metadata only; does not affect the calculation)"))
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
        L(f"  → Under these screening assumptions, seepage velocity in {comp_name} is "
          f"approximately {speed_ratio:,.1f}× that in {site['soil_class']}.")
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
            L(f"       Result : {_pass_fail(c)}")
            L()

        L(f"  {_hr('-')[:76]}")

    # ------------------------------------------ comparison soil analysis
    if comparison_results:
        L()
        L(f"RECEPTOR ANALYSIS — COMPARISON SOIL ({comp_name.upper()})")
        L(_SEP)
        L("  (Illustrates, under the model's assumptions, that higher-permeability")
        L("   soils provide less attenuation. Screening-level comparison only.)")
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
                L(f"       Result : {_pass_fail(c)}")
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
            f"At the screening level, all constituents at all receptors meet their "
            f"screening criteria for the site soil ({site['soil_class']}) under the "
            f"assumptions stated below. In the model, the low saturated hydraulic "
            f"conductivity of this native soil class (K = "
            f"{site_soil['K_m_per_day']:.4f} m/day) combined with first-order decay "
            f"over the modeled travel times produces attenuation sufficient to meet "
            f"the criteria at each receptor considered. This is a screening result, "
            f"not a site-specific prediction or a regulatory determination.",
            width=_WIDTH, initial_indent="  ", subsequent_indent="  ",
        ))
    else:
        L(textwrap.fill(
            f"At the screening level, one or more constituents do not meet their "
            f"screening criteria for the site soil ({site['soil_class']}). Review "
            f"source concentrations, receptor distances, and treatment assumptions "
            f"before relying on this screening result.",
            width=_WIDTH, initial_indent="  ", subsequent_indent="  ",
        ))
    L()

    if comp_fails and site_passes:
        L(textwrap.fill(
            f"For comparison, the higher-permeability {comp_name} soil produces "
            f"shorter modeled travel times and higher modeled receptor "
            f"concentrations. This indicates, under these screening assumptions, "
            f"that native soil permeability is an important control on attenuation "
            f"at this site; sites with more permeable soils would likely require "
            f"greater setback distances or higher treatment levels. This comparison "
            f"is illustrative and does not by itself establish compliance.",
            width=_WIDTH, initial_indent="  ", subsequent_indent="  ",
        ))
        L()

    meta = results.get("meta", {})
    prov = meta.get("provenance", {})
    if prov or meta.get("generated_utc"):
        L("DATA PROVENANCE")
        L(_hr())
        L(_kv("Toolkit", str(meta.get("toolkit", "—"))))
        L(_kv("Generated (UTC)", str(meta.get("generated_utc", "—"))))
        L(_kv("Config schema version", str(meta.get("config_schema_version", "—"))))
        L(_kv("Soils DB (sha256/16)", str(prov.get("soils_db_sha256", "—"))))
        L(_kv("Constituents DB (sha256/16)", str(prov.get("constituents_db_sha256", "—"))))
        L(_kv("Non-detect target", f"{meta.get('nondetect_log_removal_target', '—')}-log removal"))
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
    """Return True if every constituent at every receptor passes.

    Uses the ``passes`` flag produced by the screening engine so that the
    report and the engine share one pass/fail policy (numeric limit vs.
    log-removal non-detect target) rather than re-deriving it here.
    """
    for rec in receptor_results:
        for c in rec["constituents"]:
            if not c["passes"]:
                return False
    return True
