"""
transport.py
============

One-dimensional advective transport of an effluent constituent from a
continuous source to a downgradient receptor, including:

  * linear-equilibrium retardation:        R = 1 + (rho_b * Kd) / theta
  * solute travel time:                    t_solute = R * t_advective
  * first-order decay during transport:    C(t) = C0 * exp(-lambda * t)

This is intentionally a screening-level model. It is consistent with the
analytical-solution framework used in EPA's Soil Screening Guidance (1996)
and is appropriate for the OSSF waiver narrative: it shows that even with
conservative assumptions, the combination of low K_sat, retardation, and
microbial die-off attenuates effluent constituents below screening limits
at the receptor.
"""

from __future__ import annotations
from dataclasses import dataclass
import math

from .darcy import FlowResult, SECONDS_PER_DAY


@dataclass(frozen=True)
class TransportResult:
    constituent: str
    distance_m: float
    C0: float
    C0_units: str
    advective_travel_time_days: float
    retardation_factor: float
    solute_travel_time_days: float
    lambda_per_day: float
    C_receptor: float
    log_removal: float
    regulatory_limit: float
    passes_screening: bool


def retardation_factor(bulk_density_kg_m3: float, Kd_L_per_kg: float, porosity: float) -> float:
    """R = 1 + (rho_b [kg/m^3] * Kd [L/kg] * 1e-3 [m^3/L]) / theta.

    The 1e-3 converts L -> m^3 so the result is dimensionless.
    For Kd = 0 (e.g., nitrate), R reduces to 1.0 (no retardation).
    """
    if porosity <= 0.0:
        raise ValueError("porosity must be positive.")
    if Kd_L_per_kg < 0 or bulk_density_kg_m3 < 0:
        raise ValueError("Kd and bulk_density must be non-negative.")
    return 1.0 + (bulk_density_kg_m3 * Kd_L_per_kg * 1e-3) / porosity


def first_order_decay(C0: float, lambda_per_day: float, time_days: float) -> float:
    """C(t) = C0 * exp(-lambda * t).  Conservative tracer if lambda = 0."""
    if C0 < 0 or lambda_per_day < 0 or time_days < 0:
        raise ValueError("C0, lambda, and time must be non-negative.")
    if math.isinf(time_days):
        return 0.0 if lambda_per_day > 0 else C0
    return C0 * math.exp(-lambda_per_day * time_days)


def log_removal(C0: float, C_final: float) -> float:
    """log10(C0/C); returns +inf for complete attenuation, 0 for no change."""
    if C0 <= 0:
        return 0.0
    if C_final <= 0:
        return float("inf")
    return math.log10(C0 / C_final)


def evaluate_transport(
    constituent_name: str,
    constituent_props: dict,
    soil_props: dict,
    flow: FlowResult,
    distance_m: float,
    C0_override: float | None = None,
) -> TransportResult:
    """Run the full source -> receptor transport calculation for one constituent.

    Parameters
    ----------
    constituent_name : key from data/pathogens.json
    constituent_props : dict from data/pathogens.json["constituents"][name]
    soil_props : dict from data/soil_database.json["soils"][soil_type]
    flow : FlowResult from darcy.evaluate_flow()
    distance_m : source-to-receptor distance [m]
    C0_override : optional override for source concentration
    """
    C0 = C0_override if C0_override is not None else constituent_props["typical_C0_post_disinfection"]
    lam = constituent_props["lambda_per_day"]
    Kd = constituent_props["Kd_L_per_kg"]
    limit = constituent_props["regulatory_limit"]
    units = constituent_props["C0_units"]

    rho_b = soil_props["bulk_density_kg_per_m3"]
    theta = soil_props["effective_porosity"]

    R = retardation_factor(rho_b, Kd, theta)
    t_adv_days = flow.travel_time_days(distance_m)
    t_solute_days = R * t_adv_days
    C_receptor = first_order_decay(C0, lam, t_solute_days)

    return TransportResult(
        constituent=constituent_name,
        distance_m=distance_m,
        C0=C0,
        C0_units=units,
        advective_travel_time_days=t_adv_days,
        retardation_factor=R,
        solute_travel_time_days=t_solute_days,
        lambda_per_day=lam,
        C_receptor=C_receptor,
        log_removal=log_removal(C0, C_receptor),
        regulatory_limit=limit,
        passes_screening=C_receptor <= limit,
    )
