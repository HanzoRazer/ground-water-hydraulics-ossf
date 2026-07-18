"""
test_physics_ogata_banks.py
===========================

Characterization tests for the Ogata-Banks physics engine.

These are the NON-NEGOTIABLE smoke tests. If any fail, the physics engine
must not be used to produce P.E.-sealed output. This is the code-side
counterpart of the sanity-limits paragraph in the module docstring.

Run: python -m pytest tests/test_physics_ogata_banks.py -v
Or standalone: python tests/test_physics_ogata_banks.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

# Allow standalone execution: add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import evidence_result_for, make_case, readiness_result_for
from core.physics_ogata_banks import (
    concentration_steady_state,
    concentration_at_time,
    longitudinal_dispersivity_m,
    _U,
    evaluate,
)
from core.preflight import RuleFinding, SiteAppropriatenessDetermination
from core.authorization import authorize_screening


# The exact validated case the test authorization is minted from. The governed
# ``evaluate`` entry point validates config-binding, so this same case must be
# passed as ``site_case`` when calling ``evaluate`` directly (OSSF-GW-002).
_AUTH_CASE = make_case(site_id="TEST")


def _valid_authorization():
    """Mint a permitting authorization via the governed path so the
    governed ``evaluate`` entry point can run. The physics values under
    test do not depend on the authorization; it only unlocks execution."""
    sad = SiteAppropriatenessDetermination(
        disposition="proceed",
        findings=[
            RuleFinding("SAD-001", "proceed", "Not in EARZ.", "30 TAC 285.40-42"),
        ],
    )
    ev = evidence_result_for(_AUTH_CASE)
    return authorize_screening(
        _AUTH_CASE, sad, ev, readiness_result_for(_AUTH_CASE, ev)
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def close(a: float, b: float, rel: float = 1e-6, abs_tol: float = 1e-12) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol)


# ---------------------------------------------------------------------------
# Test 1: conservative tracer (lambda = 0) reaches steady state at C = C0
# ---------------------------------------------------------------------------

def test_conservative_tracer_steady_state_is_C0():
    """With no decay and no retardation, a continuous source produces
    C = C0 at every downgradient point at steady state."""
    C = concentration_steady_state(
        C0=100.0, v_m_per_day=1.0, R=1.0, D_L_m2_per_day=1.0,
        lam_per_day=0.0, distance_m=50.0,
    )
    assert close(C, 100.0), f"Expected 100.0, got {C}"


# ---------------------------------------------------------------------------
# Test 2: low-dispersion limit reduces to pure advection with decay
# THIS IS THE FUNDAMENTAL CORRECTNESS TEST for the new engine.
# ---------------------------------------------------------------------------

def test_low_dispersion_matches_pure_advection_with_decay():
    """As D_L -> 0, Ogata-Banks steady-state must reduce to
    exp(-lambda * R * x / v). This is the boundary that lets us claim
    the new engine is a strict generalization of the old one."""
    C0 = 100.0
    v = 1.0            # m/day
    R = 2.0            # retardation
    lam = 0.1          # 1/day
    x = 10.0           # m
    # Pure-advection-with-decay expected:
    expected = C0 * math.exp(-lam * R * x / v)

    # Ogata-Banks at very small D_L should match:
    D_L_tiny = 1e-8
    got = concentration_steady_state(
        C0=C0, v_m_per_day=v, R=R, D_L_m2_per_day=D_L_tiny,
        lam_per_day=lam, distance_m=x,
    )
    assert close(got, expected, rel=1e-3), (
        f"Low-D limit failed: expected {expected}, got {got}"
    )

    # And D_L=0 should hit the exact analytical fallback:
    got_zero = concentration_steady_state(
        C0=C0, v_m_per_day=v, R=R, D_L_m2_per_day=0.0,
        lam_per_day=lam, distance_m=x,
    )
    assert close(got_zero, expected), (
        f"D_L=0 branch failed: expected {expected}, got {got_zero}"
    )


# ---------------------------------------------------------------------------
# Test 3: dispersion INCREASES receptor concentration relative to advection
# ---------------------------------------------------------------------------

def test_dispersion_increases_steady_state_vs_advection():
    """Physical intuition: dispersion lets some solute travel faster than
    the mean velocity, so at steady state the receptor concentration
    (for a decaying species) is HIGHER with dispersion than without.
    (Fast-moving mass spends less time decaying.)"""
    C0 = 100.0
    v = 1.0
    R = 1.0
    lam = 0.5
    x = 5.0

    no_disp = concentration_steady_state(C0, v, R, 0.0, lam, x)
    with_disp = concentration_steady_state(C0, v, R, 1.0, lam, x)
    assert with_disp > no_disp, (
        f"Expected dispersion to increase C_ss: no_disp={no_disp}, "
        f"with_disp={with_disp}"
    )


# ---------------------------------------------------------------------------
# Test 4: monotonic decrease with distance
# ---------------------------------------------------------------------------

def test_monotonic_decrease_with_distance():
    args = dict(C0=100.0, v_m_per_day=1.0, R=1.0, D_L_m2_per_day=0.5,
                lam_per_day=0.2)
    Cs = [concentration_steady_state(distance_m=x, **args)
          for x in [1.0, 5.0, 10.0, 50.0, 100.0]]
    assert all(Cs[i] > Cs[i+1] for i in range(len(Cs)-1)), (
        f"C_ss should decrease with distance: {Cs}"
    )


# ---------------------------------------------------------------------------
# Test 5: U composite velocity is always >= v
# ---------------------------------------------------------------------------

def test_U_geq_v():
    """U = v*sqrt(1 + 4*lambda*R*D/v^2) >= v by construction."""
    for lam, R, D in [(0.0, 1.0, 1.0), (0.1, 2.0, 0.5), (1.0, 10.0, 2.0)]:
        u = _U(1.0, lam, R, D)
        assert u >= 1.0 - 1e-12, f"U < v for lam={lam}, R={R}, D={D}: U={u}"


# ---------------------------------------------------------------------------
# Test 6: dispersivity method knobs behave as documented
# ---------------------------------------------------------------------------

def test_dispersivity_epa_ssg_is_10_percent_of_L():
    assert close(longitudinal_dispersivity_m(100.0, "epa_ssg"), 10.0)
    assert close(longitudinal_dispersivity_m(50.0, "epa_ssg"), 5.0)


def test_dispersivity_xu_eckstein_positive_for_L_gt_1():
    a = longitudinal_dispersivity_m(100.0, "xu_eckstein")
    assert a > 0
    b = longitudinal_dispersivity_m(1000.0, "xu_eckstein")
    assert b > a, "Xu-Eckstein should increase with L"


# ---------------------------------------------------------------------------
# Test 7: transient solution: at t = 0 the receptor sees C = 0
# ---------------------------------------------------------------------------

def test_transient_at_zero_time_is_zero():
    C = concentration_at_time(
        C0=100.0, v_m_per_day=1.0, R=1.0, D_L_m2_per_day=1.0,
        lam_per_day=0.1, distance_m=10.0, time_days=0.0,
    )
    assert C == 0.0, f"C(x, t=0) must be 0, got {C}"


# ---------------------------------------------------------------------------
# Test 8: transient solution converges to steady state at large t
# ---------------------------------------------------------------------------

def test_transient_converges_to_steady_state():
    args = dict(C0=100.0, v_m_per_day=1.0, R=1.0, D_L_m2_per_day=0.5,
                lam_per_day=0.1, distance_m=10.0)
    C_ss = concentration_steady_state(**args)
    C_large_t = concentration_at_time(time_days=10_000.0, **args)
    assert close(C_large_t, C_ss, rel=1e-3), (
        f"Transient did not converge to steady state: "
        f"C(large t)={C_large_t}, C_ss={C_ss}"
    )


# ---------------------------------------------------------------------------
# Test 9: full-stack evaluate() reproduces manual calc
# ---------------------------------------------------------------------------

def test_full_stack_evaluate_reproduces_hand_calc():
    """Sanity check that the wrapper wires K_sat, gradient, porosity,
    and retardation together the way the docstring says it does."""
    result = evaluate(
        C0=126.0,               # E. coli reference
        lam_per_day=0.5,
        Kd_L_per_kg=1.5,
        bulk_density_kg_m3=1390.0,
        effective_porosity=0.08,
        K_sat_m_per_s=7.22e-7,  # clay loam
        hydraulic_gradient=0.01,
        distance_m=30.5,        # 100 ft
        authorization=_valid_authorization(),
        site_case=_AUTH_CASE,
    )
    # Hand-computed values:
    # q = 7.22e-7 * 0.01 = 7.22e-9 m/s
    # v = q / 0.08 = 9.025e-8 m/s = 0.007798 m/day
    assert close(result.seepage_velocity_m_per_day, 0.007798, rel=1e-3)
    # R = 1 + 1390 * 1.5 * 1e-3 / 0.08 = 27.0625
    assert close(result.retardation_factor, 27.0625, rel=1e-4)
    # alpha_L (EPA SSG) = 0.1 * 30.5 = 3.05 m
    assert close(result.dispersivity_m, 3.05, rel=1e-6)
    # Concentration at receptor: with lambda*R*x/v = 0.5*27.0625*30.5/0.007798
    # = 52,918, the receptor concentration is functionally zero.
    assert result.C_receptor_steady_state < 1e-10


# ---------------------------------------------------------------------------
# Test 10: defensive input validation — negative decay constant
# ---------------------------------------------------------------------------

def test_negative_decay_constant_is_rejected_cleanly():
    """A negative decay constant must raise a clear ValueError, not an
    opaque math-domain error from the sqrt in _U()."""
    import pytest

    with pytest.raises(ValueError):
        evaluate(
            C0=126.0,
            lam_per_day=-1.0,
            Kd_L_per_kg=1.5,
            bulk_density_kg_m3=1390.0,
            effective_porosity=0.08,
            K_sat_m_per_s=7.22e-7,
            hydraulic_gradient=0.01,
            distance_m=30.5,
            authorization=_valid_authorization(),
            site_case=_AUTH_CASE,
        )


def test_U_rejects_negative_radicand():
    """_U() with a negative decay constant large enough to drive the
    radicand negative raises ValueError rather than crashing in sqrt."""
    import pytest

    with pytest.raises(ValueError):
        _U(v_m_per_day=1.0, lam_per_day=-10.0, R=1.0, D_L_m2_per_day=1.0)


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_conservative_tracer_steady_state_is_C0,
        test_low_dispersion_matches_pure_advection_with_decay,
        test_dispersion_increases_steady_state_vs_advection,
        test_monotonic_decrease_with_distance,
        test_U_geq_v,
        test_dispersivity_epa_ssg_is_10_percent_of_L,
        test_dispersivity_xu_eckstein_positive_for_L_gt_1,
        test_transient_at_zero_time_is_zero,
        test_transient_converges_to_steady_state,
        test_full_stack_evaluate_reproduces_hand_calc,
        test_negative_decay_constant_is_rejected_cleanly,
        test_U_rejects_negative_radicand,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed.")
    sys.exit(1 if failures else 0)
