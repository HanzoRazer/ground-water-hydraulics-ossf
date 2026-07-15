"""
darcy.py
========

Darcy's Law and seepage-velocity calculations for saturated porous media.

The fundamental relation is:

    q = -K * dh/dl              (Darcy flux / specific discharge, [m/s])
    v = q / n_eff               (average linear / seepage velocity, [m/s])
    t_advective = L / v         (advective travel time over distance L, [s])

Sign conventions are dropped here because we work with magnitudes and an
externally-supplied gradient direction (source -> receptor).

Units are SI throughout. Conversions are provided at module bottom for the
cm/hr and ft/day values commonly used in TCEQ Ch. 285 / NRCS reports.
"""

from __future__ import annotations
from dataclasses import dataclass


SECONDS_PER_DAY = 86_400.0
SECONDS_PER_YEAR = 365.25 * SECONDS_PER_DAY
M_PER_FT = 0.3048
M_PER_CM = 0.01


@dataclass(frozen=True)
class FlowResult:
    """Container for a single Darcy-flow evaluation."""
    K_sat_m_per_s: float
    gradient: float
    effective_porosity: float
    darcy_flux_m_per_s: float
    seepage_velocity_m_per_s: float
    seepage_velocity_m_per_day: float
    seepage_velocity_ft_per_day: float

    def travel_time_seconds(self, distance_m: float) -> float:
        if self.seepage_velocity_m_per_s <= 0.0:
            return float("inf")
        return distance_m / self.seepage_velocity_m_per_s

    def travel_time_days(self, distance_m: float) -> float:
        return self.travel_time_seconds(distance_m) / SECONDS_PER_DAY

    def travel_time_years(self, distance_m: float) -> float:
        return self.travel_time_seconds(distance_m) / SECONDS_PER_YEAR


def darcy_flux(K_sat: float, gradient: float) -> float:
    """Specific discharge q = K * i  [m/s].

    Parameters
    ----------
    K_sat : saturated hydraulic conductivity [m/s]
    gradient : hydraulic gradient dh/dl [m/m, dimensionless]
    """
    if K_sat < 0:
        raise ValueError("K_sat must be non-negative.")
    if gradient < 0:
        raise ValueError("gradient magnitude must be non-negative.")
    return K_sat * gradient


def seepage_velocity(K_sat: float, gradient: float, effective_porosity: float) -> float:
    """Average linear groundwater velocity v = q / n_eff  [m/s]."""
    if not 0.0 < effective_porosity <= 1.0:
        raise ValueError("effective_porosity must be in (0, 1].")
    return darcy_flux(K_sat, gradient) / effective_porosity


def evaluate_flow(K_sat: float, gradient: float, effective_porosity: float) -> FlowResult:
    """Compute and return a populated FlowResult."""
    q = darcy_flux(K_sat, gradient)
    v = seepage_velocity(K_sat, gradient, effective_porosity)
    return FlowResult(
        K_sat_m_per_s=K_sat,
        gradient=gradient,
        effective_porosity=effective_porosity,
        darcy_flux_m_per_s=q,
        seepage_velocity_m_per_s=v,
        seepage_velocity_m_per_day=v * SECONDS_PER_DAY,
        seepage_velocity_ft_per_day=v * SECONDS_PER_DAY / M_PER_FT,
    )


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

def cm_per_hr_to_m_per_s(K_cm_hr: float) -> float:
    return K_cm_hr * M_PER_CM / 3600.0


def m_per_s_to_cm_per_hr(K_m_s: float) -> float:
    return K_m_s / M_PER_CM * 3600.0


def m_per_s_to_ft_per_day(v_m_s: float) -> float:
    return v_m_s * SECONDS_PER_DAY / M_PER_FT
