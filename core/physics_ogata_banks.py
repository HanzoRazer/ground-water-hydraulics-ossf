"""
physics_ogata_banks.py
======================

One-dimensional advection-dispersion transport with linear-equilibrium
retardation and first-order decay. Continuous source, semi-infinite domain.

Governing equation:

    R * dc/dt = D_L * d2c/dx2 - v * dc/dx - lambda * R * c

with initial condition c(x, 0) = 0 and boundary conditions
c(0, t) = c0, c(inf, t) = 0.

Analytical solution (Van Genuchten & Alves 1982, solution A1;
Bear 1972 Ch. 10; original steady-state form due to Ogata & Banks 1961):

    c(x, t) / c0 = (1/2) * [
        exp( (v - U) x / (2 D_L) ) * erfc( (R x - U t) / (2 sqrt(D_L R t)) )
      + exp( (v + U) x / (2 D_L) ) * erfc( (R x + U t) / (2 sqrt(D_L R t)) )
    ]

where U = v * sqrt(1 + 4 lambda R D_L / v^2).

Steady-state form (t -> inf):

    c_ss(x) / c0 = exp( (v - U) x / (2 D_L) )

For the OSSF screening use case, the steady-state form is what a reviewer
should evaluate: it represents the worst-case concentration at the receptor
after a long-running continuous source. This is the number that appears in
the report.

Sanity limits (verified by tests/test_physics_ogata_banks.py):

  * lambda -> 0:  Ogata-Banks steady-state -> c0 (conservative tracer,
    concentration at receptor equals source concentration).

  * D_L -> 0:  U -> v, and (v - U) x / (2 D_L) -> -lambda R x / v, giving
    c_ss / c0 -> exp(-lambda R x / v), which is the pure-advection-with-
    decay result. This is the non-negotiable smoke test for correctness.

  * lambda large:  U >> v, exponent is large negative, c_ss -> 0.

Reference:
    Van Genuchten, M.Th. and Alves, W.J. (1982). Analytical solutions of
    the one-dimensional convective-dispersive solute transport equation.
    USDA Technical Bulletin 1661. Solution A1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .governance import methodology_attested
from .authorization import (
    AuthorizationError,
    ScreeningAuthorization,
    validate_authorization,
)
from .contracts.site_case_v1 import SiteCaseV1


ENGINE_NAME = "ogata_banks_1d"
ENGINE_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Dispersivity estimation
# ---------------------------------------------------------------------------

def longitudinal_dispersivity_m(distance_m: float, method: str = "epa_ssg") -> float:
    """Estimate longitudinal dispersivity (m) as a function of transport
    distance.

    * ``epa_ssg``   — alpha_L = 0.1 * L. EPA Soil Screening Guidance (1996)
                       Part 5, screening default. Simple, conservative.
    * ``xu_eckstein`` — alpha_L = 0.83 * (log10(L))^2.414. Empirical fit
                       from Xu & Eckstein (1995) to a large field dataset.
                       Better calibrated for L on the order of 10-1000 m.
    """
    if distance_m <= 0:
        return 0.0
    if method == "epa_ssg":
        return 0.1 * distance_m
    if method == "xu_eckstein":
        log_l = math.log10(distance_m)
        if log_l <= 0:
            return 0.0
        return 0.83 * (log_l ** 2.414)
    raise ValueError(f"Unknown dispersivity method: {method!r}")


# ---------------------------------------------------------------------------
# Core solutions
#
# NON-PRODUCTION PRIMITIVES. The functions in this section
# (``concentration_steady_state``, ``concentration_at_time``,
# ``longitudinal_dispersivity_m``, ``_U``) are ungoverned pure-math kernels
# exposed for characterization testing. They perform NO authorization check.
# Production screening must go through the governed ``evaluate`` entry point
# (below) via ``physics_registry.run_authorized_engine`` — do not wire these
# primitives into a production execution path.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OgataBanksResult:
    C0: float
    C_receptor_steady_state: float
    C_receptor_at_time: float
    time_evaluated_days: float
    distance_m: float
    seepage_velocity_m_per_day: float
    retardation_factor: float
    dispersivity_m: float
    dispersion_coeff_m2_per_day: float
    U_m_per_day: float           # composite velocity term
    lambda_per_day: float


def _U(v_m_per_day: float, lam_per_day: float, R: float,
       D_L_m2_per_day: float) -> float:
    if v_m_per_day <= 0:
        return 0.0
    radicand = 1.0 + (4.0 * lam_per_day * R * D_L_m2_per_day) / (v_m_per_day ** 2)
    if radicand < 0.0:
        # Physically valid inputs (lambda >= 0, R >= 1, D_L >= 0) always give
        # radicand >= 1. A negative radicand means an invalid parameter (most
        # commonly a negative decay constant) reached the kernel; fail loudly
        # rather than raising an opaque math-domain error from sqrt().
        raise ValueError(
            "Invalid transport parameters produced a negative radicand in U "
            f"(v={v_m_per_day}, lambda={lam_per_day}, R={R}, D_L={D_L_m2_per_day}); "
            "check that lambda_per_day >= 0."
        )
    return v_m_per_day * math.sqrt(radicand)


def concentration_steady_state(
    C0: float, v_m_per_day: float, R: float, D_L_m2_per_day: float,
    lam_per_day: float, distance_m: float,
) -> float:
    """Steady-state concentration at ``distance_m``. This is the value used
    in the screening report because it represents the worst-case long-run
    receptor concentration under a continuous source."""
    if C0 <= 0 or distance_m <= 0:
        return C0
    if v_m_per_day <= 0:
        return 0.0
    U = _U(v_m_per_day, lam_per_day, R, D_L_m2_per_day)
    if D_L_m2_per_day <= 0:
        # Pure advection with decay limit
        return C0 * math.exp(-lam_per_day * R * distance_m / v_m_per_day)
    exponent = (v_m_per_day - U) * distance_m / (2.0 * D_L_m2_per_day)
    return C0 * math.exp(exponent)


def concentration_at_time(
    C0: float, v_m_per_day: float, R: float, D_L_m2_per_day: float,
    lam_per_day: float, distance_m: float, time_days: float,
) -> float:
    """Full transient Van Genuchten & Alves (1982) A1 solution at time t."""
    if C0 <= 0 or distance_m <= 0:
        return C0
    if time_days <= 0:
        return 0.0
    if v_m_per_day <= 0:
        return 0.0
    if D_L_m2_per_day <= 0:
        # Pure advection with decay: plug-flow, arrival at t_a = Rx/v.
        t_arrival = R * distance_m / v_m_per_day
        if time_days < t_arrival:
            return 0.0
        return C0 * math.exp(-lam_per_day * R * distance_m / v_m_per_day)
    U = _U(v_m_per_day, lam_per_day, R, D_L_m2_per_day)
    denom = 2.0 * math.sqrt(D_L_m2_per_day * R * time_days)
    arg1 = (R * distance_m - U * time_days) / denom
    arg2 = (R * distance_m + U * time_days) / denom
    exp1 = (v_m_per_day - U) * distance_m / (2.0 * D_L_m2_per_day)
    exp2 = (v_m_per_day + U) * distance_m / (2.0 * D_L_m2_per_day)
    # Guard against exp overflow when U*t >> R*x and dispersion is small:
    # the physically relevant term is exp1 * erfc(arg1); exp2 * erfc(arg2)
    # goes to zero for large exp2 because erfc(arg2) -> 0 faster.
    term1 = math.exp(exp1) * math.erfc(arg1)
    try:
        term2 = math.exp(exp2) * math.erfc(arg2)
    except OverflowError:
        term2 = 0.0
    return 0.5 * C0 * (term1 + term2)


# ---------------------------------------------------------------------------
# Engine-facing wrapper
# ---------------------------------------------------------------------------

@methodology_attested(engine_name=ENGINE_NAME, engine_version=ENGINE_VERSION)
def evaluate(
    C0: float,
    lam_per_day: float,
    Kd_L_per_kg: float,
    bulk_density_kg_m3: float,
    effective_porosity: float,
    K_sat_m_per_s: float,
    hydraulic_gradient: float,
    distance_m: float,
    time_days: float | None = None,
    dispersivity_method: str = "epa_ssg",
    *,
    authorization: ScreeningAuthorization | None = None,
    site_case: SiteCaseV1 | None = None,
) -> OgataBanksResult:
    """Full-stack evaluation: takes soil + constituent inputs, computes
    Darcy velocity, retardation, dispersivity, and returns concentrations.

    This is the P.E.-sealable production entry point, so it is governed: a
    permitting ``ScreeningAuthorization`` **and** the ``site_config`` it was
    minted from are REQUIRED, and the token's config-binding is validated
    here (not merely its presence). This closes the direct-call gap where a
    caller holding any permitting token could previously run the engine
    against a config the token was not authorized for. In normal operation
    the entry point is reached through ``physics_registry.run_authorized_engine``.
    A direct call without a valid, config-bound authorization raises
    (ADR-0001, no bypass). The pure-math functions above
    (``concentration_steady_state``, ``concentration_at_time``,
    ``longitudinal_dispersivity_m``, ``_U``) remain ungoverned and directly
    callable for characterization tests.

    If ``time_days`` is None, only the steady-state concentration is
    populated (transient uses 100 * advective travel time as a proxy for
    steady state so the reported ``C_receptor_at_time`` is comparable).
    """
    if not isinstance(authorization, ScreeningAuthorization):
        raise AuthorizationError(
            "Physics engine invoked without a ScreeningAuthorization. The "
            "engine only runs on sites authorized through the preflight -> "
            "authorize_screening -> run_authorized_engine path (ADR-0001)."
        )
    if site_case is None:
        raise AuthorizationError(
            "evaluate() requires the SiteCaseV1 the authorization was minted "
            "from so config-binding can be verified. Route production "
            "screening through physics_registry.run_authorized_engine "
            "(ADR-0001, no bypass)."
        )
    # Full config-binding + tamper + disposition check (not just presence).
    validate_authorization(authorization, site_case)

    if lam_per_day < 0:
        raise ValueError(f"lam_per_day (decay constant) must be >= 0; got {lam_per_day}")
    if effective_porosity <= 0:
        raise ValueError("effective_porosity must be positive.")

    # Seepage velocity (m/day)
    SECONDS_PER_DAY = 86400.0
    q = K_sat_m_per_s * hydraulic_gradient           # m/s
    v_m_per_s = q / effective_porosity
    v_m_per_day = v_m_per_s * SECONDS_PER_DAY

    # Retardation factor
    R = 1.0 + (bulk_density_kg_m3 * Kd_L_per_kg * 1e-3) / effective_porosity

    # Longitudinal dispersivity and dispersion coefficient
    alpha_L = longitudinal_dispersivity_m(distance_m, method=dispersivity_method)
    D_L = alpha_L * v_m_per_day                      # m^2/day

    # Steady-state
    C_ss = concentration_steady_state(
        C0, v_m_per_day, R, D_L, lam_per_day, distance_m,
    )

    # Time-resolved (if requested)
    if time_days is None:
        if v_m_per_day > 0:
            t_probe = 100.0 * R * distance_m / v_m_per_day
        else:
            t_probe = 0.0
    else:
        t_probe = time_days
    C_t = concentration_at_time(
        C0, v_m_per_day, R, D_L, lam_per_day, distance_m, t_probe,
    )

    return OgataBanksResult(
        C0=C0,
        C_receptor_steady_state=C_ss,
        C_receptor_at_time=C_t,
        time_evaluated_days=t_probe,
        distance_m=distance_m,
        seepage_velocity_m_per_day=v_m_per_day,
        retardation_factor=R,
        dispersivity_m=alpha_L,
        dispersion_coeff_m2_per_day=D_L,
        U_m_per_day=_U(v_m_per_day, lam_per_day, R, D_L),
        lambda_per_day=lam_per_day,
    )
