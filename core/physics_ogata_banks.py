"""
physics_ogata_banks.py
======================

One-dimensional advection-dispersion transport with linear-equilibrium
retardation and first-order decay. Continuous source, semi-infinite domain.

Governing equation:

    R * dc/dt = D_L * d²c/dx² - v * dc/dx - λ * R * c

Analytical steady-state solution (Ogata & Banks 1961; Van Genuchten &
Alves 1982 solution A1):

    c_ss(x) / c0 = exp( (v - U) * x / (2 * D_L) )

where:

    U = v * sqrt(1 + 4 * λ * R * D_L / v²)
    D_L = α_L * v   (longitudinal dispersivity × seepage velocity)

For the OSSF screening use case, the steady-state form represents the
worst-case concentration at the receptor after a long-running continuous
source. This is the number that appears in the report.

Sanity limits (verified by tests):
  * λ → 0:  c_ss / c0 → 1 (conservative tracer, no attenuation).
  * D_L → 0:  c_ss / c0 → exp(-λ * R * x / v)  (pure advection + decay).
  * λ large:  c_ss → 0 (strong decay).

Reference:
    Van Genuchten, M.Th. and Alves, W.J. (1982). Analytical solutions of
    the one-dimensional convective-dispersive solute transport equation.
    USDA Technical Bulletin 1661. Solution A1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .physics_engine_base import AbstractPhysicsEngine


ENGINE_NAME = "ogata_banks_1d"
ENGINE_VERSION = "1.0.0"
ENGINE_DESCRIPTION = (
    "1D advection-dispersion transport with linear retardation and "
    "first-order decay. Continuous source, semi-infinite domain. "
    "Van Genuchten & Alves (1982) solution A1."
)
ENGINE_SCOPE_NOTES = (
    "Appropriate for on-axis receptors, homogeneous soils, steady flow. "
    "Not appropriate for off-axis receptors (no transverse dispersion), "
    "heterogeneous soils, or transient sources."
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OgataBanksResult:
    """Output of one Ogata-Banks steady-state evaluation."""
    C0: float
    C_receptor_steady_state: float
    retardation_factor: float
    longitudinal_dispersivity_m: float
    distance_m: float
    seepage_velocity_m_per_day: float
    K_sat_m_per_day: float
    hydraulic_gradient: float
    lambda_per_day: float
    Kd_L_per_kg: float
    bulk_density_kg_m3: float
    effective_porosity: float


# ---------------------------------------------------------------------------
# Pure-math primitives (ungoverned, for characterization testing)
# ---------------------------------------------------------------------------

def longitudinal_dispersivity_m(distance_m: float, method: str = "epa_ssg") -> float:
    """Estimate longitudinal dispersivity (m) as a function of distance.

    * ``epa_ssg``:     α_L = 0.1 * L  (EPA SSG 1996 default).
    * ``xu_eckstein``: α_L = 0.83 * (log10(L))^2.414  (Xu & Eckstein 1995).
    """
    if distance_m <= 0:
        return 0.0
    if method == "epa_ssg":
        return 0.1 * distance_m
    if method == "xu_eckstein":
        log_l = math.log10(distance_m)
        return max(0.0, 0.83 * (log_l ** 2.414))
    raise ValueError(f"Unknown dispersivity method: {method!r}")


def retardation_factor(
    Kd_L_per_kg: float,
    bulk_density_kg_m3: float,
    effective_porosity: float,
) -> float:
    """R = 1 + (ρ_b / n_e) * K_d."""
    if effective_porosity <= 0:
        raise ValueError("effective_porosity must be positive")
    # Convert K_d from L/kg to m³/kg for consistent SI units.
    Kd_m3_per_kg = Kd_L_per_kg * 1e-3
    rho_b_kg_m3 = bulk_density_kg_m3
    return 1.0 + (rho_b_kg_m3 / effective_porosity) * Kd_m3_per_kg


def concentration_steady_state(
    C0: float,
    v: float,      # seepage velocity [m/day]
    lam: float,    # first-order decay [1/day]
    R: float,      # retardation factor [-]
    x: float,      # distance [m]
    D_L: float,    # longitudinal dispersion coefficient [m²/day]
) -> float:
    """Ogata-Banks steady-state solution: c_ss / c0 = exp((v - U) x / (2 D_L)).

    Returns C_receptor_steady_state directly.

    Handles the zero-dispersion limit (D_L → 0) analytically.
    """
    if C0 <= 0 or x <= 0:
        return 0.0
    if v <= 0:
        return 0.0

    if D_L <= 0.0:
        # Pure advection + decay limit.
        exponent = -lam * R * x / v
        return C0 * math.exp(exponent)

    U = v * math.sqrt(max(0.0, 1.0 + 4.0 * lam * R * D_L / (v * v)))
    exponent = (v - U) * x / (2.0 * D_L)
    # Guard against extreme negative exponents that underflow to 0.
    if exponent < -700:
        return 0.0
    return C0 * math.exp(exponent)


def seepage_velocity_m_per_day(
    K_sat_m_per_s: float,
    hydraulic_gradient: float,
    effective_porosity: float,
) -> float:
    """v_s = (K_sat * i) / n_e  [m/day]."""
    K_day = K_sat_m_per_s * 86400.0
    q = K_day * hydraulic_gradient
    return q / effective_porosity


# ---------------------------------------------------------------------------
# Governed engine class
# ---------------------------------------------------------------------------

class OgataBanksEngine(AbstractPhysicsEngine):
    """Governed Ogata-Banks 1D transport engine.

    Production execution: obtain a ``SessionScopedExecutor`` from a
    ``RunSession`` and call ``engine.run(executor, **kwargs)``.

    Direct calls (``engine._evaluate_impl(**kwargs)``) or
    ``engine.run(authorization, **kwargs)`` will be rejected.
    """

    ENGINE_NAME = ENGINE_NAME
    ENGINE_VERSION = ENGINE_VERSION
    ENGINE_DESCRIPTION = ENGINE_DESCRIPTION
    ENGINE_SCOPE_NOTES = ENGINE_SCOPE_NOTES

    def _evaluate_impl(
        self,
        C0: float,
        lam_per_day: float,
        Kd_L_per_kg: float,
        bulk_density_kg_m3: float,
        effective_porosity: float,
        K_sat_m_per_s: float,
        hydraulic_gradient: float,
        distance_m: float,
        dispersivity_method: str = "epa_ssg",
        **_: Any,
    ) -> OgataBanksResult:
        """Compute steady-state receptor concentration via Ogata-Banks.

        Parameters
        ----------
        C0 : source concentration [same unit as limit]
        lam_per_day : first-order decay coefficient [1/day]
        Kd_L_per_kg : distribution coefficient [L/kg]
        bulk_density_kg_m3 : soil dry bulk density [kg/m³]
        effective_porosity : dimensionless [-]
        K_sat_m_per_s : saturated hydraulic conductivity [m/s]
        hydraulic_gradient : dimensionless [-]
        distance_m : receptor distance [m]
        dispersivity_method : dispersivity estimation method (default "epa_ssg")
        """
        v = seepage_velocity_m_per_day(K_sat_m_per_s, hydraulic_gradient, effective_porosity)
        R = retardation_factor(Kd_L_per_kg, bulk_density_kg_m3, effective_porosity)
        alpha_L = longitudinal_dispersivity_m(distance_m, dispersivity_method)
        D_L = alpha_L * v
        C_rec = concentration_steady_state(C0, v, lam_per_day, R, distance_m, D_L)

        return OgataBanksResult(
            C0=C0,
            C_receptor_steady_state=C_rec,
            retardation_factor=R,
            longitudinal_dispersivity_m=alpha_L,
            distance_m=distance_m,
            seepage_velocity_m_per_day=v,
            K_sat_m_per_day=K_sat_m_per_s * 86400.0,
            hydraulic_gradient=hydraulic_gradient,
            lambda_per_day=lam_per_day,
            Kd_L_per_kg=Kd_L_per_kg,
            bulk_density_kg_m3=bulk_density_kg_m3,
            effective_porosity=effective_porosity,
        )


# ---------------------------------------------------------------------------
# Module-level singleton (convenience)
# ---------------------------------------------------------------------------

_engine = OgataBanksEngine()


def get_engine_instance() -> OgataBanksEngine:
    """Return the module-level singleton engine instance."""
    return _engine
