"""
Solute transport calculations: travel time, retardation, first-order decay.

Theory
------
Advective travel time (unretarded):

    t_adv = L / v_s                 [days]

where
    L   = flow-path length to receptor   [m]
    v_s = seepage velocity               [m/day]

Linear sorption distribution coefficient:

    K_d = K_oc * f_oc               [mL/g  ==  cm³/g  ==  L/kg]

where
    K_oc = organic-carbon partition coefficient  [mL/g]
    f_oc = soil organic-carbon mass fraction     [g_oc / g_soil]

Linear-equilibrium retardation factor:

    R = 1 + (rho_b / n_e) * K_d    [dimensionless, >= 1]

where
    rho_b = dry bulk density         [g/cm³]
    n_e   = effective porosity       [dimensionless]

    Note: rho_b [g/cm³] and K_d [mL/g = cm³/g] share consistent
    volumetric units, so the product (rho_b / n_e) * K_d is dimensionless.

Retarded seepage velocity:

    v_r = v_s / R                   [m/day]

Retarded travel time:

    t_r = L / v_r  =  t_adv * R    [days]

First-order decay / attenuation:

    C(t) = C0 * exp(-lambda * t_r)  [same units as C0]

References
----------
Fetter, C.W. (1999). *Contaminant Hydrogeology*, 2nd ed. Prentice Hall.
USEPA (1996). *Soil Screening Guidance: Technical Background Document.*
    EPA/540/R-95/128.
Pang, L. (2009). Microbial removal rates in subsurface media estimated from
    published studies. *Journal of Environmental Quality* 38:1531–1559.
"""

import math


def advective_travel_time(distance_m: float, seepage_velocity_m_per_day: float) -> float:
    """Compute unretarded advective travel time.

    Parameters
    ----------
    distance_m:
        Flow-path length from disposal area to receptor [m].
    seepage_velocity_m_per_day:
        Average linear (seepage) velocity [m/day].

    Returns
    -------
    float
        Advective travel time [days].

    Raises
    ------
    ValueError
        If either argument is not positive.
    """
    if distance_m <= 0:
        raise ValueError(f"Distance must be positive; got {distance_m}")
    if seepage_velocity_m_per_day <= 0:
        raise ValueError(
            f"Seepage velocity must be positive; got {seepage_velocity_m_per_day}"
        )
    return distance_m / seepage_velocity_m_per_day


def distribution_coefficient(K_oc_mL_per_g: float, f_oc: float) -> float:
    """Compute linear sorption distribution coefficient K_d.

    Parameters
    ----------
    K_oc_mL_per_g:
        Organic-carbon partition coefficient [mL/g].
    f_oc:
        Soil organic-carbon mass fraction [dimensionless].

    Returns
    -------
    float
        K_d [mL/g  =  cm³/g].
    """
    if K_oc_mL_per_g < 0:
        raise ValueError(f"K_oc must be >= 0; got {K_oc_mL_per_g}")
    if f_oc < 0:
        raise ValueError(f"f_oc must be >= 0; got {f_oc}")
    return K_oc_mL_per_g * f_oc


def retardation_factor(
    rho_b_g_per_cm3: float, n_e: float, K_d_mL_per_g: float
) -> float:
    """Compute linear-equilibrium retardation factor R.

    Parameters
    ----------
    rho_b_g_per_cm3:
        Dry bulk density [g/cm³].
    n_e:
        Effective porosity [dimensionless, 0 < n_e <= 1].
    K_d_mL_per_g:
        Distribution coefficient [mL/g  =  cm³/g].

    Returns
    -------
    float
        Retardation factor R [dimensionless, >= 1.0].

    Raises
    ------
    ValueError
        If bulk density or porosity are not positive.
    """
    if rho_b_g_per_cm3 <= 0:
        raise ValueError(f"Bulk density must be positive; got {rho_b_g_per_cm3}")
    if not (0 < n_e <= 1):
        raise ValueError(f"Effective porosity must be in (0, 1]; got {n_e}")
    return 1.0 + (rho_b_g_per_cm3 / n_e) * K_d_mL_per_g


def retarded_travel_time(
    t_adv_days: float, R: float
) -> float:
    """Compute retarded travel time.

    Parameters
    ----------
    t_adv_days:
        Unretarded advective travel time [days, >= 0].
    R:
        Retardation factor [dimensionless, >= 1].

    Returns
    -------
    float
        Retarded travel time [days].

    Raises
    ------
    ValueError
        If ``t_adv_days`` is negative or ``R`` is less than 1.
    """
    if t_adv_days < 0:
        raise ValueError(f"Advective travel time must be >= 0; got {t_adv_days}")
    if R < 1.0:
        raise ValueError(f"Retardation factor must be >= 1; got {R}")
    return t_adv_days * R


def attenuation_factor(lambda_per_day: float, time_days: float) -> float:
    """Compute dimensionless first-order attenuation factor C/C0.

    C/C0 = exp(-lambda * t)

    Parameters
    ----------
    lambda_per_day:
        First-order decay / removal rate constant [1/day, >= 0].
    time_days:
        Elapsed (retarded) travel time [days, >= 0].

    Returns
    -------
    float
        Attenuation factor in [0, 1]; smaller values mean more attenuation.
    """
    if lambda_per_day < 0:
        raise ValueError(f"Decay constant must be >= 0; got {lambda_per_day}")
    if time_days < 0:
        raise ValueError(f"Travel time must be >= 0; got {time_days}")
    exponent = lambda_per_day * time_days
    if exponent > 700:
        return 0.0
    return math.exp(-exponent)


