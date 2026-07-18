"""
test_evidence_records.py
========================

Local validation for EvidenceRecord / FieldEvidenceBinding (OSSF-GW-003).

Run: python -m pytest tests/test_evidence_records.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.contracts import (
    ContractValidationError,
    EvidenceConfidence,
    EvidenceRecord,
    EvidenceReviewStatus,
    FieldEvidenceBinding,
    ProvenanceClass,
)


def test_evidence_record_coerces_enums():
    rec = EvidenceRecord(
        evidence_id="ev1",
        provenance_class="measured",
        confidence="high",
        review_status="accepted",
        source_description="Piezometer transect",
    )
    assert rec.provenance_class is ProvenanceClass.MEASURED
    assert rec.confidence is EvidenceConfidence.HIGH
    assert rec.review_status is EvidenceReviewStatus.ACCEPTED


def test_binding_requires_resolution_route():
    with pytest.raises(ContractValidationError):
        FieldEvidenceBinding(
            field_path="groundwater.hydraulic_gradient",
            provenance_class="assumed",
            review_status="accepted",
        )


def test_binding_may_omit_evidence_id_with_database_id():
    b = FieldEvidenceBinding(
        field_path="subsurface.soil_id",
        provenance_class="database_derived",
        review_status="accepted",
        database_id="clay_loam",
    )
    assert b.evidence_id is None
    assert b.database_id == "clay_loam"


def test_binding_may_omit_evidence_id_with_regulatory_authority():
    b = FieldEvidenceBinding(
        field_path="constituents[e_coli].use_governed_default",
        provenance_class="regulatory_default",
        review_status="accepted",
        regulatory_authority="30 TAC Ch. 285",
    )
    assert b.evidence_id is None
