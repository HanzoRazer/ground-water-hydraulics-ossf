"""tests/test_physics_ogata_banks.py — Characterization tests for OgataBanks1D.

These tests lock in the numerical output of the Ogata-Banks 1D engine so
that any future refactor that inadvertently changes the physics is caught
immediately.  The expected values were computed from the same implementation
on first acceptance and are treated as the ground truth for this engine
version (1.0.0).

The tests also exercise the full authorized execution path via
``run_authorized_engine``, confirming that the authorization gate does not
alter the numerical result.

Reference: Ogata, A. & Banks, R.B. (1961). USGS Professional Paper 411-A.
"""

from __future__ import annotations

import math

import pytest

# Trigger registration of the Ogata-Banks engine.
import core.physics_ogata_banks  # noqa: F401
from core.governance import Authorization, AuthorizationError
from core.physics_ogata_banks import OGATA_BANKS_1D, OgataBanks1D
from core.physics_registry import EngineMetadata, get_engine, run_authorized_engine

# A valid authorization used throughout characterization tests.
_AUTH = Authorization(authorization_id="char-test-001", disposition="permitted")

# ---------------------------------------------------------------------------
# Registration smoke-test
# ---------------------------------------------------------------------------


def test_engine_is_registered():
    meta = get_engine("ogata_banks_1d")
    assert isinstance(meta, EngineMetadata)
    assert meta.name == "ogata_banks_1d"
    assert meta.version == "1.0.0"


def test_singleton_is_ogata_banks_1d_instance():
    assert isinstance(OGATA_BANKS_1D, OgataBanks1D)


# ---------------------------------------------------------------------------
# Characterization: hand-computable reference cases
# ---------------------------------------------------------------------------


def _ogata_banks_reference(x, t, v, D, C0):
    """Pure-Python reference implementation for cross-checking.

    Implements the same formula as OgataBanks1D._evaluate_impl but written
    independently for test cross-checking.
    """
    sqrt_Dt = math.sqrt(D * t)
    two_sqrt_Dt = 2.0 * sqrt_Dt
    arg1 = (x - v * t) / two_sqrt_Dt
    arg2 = (x + v * t) / two_sqrt_Dt
    exp_exp = v * x / D
    term1 = math.erfc(arg1)
    if exp_exp > 700.0:
        exponent_adjusted = exp_exp - arg2 ** 2
        if exponent_adjusted > 700.0:
            term2 = 0.0
        else:
            erfcx2 = 1.0 / (arg2 * math.sqrt(math.pi)) if arg2 > 0 else math.erfc(arg2)
            term2 = math.exp(exponent_adjusted) * erfcx2
    else:
        term2 = math.exp(exp_exp) * math.erfc(arg2)
    return (C0 / 2.0) * (term1 + term2)


@pytest.mark.parametrize(
    "x_m, t_days, v_m_per_day, D_m2_per_day, C0, description",
    [
        # Concentration front has barely arrived: C ≈ small fraction of C0
        (30.0, 100.0, 0.1, 0.5, 1.0, "front not yet arrived"),
        # Concentration front at x: t = x/v, C ≈ C0/2 for small D
        (30.0, 300.0, 0.1, 0.5, 1.0, "front at receptor"),
        # Long time: C approaches C0 (breakthrough complete)
        (30.0, 1000.0, 0.1, 0.5, 1.0, "breakthrough complete"),
        # High dispersion: earlier breakthrough
        (30.0, 100.0, 0.1, 5.0, 1.0, "high dispersion"),
        # Non-unit C0
        (20.0, 200.0, 0.1, 1.0, 100.0, "nonunit C0"),
        # Low velocity
        (10.0, 365.0, 0.05, 0.1, 50.0, "low velocity"),
        # Short distance
        (5.0, 50.0, 0.2, 0.5, 1.0, "short distance"),
    ],
)
def test_characterization_matches_reference(
    x_m, t_days, v_m_per_day, D_m2_per_day, C0, description
):
    """Numerical output must match the reference implementation bit-for-bit."""
    expected = _ogata_banks_reference(x_m, t_days, v_m_per_day, D_m2_per_day, C0)
    actual = run_authorized_engine(
        "ogata_banks_1d",
        _AUTH,
        x_m=x_m,
        t_days=t_days,
        v_m_per_day=v_m_per_day,
        D_m2_per_day=D_m2_per_day,
        C0=C0,
    )
    assert actual == pytest.approx(expected, rel=1e-12), (
        f"Mismatch for case {description!r}: got {actual}, expected {expected}"
    )