def receptor_concentration(C0: float, lambda_per_day: float, time_days: float) -> float:
    """Compute receptor concentration after first-order decay.

    Parameters
    ----------
    C0:
        Source (effluent) concentration [any consistent unit, >= 0].
    lambda_per_day:
        First-order decay constant [1/day, >= 0].
    time_days:
        Retarded travel time to receptor [days, >= 0].

    Returns
    -------
    float
        Predicted receptor concentration [same unit as C0].

    Raises
    ------
    ValueError
        If ``C0`` is negative.
    """
    if C0 < 0:
        raise ValueError(f"Source concentration C0 must be >= 0; got {C0}")
    return C0 * attenuation_factor(lambda_per_day, time_days)


# ---------------------------------------------------------------------------
# Screening pass/fail policy
# ---------------------------------------------------------------------------
#
# Two distinct kinds of regulatory limit are handled explicitly so that a
# *numerical* underflow (see ``attenuation_factor``) can never masquerade as a
# *scientific* statement of absence:
#
#   * Numeric limit (limit > 0): pass iff modeled C_receptor <= limit.
#   * Non-detect target (limit == 0.0): a modeled concentration can only reach
#     exactly zero through floating-point underflow, so an exact-zero test is
#     not defensible. Instead we require a documented log-removal target
#     (default 4-log, consistent with the USEPA GWUDI pathogen-removal
#     benchmark). Pass iff the achieved log-removal meets the target. A
#     constituent may override the default via a ``nondetect_log_removal_target``
#     field in the constituents database.

NONDETECT_LOG_REMOVAL_TARGET = 4.0


def log_removal(C0: float, C_receptor: float) -> float:
    """Return achieved log10 removal, log10(C0 / C_receptor).

    Returns ``math.inf`` when the modeled receptor concentration has
    underflowed to zero (removal is beyond the computational floor rather than
    literally complete). Returns ``0.0`` when ``C0`` is non-positive.
    """
    if C0 <= 0:
        return 0.0
    if C_receptor <= 0:
        return math.inf
    return math.log10(C0 / C_receptor)


def passes_screening(
    C_receptor: float,
    limit: float,
    C0: float,
    nondetect_log_removal_target: float = NONDETECT_LOG_REMOVAL_TARGET,
) -> bool:
    """Apply the screening pass/fail policy for one constituent.

    See the module-level policy note. For a positive limit this is a simple
    ``C_receptor <= limit`` comparison; for a non-detect target (``limit == 0``)
    it is a log-removal comparison that does not depend on exact-zero
    floating-point behavior.
    """
    if limit > 0:
        return C_receptor <= limit
    return log_removal(C0, C_receptor) >= nondetect_log_removal_target


# ---------------------------------------------------------------------------
# Physics primitives — Tier 3 (import via core.transport only)
# ---------------------------------------------------------------------------
# These are lower-level building blocks used by analytical ADE solutions.
# They are NOT re-exported from core.__init__ because:
#   * They encode engine-implementation details, not the consumer API.
#   * Future engines may replace or extend them without a MAJOR version bump.


def _U(x: float, Pe: float) -> float:
    """Exponential Péclet-number helper for 1-D ADE analytical solutions.

    Computes ``exp(Pe * x / 2)``, which appears in the Ogata–Banks (1961)
    and related closed-form solute-transport solutions.

    Tier 3 — internal physics primitive.  Import via ``core.transport`` only.

    Parameters
    ----------
    x:
        Dimensionless spatial coordinate (distance / dispersivity).
    Pe:
        Cell Péclet number (v * L / D_L).

    Returns
    -------
    float
    """
    return math.exp(Pe * x / 2.0)


def concentration_at_time(
    C0: float,
    lambda_per_day: float,
    t_days: float,
) -> float:
    """Concentration after first-order decay over elapsed retarded travel time.

    A named alias for ``receptor_concentration``, retained as a distinct
    symbol because it appears in time-series contexts where "at time t"
    is more expressive than "at receptor".

    Tier 3 — internal physics primitive.  Import via ``core.transport`` only.

    Parameters
    ----------
    C0:
        Initial (source) concentration [any consistent unit, >= 0].
    lambda_per_day:
        First-order decay constant [1/day, >= 0].
    t_days:
        Elapsed retarded travel time [days, >= 0].

    Returns
    -------
    float
        C(t) = C0 * exp(-lambda * t).
    """
    return receptor_concentration(C0, lambda_per_day, t_days)


def concentration_steady_state(
    C0: float,
    lambda_per_day: float,
    v_r_m_per_day: float,
    x_m: float,
) -> float:
    """Steady-state concentration at distance *x* under advection and decay.

    For a 1-D steady-state system with advective velocity *v_r* and
    first-order decay *lambda*:

        C(x) = C0 * exp(-(lambda / v_r) * x)

    Tier 3 — internal physics primitive.  Import via ``core.transport`` only.

    Parameters
    ----------
    C0:
        Source concentration [any consistent unit, >= 0].
    lambda_per_day:
        First-order decay constant [1/day, >= 0].
    v_r_m_per_day:
        Retarded seepage velocity [m/day, > 0].
    x_m:
        Distance from source to evaluation point [m, >= 0].

    Returns
    -------
    float
        Steady-state concentration at *x* [same unit as C0].

    Raises
    ------
    ValueError
        If *v_r_m_per_day* is not positive or *x_m* is negative.
    """
    if v_r_m_per_day <= 0:
        raise ValueError(
            f"Retarded velocity must be positive; got {v_r_m_per_day}"
        )
    if x_m < 0:
        raise ValueError(f"Distance must be non-negative; got {x_m}")
    k = lambda_per_day / v_r_m_per_day
    return C0 * math.exp(-k * x_m)
