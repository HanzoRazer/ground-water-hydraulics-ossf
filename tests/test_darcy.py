"""Tests for darcy.py — Darcy's Law calculations."""

import pytest
from core.darcy import (
    darcy_flux,
    seepage_velocity,
    evaluate_flow,
    cm_per_hr_to_m_per_s,
    m_per_s_to_cm_per_hr,
    FlowResult,
)


class TestDarcyFlux:
    def test_basic_calculation(self):
        K = 1e-6
        i = 0.01
        assert darcy_flux(K, i) == pytest.approx(1e-8)

    def test_zero_gradient(self):
        assert darcy_flux(1e-5, 0.0) == 0.0

    def test_negative_K_raises(self):
        with pytest.raises(ValueError, match="K_sat must be non-negative"):
            darcy_flux(-1e-6, 0.01)

    def test_negative_gradient_raises(self):
        with pytest.raises(ValueError, match="gradient magnitude must be non-negative"):
            darcy_flux(1e-6, -0.01)


class TestSeepageVelocity:
    def test_basic_calculation(self):
        K = 1e-6
        i = 0.01
        n = 0.1
        expected = (K * i) / n
        assert seepage_velocity(K, i, n) == pytest.approx(expected)

    def test_invalid_porosity_zero(self):
        with pytest.raises(ValueError, match="effective_porosity must be in"):
            seepage_velocity(1e-6, 0.01, 0.0)

    def test_invalid_porosity_over_one(self):
        with pytest.raises(ValueError, match="effective_porosity must be in"):
            seepage_velocity(1e-6, 0.01, 1.5)


class TestEvaluateFlow:
    def test_returns_flow_result(self):
        result = evaluate_flow(K_sat=1e-6, gradient=0.01, effective_porosity=0.1)
        assert isinstance(result, FlowResult)
        assert result.K_sat_m_per_s == 1e-6
        assert result.gradient == 0.01
        assert result.effective_porosity == 0.1

    def test_travel_time_calculation(self):
        result = evaluate_flow(K_sat=1e-6, gradient=0.01, effective_porosity=0.1)
        v_m_s = result.seepage_velocity_m_per_s
        distance = 100.0
        expected_seconds = distance / v_m_s
        assert result.travel_time_seconds(distance) == pytest.approx(expected_seconds)

    def test_travel_time_days(self):
        result = evaluate_flow(K_sat=1e-6, gradient=0.01, effective_porosity=0.1)
        days = result.travel_time_days(100.0)
        assert days == pytest.approx(result.travel_time_seconds(100.0) / 86400.0)


class TestUnitConversions:
    def test_cm_per_hr_to_m_per_s(self):
        assert cm_per_hr_to_m_per_s(3600.0) == pytest.approx(0.01)

    def test_m_per_s_to_cm_per_hr(self):
        assert m_per_s_to_cm_per_hr(0.01) == pytest.approx(3600.0)

    def test_round_trip(self):
        original = 0.26
        converted = m_per_s_to_cm_per_hr(cm_per_hr_to_m_per_s(original))
        assert converted == pytest.approx(original)
