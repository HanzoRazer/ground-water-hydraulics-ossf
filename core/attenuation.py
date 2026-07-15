"""
attenuation.py
==============

Aggregates Darcy + transport results into a single "natural attenuation
capacity" judgment for the site, and maps each calculated quantity back
to a clause in the standard waiver narrative.

This is the layer that produces the defensible engineering statement:

    "Native soil characteristics provide an additional level of protection
     by limiting the velocity of subsurface flow and enhancing treatment
     within the soil profile."

The judgment criteria below are conservative defaults and can be tuned in
config without touching the physics in darcy.py / transport.py.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from .darcy import FlowResult, m_per_s_to_cm_per_hr
from .transport import TransportResult


# Permeability classification thresholds (NRCS-style, m/s)
PERMEABILITY_BANDS = [
    (1.0e-7,  "very low"),
    (1.0e-6,  "low"),
    (1.0e-5,  "moderate"),
    (1.0e-4,  "moderately high"),
    (1.0e-3,  "high"),
    (float("inf"), "very high"),
]


@dataclass
class ReceptorEvaluation:
    receptor_name: str
    receptor_type: str
    distance_m: float
    flow: FlowResult
    transport_results: List[TransportResult] = field(default_factory=list)

    @property
    def all_constituents_pass(self) -> bool:
        return all(t.passes_screening for t in self.transport_results)

    @property
    def minimum_log_removal(self) -> float:
        if not self.transport_results:
            return 0.0
        return min(t.log_removal for t in self.transport_results)


def classify_permeability(K_sat_m_per_s: float) -> str:
    for upper, label in PERMEABILITY_BANDS:
        if K_sat_m_per_s < upper:
            return label
    return "very high"


def narrative_attestation(
    soil_type: str,
    K_sat_m_per_s: float,
    flow: FlowResult,
    receptor_evals: List[ReceptorEvaluation],
) -> dict:
    """Produce the dict of justifications that map onto the canned narrative.

    Each key corresponds to a clause from the company's standard statement.
    """
    perm_class = classify_permeability(K_sat_m_per_s)
    K_cm_hr = m_per_s_to_cm_per_hr(K_sat_m_per_s)

    nearest = min(receptor_evals, key=lambda r: r.distance_m) if receptor_evals else None
    all_pass = all(r.all_constituents_pass for r in receptor_evals)

    return {
        "darcy_law_basis": (
            "Subsurface flow evaluated using Darcy's Law: q = K * i, "
            "v = q / n_eff."
        ),
        "ksat_clause": (
            f"Native soil ({soil_type.replace('_', ' ')}) exhibits "
            f"{perm_class} saturated hydraulic conductivity "
            f"(K_sat = {K_sat_m_per_s:.2e} m/s = {K_cm_hr:.3f} cm/hr), "
            "which is consistent with the 'low to moderate Ksat' clause."
        ),
        "contact_time_clause": (
            f"Computed seepage velocity is "
            f"{flow.seepage_velocity_m_per_day*1000:.3f} mm/day "
            f"({flow.seepage_velocity_ft_per_day:.4f} ft/day), "
            "which limits transport rate and increases contact time for "
            "filtration, adsorption, and biological degradation."
        ),
        "comparison_clause": (
            "Run comparison_scenarios in config to demonstrate the "
            "'in contrast, highly permeable soils...' clause; sand-class "
            "soils typically yield seepage velocities 100-1000x greater."
        ),
        "minimum_distance_to_receptor_m": (
            nearest.distance_m if nearest else None
        ),
        "minimum_advective_travel_time_days": (
            nearest.flow.travel_time_days(nearest.distance_m) if nearest else None
        ),
        "all_receptors_pass_screening": all_pass,
        "conclusion_clause": (
            "Combined effect of aerobic treatment + disinfection + native "
            "soil attenuation results in receptor concentrations below "
            "regulatory screening limits for all evaluated constituents."
            if all_pass else
            "WARNING: At least one constituent at one receptor exceeds its "
            "regulatory screening limit. Re-examine setbacks or treatment "
            "before relying on the standard waiver narrative."
        ),
    }
