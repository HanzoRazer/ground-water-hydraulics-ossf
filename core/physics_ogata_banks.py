"""core/physics_ogata_banks.py — Ogata-Banks 1D advection-dispersion engine.

Implements the Ogata-Banks (1961) analytical solution for transient,
one-dimensional, steady-state-flow advection-dispersion transport in a
homogeneous, saturated porous medium with a continuous step-input source.

This module registers the engine as a singleton (``OGATA_BANKS_1D``) so it
is available immediately on import via::

    from core.physics_ogata_banks import OGATA_BANKS_1D  # noqa: F401
    # or simply import the module; registration happens at module scope.

Physics
-------
Ogata & Banks (1961) solution for 1-D advection-dispersion without decay:

    C(x, t) = C0/2 * { erfc[(x - v*t) / (2*sqrt(D*t))]
                      + exp(v*x/D) * erfc[(x + v*t) / (2*sqrt(D*t))] }

Parameters:

    x   = distance from continuous source [m]
    t   = elapsed time [days]
    v   = average linear (pore-water) velocity [m/day]
    D   = hydrodynamic dispersion coefficient [m²/day]
          (often written as alpha_L * v, where alpha_L is longitudinal
          dispersivity [m]; the caller may supply D directly or derive it
          from alpha_L)
    C0  = source (influent) concentration [any consistent unit]

Scope / limitations
-------------------
* 1-D, steady-state flow field (v is constant in space and time).
* Homogeneous, isotropic medium.
* Linear-equilibrium sorption can be incorporated by replacing v with
  v/R and D with D/R, where R is the retardation factor.
* No first-order decay; for decay, use the retarded-travel-time model in
  ``core/transport.py`` or extend this engine.
* Requires t > 0 and D > 0.

References
----------
Ogata, A. & Banks, R.B. (1961). *A solution of the differential equation
    of longitudinal dispersion in porous media.* USGS Professional Paper
    411-A. USGS, Reston, VA.
Bear, J. (1972). *Dynamics of Fluids in Porous Media.* Elsevier.
Fetter, C.W. (1999). *Contaminant Hydrogeology*, 2nd ed. Prentice Hall.

Versioning
----------
ENGINE_NAME    = "ogata_banks_1d"
ENGINE_VERSION = "1.0.0"

A version bump is required whenever the numerical output changes for the
same inputs (physics change → MAJOR; parameter addition with default →
MINOR; documentation only → PATCH).
"""

from __future__ import annotations

import math
from typing import Any

from core.physics_registry import AbstractPhysicsEngine, register_engine


