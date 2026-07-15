"""Tests for attenuation.py — narrative attestation and classification."""

import pytest
from core.darcy import evaluate_flow
from core.attenuation import (
    classify_permeability,
    ReceptorEvaluation,
    narrative_attestation,
)
from core.transport import TransportResult


class TestClassifyPermeability:
    def test_very_low(self):
        assert classify_permeability(5e-8) == "very low"

    def test_low(self):
        assert classify_permeability(5e-7) == "low"

    def test_moderate(self):
        assert classify_permeability(5e-6) == "moderate"

    def test_moderately_high(self):
        assert classify_permeability(5e-5) == "moderately high"

    def test_high(self):
        assert classify_permeability(5e-4) == "high"

    def test_very_high(self):
        assert classify_permeability(5e-2) == "very high"


class TestReceptorEvaluation:
    @pytest.fixture
    def sample_flow(self):
        return evaluate_flow(K_sat=1e-6, gradient=0.01, effective_porosity=0.1)

    def test_all_pass_empty(self, sample_flow):
        ev = ReceptorEvaluation(
            receptor_name="test",
            receptor_type="well",
            distance_m=30.0,
            flow=sample_flow,
        )
        assert ev.all_constituents_pass is True

    def test_minimum_log_removal_empty(self, sample_flow):
        ev = ReceptorEvaluation(
            receptor_name="test",
            receptor_type="well",
            distance_m=30.0,
            flow=sample_flow,
        )
        assert ev.minimum_log_removal == 0.0


class TestNarrativeAttestation:
    @pytest.fixture
    def sample_flow(self):
        return evaluate_flow(K_sat=7.22e-7, gradient=0.01, effective_porosity=0.08)

    def test_returns_dict(self, sample_flow):
        attestation = narrative_attestation(
            soil_type="clay_loam",
            K_sat_m_per_s=7.22e-7,
            flow=sample_flow,
            receptor_evals=[],
        )
        assert isinstance(attestation, dict)
        assert "darcy_law_basis" in attestation
        assert "ksat_clause" in attestation
        assert "contact_time_clause" in attestation

    def test_ksat_clause_contains_soil(self, sample_flow):
        attestation = narrative_attestation(
            soil_type="clay_loam",
            K_sat_m_per_s=7.22e-7,
            flow=sample_flow,
            receptor_evals=[],
        )
        assert "clay loam" in attestation["ksat_clause"]
