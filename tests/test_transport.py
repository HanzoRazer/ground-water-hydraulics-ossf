"""Unit tests for core.transport — travel time, retardation, decay, policy."""

import math

import pytest

from core import transport


# --------------------------------------------------------------------------- #
# advective_travel_time
# --------------------------------------------------------------------------- #

def test_advective_travel_time_basic():
    # t = L / v_s
    assert transport.advective_travel_time(100.0, 0.05) == pytest.approx(2000.0)


def test_advective_travel_time_rejects_nonpositive():
    with pytest.raises(ValueError):
        transport.advective_travel_time(0.0, 0.05)
    with pytest.raises(ValueError):
        transport.advective_travel_time(100.0, 0.0)


# --------------------------------------------------------------------------- #
# distribution_coefficient / retardation_factor
# --------------------------------------------------------------------------- #

def test_distribution_coefficient():
    assert transport.distribution_coefficient(100.0, 0.002) == pytest.approx(0.2)


def test_distribution_coefficient_rejects_negative():
    with pytest.raises(ValueError):
        transport.distribution_coefficient(-1.0, 0.002)
    with pytest.raises(ValueError):
        transport.distribution_coefficient(1.0, -0.002)


def test_retardation_factor_basic():
    # R = 1 + (rho_b / n_e) * K_d = 1 + (1.5/0.3)*2 = 11
    assert transport.retardation_factor(1.5, 0.3, 2.0) == pytest.approx(11.0)


def test_retardation_factor_unit_when_no_sorption():
    assert transport.retardation_factor(1.5, 0.3, 0.0) == pytest.approx(1.0)


def test_retardation_factor_rejects_bad_inputs():
    with pytest.raises(ValueError):
        transport.retardation_factor(0.0, 0.3, 2.0)
    with pytest.raises(ValueError):
        transport.retardation_factor(1.5, 0.0, 2.0)
    with pytest.raises(ValueError):
        transport.retardation_factor(1.5, 1.5, 2.0)


# --------------------------------------------------------------------------- #
# retarded_travel_time (newly hardened)
# --------------------------------------------------------------------------- #

def test_retarded_travel_time_basic():
    assert transport.retarded_travel_time(2000.0, 11.0) == pytest.approx(22000.0)


def test_retarded_travel_time_rejects_negative_time():
    with pytest.raises(ValueError):
        transport.retarded_travel_time(-1.0, 2.0)


def test_retarded_travel_time_rejects_R_below_one():
    with pytest.raises(ValueError):
        transport.retarded_travel_time(2000.0, 0.5)


# --------------------------------------------------------------------------- #
# attenuation_factor — overflow / underflow behavior
# --------------------------------------------------------------------------- #

def test_attenuation_factor_known_value():
    assert transport.attenuation_factor(0.1, 10.0) == pytest.approx(math.exp(-1.0))


def test_attenuation_factor_zero_time_is_one():
    assert transport.attenuation_factor(0.5, 0.0) == 1.0


def test_attenuation_factor_zero_decay_is_one():
    assert transport.attenuation_factor(0.0, 1e9) == 1.0


def test_attenuation_factor_underflow_clamps_to_zero():
    # exponent > 700 -> clamps to exact 0.0 (documented computational floor)
    assert transport.attenuation_factor(1.0, 1000.0) == 0.0


def test_attenuation_factor_rejects_negative():
    with pytest.raises(ValueError):
        transport.attenuation_factor(-0.1, 10.0)
    with pytest.raises(ValueError):
        transport.attenuation_factor(0.1, -10.0)


# --------------------------------------------------------------------------- #
# receptor_concentration
# --------------------------------------------------------------------------- #

def test_receptor_concentration_basic():
    c = transport.receptor_concentration(100.0, 0.1, 10.0)
    assert c == pytest.approx(100.0 * math.exp(-1.0))


def test_receptor_concentration_rejects_negative_C0():
    with pytest.raises(ValueError):
        transport.receptor_concentration(-1.0, 0.1, 10.0)


# --------------------------------------------------------------------------- #
# log_removal + passes_screening (the non-detect policy)
# --------------------------------------------------------------------------- #

def test_log_removal_finite():
    assert transport.log_removal(100.0, 0.01) == pytest.approx(4.0)


def test_log_removal_underflow_is_inf():
    assert transport.log_removal(100.0, 0.0) == math.inf


def test_log_removal_nonpositive_C0_is_zero():
    assert transport.log_removal(0.0, 0.0) == 0.0


def test_passes_numeric_limit():
    assert transport.passes_screening(5.0, 10.0, 40.0) is True
    assert transport.passes_screening(15.0, 10.0, 40.0) is False
    # exactly at the limit passes
    assert transport.passes_screening(10.0, 10.0, 40.0) is True


def test_passes_nondetect_meets_target():
    # C0=100, C_rec=0.001 -> 5-log removal >= 4-log target -> pass
    assert transport.passes_screening(1e-3, 0.0, 100.0) is True


def test_passes_nondetect_below_target_fails():
    # C0=100, C_rec=0.1 -> 3-log removal < 4-log target -> fail
    assert transport.passes_screening(0.1, 0.0, 100.0) is False


def test_passes_nondetect_underflow_passes():
    # C_rec underflowed to exact 0 -> inf log removal -> pass, but this is a
    # computational floor, not a measured absence (reporting makes that clear).
    assert transport.passes_screening(0.0, 0.0, 100.0) is True


def test_passes_nondetect_respects_custom_target():
    # 3-log achieved; a 2-log target passes, a 4-log target fails
    assert transport.passes_screening(0.1, 0.0, 100.0, nondetect_log_removal_target=2.0) is True
    assert transport.passes_screening(0.1, 0.0, 100.0, nondetect_log_removal_target=4.0) is False
