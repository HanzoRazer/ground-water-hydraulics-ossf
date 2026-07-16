"""
test_evidence_records.py
========================

Unit tests for OSSF-GW-003 evidence-domain records (Commit 1).

Run: python -m pytest tests/test_evidence_records.py -v
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.contracts import (
    EvidenceBasis,
    EvidenceConfidence,
    EvidenceRecord,
    EvidenceReviewStatus,
    FieldEvidenceBinding,
    GovernedDeclaredAssumption,
    ProvenanceClass,
    evidence_basis_to_provenance_class,
)
from core.contracts.errors import ContractValidationError


def _sample_evidence(**overrides):
    base = dict(
        evidence_id="ev_gradient",
        title="Site gradient survey",
        provenance_class=ProvenanceClass.MEASURED,
        confidence=EvidenceConfidence.HIGH,
        review_status=EvidenceReviewStatus.ACCEPTED,
        source_reference="Field log 2026-03-01",
    )
    base.update(overrides)
    return EvidenceRecord(**base)


def test_evidence_record_immutable():
    rec = _sample_evidence()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.title = "other"  # type: ignore[misc]


def test_evidence_record_accepts_string_enums():
    rec = EvidenceRecord(
        evidence_id="ev1",
        title="Test",
        provenance_class="documented",
        confidence="medium",
        review_status="pending_review",
    )
    assert rec.provenance_class is ProvenanceClass.DOCUMENTED
    assert rec.confidence is EvidenceConfidence.MEDIUM
    assert rec.review_status is EvidenceReviewStatus.PENDING_REVIEW


def test_evidence_record_rejects_invalid_enum():
    with pytest.raises(ContractValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            title="Test",
            provenance_class="fabricated",
            confidence="high",
            review_status="accepted",
        )


def test_field_binding_database_derived_without_evidence_id():
    binding = FieldEvidenceBinding(
        binding_id="bind_soil",
        field_path="subsurface.soil_id",
        provenance_class=ProvenanceClass.DATABASE_DERIVED,
        review_status=EvidenceReviewStatus.ACCEPTED,
        database_id="clay_loam",
    )
    assert binding.evidence_id is None
    assert binding.database_id == "clay_loam"


def test_field_binding_regulatory_default_with_authority():
    binding = FieldEvidenceBinding(
        binding_id="bind_basis",
        field_path="constituents[e_coli].source_basis",
        provenance_class=ProvenanceClass.REGULATORY_DEFAULT,
        review_status=EvidenceReviewStatus.ACCEPTED,
        regulatory_authority="30 TAC 285",
    )
    assert binding.regulatory_authority == "30 TAC 285"


def test_governed_assumption_requires_field_paths():
    with pytest.raises(ContractValidationError):
        GovernedDeclaredAssumption(
            assumption_id="asm1",
            field_paths=(),
            provenance_class=ProvenanceClass.ASSUMED,
            rationale="No direct measurement available",
            review_status=EvidenceReviewStatus.ACCEPTED,
        )


def test_governed_assumption_coerces_list_to_tuple():
    asm = GovernedDeclaredAssumption(
        assumption_id="asm_gradient",
        field_paths=["groundwater.hydraulic_gradient"],
        provenance_class=ProvenanceClass.ASSUMED,
        rationale="Conservative default pending survey",
        review_status=EvidenceReviewStatus.PENDING_REVIEW,
        supporting_evidence_ids=["ev_notes"],
    )
    assert asm.field_paths == ("groundwater.hydraulic_gradient",)
    assert asm.supporting_evidence_ids == ("ev_notes",)


@pytest.mark.parametrize(
    "basis,expected",
    [
        (EvidenceBasis.MEASURED, ProvenanceClass.MEASURED),
        (EvidenceBasis.ESTIMATED, ProvenanceClass.ASSUMED),
        (EvidenceBasis.LITERATURE, ProvenanceClass.DOCUMENTED),
        (EvidenceBasis.REGULATORY_DEFAULT, ProvenanceClass.REGULATORY_DEFAULT),
        (EvidenceBasis.ASSUMED, ProvenanceClass.ASSUMED),
    ],
)
def test_evidence_basis_maps_to_provenance_class(basis, expected):
    assert evidence_basis_to_provenance_class(basis) is expected