def test_concentration_bounded_by_c0():
    """C(x, t) must always be in [0, C0]."""
    for x in [5.0, 15.0, 50.0]:
        for t in [50.0, 200.0, 1000.0]:
            result = run_authorized_engine(
                "ogata_banks_1d",
                _AUTH,
                x_m=x,
                t_days=t,
                v_m_per_day=0.1,
                D_m2_per_day=0.5,
                C0=1.0,
            )
            assert 0.0 <= result <= 1.0, (
                f"Out-of-bounds concentration {result} for x={x}, t={t}"
            )


def test_zero_c0_gives_zero():
    """Zero source concentration must give zero receptor concentration."""
    result = run_authorized_engine(
        "ogata_banks_1d",
        _AUTH,
        x_m=20.0,
        t_days=200.0,
        v_m_per_day=0.1,
        D_m2_per_day=1.0,
        C0=0.0,
    )
    assert result == 0.0


def test_monotone_with_time():
    """C(x, t) must be non-decreasing in time for a step input."""
    prev = 0.0
    for t in [50.0, 100.0, 200.0, 500.0, 1000.0]:
        c = run_authorized_engine(
            "ogata_banks_1d",
            _AUTH,
            x_m=20.0,
            t_days=t,
            v_m_per_day=0.1,
            D_m2_per_day=0.5,
            C0=1.0,
        )
        assert c >= prev - 1e-12, (
            f"Non-monotone: C({t}) = {c} < C({t - 1}) = {prev}"
        )
        prev = c


def test_monotone_decreasing_with_distance():
    """C(x, t) must be non-increasing in distance at a fixed time."""
    prev = 1.0
    for x in [5.0, 10.0, 20.0, 40.0, 80.0]:
        c = run_authorized_engine(
            "ogata_banks_1d",
            _AUTH,
            x_m=x,
            t_days=500.0,
            v_m_per_day=0.1,
            D_m2_per_day=0.5,
            C0=1.0,
        )
        assert c <= prev + 1e-12, (
            f"Non-monotone: C({x}) = {c} > C({x - 1}) = {prev}"
        )
        prev = c


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, description",
    [
        (dict(x_m=-1.0, t_days=100.0, v_m_per_day=0.1, D_m2_per_day=0.5, C0=1.0), "negative x"),
        (dict(x_m=0.0, t_days=100.0, v_m_per_day=0.1, D_m2_per_day=0.5, C0=1.0), "zero x"),
        (dict(x_m=10.0, t_days=-1.0, v_m_per_day=0.1, D_m2_per_day=0.5, C0=1.0), "negative t"),
        (dict(x_m=10.0, t_days=0.0, v_m_per_day=0.1, D_m2_per_day=0.5, C0=1.0), "zero t"),
        (dict(x_m=10.0, t_days=100.0, v_m_per_day=-0.1, D_m2_per_day=0.5, C0=1.0), "negative v"),
        (dict(x_m=10.0, t_days=100.0, v_m_per_day=0.0, D_m2_per_day=0.5, C0=1.0), "zero v"),
        (dict(x_m=10.0, t_days=100.0, v_m_per_day=0.1, D_m2_per_day=-0.5, C0=1.0), "negative D"),
        (dict(x_m=10.0, t_days=100.0, v_m_per_day=0.1, D_m2_per_day=0.0, C0=1.0), "zero D"),
        (dict(x_m=10.0, t_days=100.0, v_m_per_day=0.1, D_m2_per_day=0.5, C0=-1.0), "negative C0"),
    ],
)
def test_invalid_inputs_raise_value_error(kwargs, description):
    """Out-of-range inputs must raise ValueError from _evaluate_impl."""
    auth = Authorization(authorization_id="val-test-001", disposition="permitted")
    with pytest.raises(ValueError):
        run_authorized_engine("ogata_banks_1d", auth, **kwargs)


# ---------------------------------------------------------------------------
# Numerical robustness: large Peclet number (overflow guard)
# ---------------------------------------------------------------------------


def test_large_peclet_number_does_not_overflow():
    """Large v*x/D must not raise OverflowError or produce NaN/inf."""
    # v*x/D = 10 * 1000 / 0.01 = 1_000_000 >> 700 (overflow threshold)
    result = run_authorized_engine(
        "ogata_banks_1d",
        _AUTH,
        x_m=1000.0,
        t_days=365.0,
        v_m_per_day=10.0,
        D_m2_per_day=0.01,
        C0=1.0,
    )
    assert math.isfinite(result), f"Expected finite result, got {result}"
    assert 0.0 <= result <= 1.0, f"Expected result in [0, 1], got {result}"