class OgataBanks1D(AbstractPhysicsEngine):
    """Ogata-Banks 1D advection-dispersion engine.

    Implements the Ogata-Banks (1961) analytical solution.  See the module
    docstring for the equation, parameter definitions, and scope notes.

    Usage
    -----
    Do **not** instantiate or call this class directly in application code.
    Use :func:`~core.physics_registry.run_authorized_engine` instead::

        from core.governance import Authorization
        from core.physics_registry import run_authorized_engine

        auth = Authorization(authorization_id="run-001", disposition="permitted")
        result = run_authorized_engine(
            "ogata_banks_1d",
            auth,
            x_m=30.0,
            t_days=365.0,
            v_m_per_day=0.1,
            D_m2_per_day=0.01,
            C0=1.0,
        )
    """

    ENGINE_NAME: str = "ogata_banks_1d"
    ENGINE_VERSION: str = "1.0.0"

    # ------------------------------------------------------------------
    # AbstractPhysicsEngine property implementations
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.ENGINE_NAME

    @property
    def version(self) -> str:
        return self.ENGINE_VERSION

    @property
    def scope_notes(self) -> str:
        return (
            "1-D, steady-state-flow, saturated-zone advection-dispersion. "
            "Homogeneous medium; no first-order decay. "
            "Valid for t > 0, D > 0, v > 0. "
            "For retarded transport multiply caller-supplied v and D by 1/R "
            "where R is the retardation factor before calling."
        )

    @property
    def description(self) -> str:
        return (
            "Ogata-Banks (1961) analytical solution for 1-D "
            "advection-dispersion in saturated porous media."
        )

    # ------------------------------------------------------------------
    # Physics implementation
    # ------------------------------------------------------------------

    def _evaluate_impl(
        self,
        *,
        x_m: float,
        t_days: float,
        v_m_per_day: float,
        D_m2_per_day: float,
        C0: float,
    ) -> float:
        """Compute receptor concentration using the Ogata-Banks solution.

        Parameters
        ----------
        x_m:
            Distance from the continuous source [m, > 0].
        t_days:
            Elapsed time since source onset [days, > 0].
        v_m_per_day:
            Average linear (pore-water) velocity [m/day, > 0].
        D_m2_per_day:
            Hydrodynamic dispersion coefficient [m²/day, > 0].
            Equals alpha_L * v_m_per_day where alpha_L is longitudinal
            dispersivity [m].
        C0:
            Continuous-source concentration [any unit, >= 0].

        Returns
        -------
        float
            Predicted receptor concentration C(x, t) [same unit as C0].

        Raises
        ------
        ValueError
            If any of *x_m*, *t_days*, *v_m_per_day*, *D_m2_per_day* is
            not positive, or if *C0* is negative.

        Notes
        -----
        The second complementary-error-function term (``exp(v*x/D) * erfc(...)``)
        can produce numerical overflow when ``v*x/D`` is very large.  The
        implementation caps the exponent: when ``v*x/D > 700`` the exp term
        dominates and its product with the vanishingly small erfc argument is
        treated as zero (both factors are evaluated to avoid 0 * inf NaN).
        """
        if x_m <= 0:
            raise ValueError(f"x_m must be positive; got {x_m}")
        if t_days <= 0:
            raise ValueError(f"t_days must be positive; got {t_days}")
        if v_m_per_day <= 0:
            raise ValueError(f"v_m_per_day must be positive; got {v_m_per_day}")
        if D_m2_per_day <= 0:
            raise ValueError(f"D_m2_per_day must be positive; got {D_m2_per_day}")
        if C0 < 0:
            raise ValueError(f"C0 must be >= 0; got {C0}")

        v = v_m_per_day
        D = D_m2_per_day
        x = x_m
        t = t_days

        sqrt_Dt = math.sqrt(D * t)
        two_sqrt_Dt = 2.0 * sqrt_Dt

        # First term: erfc[(x - v*t) / (2*sqrt(D*t))]
        arg1 = (x - v * t) / two_sqrt_Dt
        term1 = math.erfc(arg1)

        # Second term: exp(v*x/D) * erfc[(x + v*t) / (2*sqrt(D*t))]
        exp_exponent = v * x / D
        arg2 = (x + v * t) / two_sqrt_Dt
        erfc2 = math.erfc(arg2)

        if exp_exponent > 700.0:
            # exp() would overflow; erfc2 is vanishingly small at large arg2.
            # The product exp(large) * erfc(large) → 0 via scaled erfc.
            # Use erfcx (scaled erfc) approximation: erfcx(z) ≈ 1/(z*sqrt(pi))
            # so exp(vx/D) * erfc(arg2) = exp(vx/D - arg2^2) * erfcx(arg2)
            # Note: arg2^2 = (x + v*t)^2 / (4*D*t)
            exponent_adjusted = exp_exponent - arg2 * arg2
            if exponent_adjusted > 700.0:
                term2 = 0.0
            else:
                # erfcx(z) ≈ 1/(z * sqrt(pi)) for large z
                erfcx2 = 1.0 / (arg2 * math.sqrt(math.pi)) if arg2 > 0 else erfc2
                term2 = math.exp(exponent_adjusted) * erfcx2
        else:
            term2 = math.exp(exp_exponent) * erfc2

        return (C0 / 2.0) * (term1 + term2)


# ---------------------------------------------------------------------------
# Module-level singleton and registration
# ---------------------------------------------------------------------------

OGATA_BANKS_1D: OgataBanks1D = OgataBanks1D()
"""Module-level singleton instance of :class:`OgataBanks1D`.

Registered in the global engine registry at module import time.
Reference this name only if you need metadata inspection; for execution
use :func:`~core.physics_registry.run_authorized_engine`.
"""

register_engine(OGATA_BANKS_1D)
