"""
Darcy flux and seepage velocity calculations.

Theory
------
Darcy's Law (1856):

    q = K * i                       [m/day]

where
    K  = saturated hydraulic conductivity [m/day]
    i  = hydraulic gradient (dh/dL)       [dimensionless]
    q  = Darcy flux (specific discharge)  [m/day]

Average linear (seepage) velocity:

    v_s = q / n_e                   [m/day]

where
    n_e = effective (drainable) porosity  [dimensionless]

References
----------
Darcy, H. (1856). *Les fontaines publiques de la ville de Dijon.*
Bear, J. (1972). *Dynamics of Fluids in Porous Media.* Elsevier.
Freeze, R.A. & Cherry, J.A. (1979). *Groundwater.* Prentice Hall.
"""


def darcy_flux(K_m_per_day: float, gradient: float) -> float:
    """Compute Darcy flux (specific discharge).

    Parameters
    ----------
    K_m_per_day:
        Saturated hydraulic conductivity [m/day].
    gradient:
        Hydraulic gradient dh/dL [dimensionless, > 0].

    Returns
    -------
    float
        Darcy flux *q* [m/day].

    Raises
    ------
    ValueError
        If *K_m_per_day* or *gradient* is not positive.
    """
    if K_m_per_day <= 0:
        raise ValueError(
            f"Hydraulic conductivity must be positive; got {K_m_per_day}"
        )
    if gradient <= 0:
        raise ValueError(
            f"Hydraulic gradient must be positive; got {gradient}"
        )
    return K_m_per_day * gradient


def seepage_velocity(q: float, n_e: float) -> float:
    """Compute average linear (seepage) velocity.

    Parameters
    ----------
    q:
        Darcy flux [m/day].
    n_e:
        Effective (drainable) porosity [dimensionless, 0 < n_e <= 1].

    Returns
    -------
    float
        Seepage velocity *v_s* [m/day].

    Raises
    ------
    ValueError
        If *n_e* is not in (0, 1].
    """
    if not (0 < n_e <= 1):
        raise ValueError(
            f"Effective porosity must be in (0, 1]; got {n_e}"
        )
    return q / n_e
