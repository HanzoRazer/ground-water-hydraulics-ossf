"""Tests for transport.py — solute transport calculations."""

import math
import pytest
from core.darcy import evaluate_flow
from core.transport import (
    retardation_factor,
    first_order_decay,
    log_removal,
    evaluate_transport,
    TransportResult,
)


class TestRetardationFactor:
    def test_no_sorption(self):
        R = retardation_factor(bulk_density_kg_m3=1400, Kd_L_per_kg=0.0, porosity=0.1)
        assert R == 1.0

    def test_with_sorption(self):
        R = retardation_factor(bulk_density_kg_m3=1400, Kd_L_per_kg=1.0, porosity=0.1)
        expected = 1.0 + (1400 * 1.0 * 1e-3) / 0.1
        assert R == pytest.approx(expected)

    def test_zero_porosity_raises(self):
        with pytest.raises(ValueError, match="porosity must be positive"):
            retardation_factor(1400, 1.0, 0.0)

    def test_negative_Kd_raises(self):
        with pytest.raises(ValueError, match="Kd and bulk_density must be non-negative"):
            retardation_factor(1400, -1.0, 0.1)


class TestFirstOrderDecay:
    def test_no_decay(self):
        C = first_order_decay(C0=100, lambda_per_day=0.0, time_days=100)
        assert C == 100.0

    def test_half_life(self):
        lambda_d = 0.693
        C = first_order_decay(C0=100, lambda_per_day=lambda_d, time_days=1.0)
        assert C == pytest.approx(50, rel=0.01)

    def test_infinite_time_with_decay(self):
        C = first_order_decay(C0=100, lambda_per_day=0.1, time_days=float("inf"))
        assert C == 0.0

    def test_infinite_time_no_decay(self):
        C = first_order_decay(C0=100, lambda_per_day=0.0, time_days=float("inf"))
        assert C == 100.0


class TestLogRemoval:
    def test_no_removal(self):
        assert log_removal(100, 100) == 0.0

    def test_one_log_removal(self):
        assert log_removal(100, 10) == pytest.approx(1.0)

    def test_complete_removal(self):
        assert log_removal(100, 0) == float("inf")

    def test_zero_initial(self):
        assert log_removal(0, 50) == 0.0


class TestEvaluateTransport:
    @pytest.fixture
    def sample_flow(self):
        return evaluate_flow(K_sat=7.22e-7, gradient=0.01, effective_porosity=0.08)

    @pytest.fixture
    def sample_constituent(self):
        return {
            "lambda_per_day": 0.69,
            "Kd_L_per_kg": 1.0,
            "typical_C0_post_disinfection": 200,
            "C0_units": "MPN/100 mL",
            "regulatory_limit": 200,
        }

    @pytest.fixture
    def sample_soil(self):
        return {
            "bulk_density_kg_per_m3": 1390,
            "effective_porosity": 0.08,
        }

    def test_returns_transport_result(self, sample_flow, sample_constituent, sample_soil):
        result = evaluate_transport(
            constituent_name="fecal_coliform",
            constituent_props=sample_constituent,
            soil_props=sample_soil,
            flow=sample_flow,
            distance_m=30.0,
        )
        assert isinstance(result, TransportResult)
        assert result.constituent == "fecal_coliform"
        assert result.distance_m == 30.0

    def test_c0_override(self, sample_flow, sample_constituent, sample_soil):
        result = evaluate_transport(
            constituent_name="test",
            constituent_props=sample_constituent,
            soil_props=sample_soil,
            flow=sample_flow,
            distance_m=30.0,
            C0_override=500,
        )
        assert result.C0 == 500
