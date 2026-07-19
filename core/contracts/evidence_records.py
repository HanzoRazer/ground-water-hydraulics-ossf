"""
core/contracts/evidence_records.py
==================================

Typed, immutable evidence and field-binding records for the OSSF evidence
and assumption layer (OSSF-GW-003).

These records own *evidence shape*: stable IDs, provenance class, confidence,
review status, and optional capture metadata (text/date only — no file blobs).
Completeness, contradiction, and review-gate policy live in
``evidence_validation.py``. The load-bearing field registry lives in
``evidence_registry.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import _primitives as P
from .enums import (
    EvidenceConfidence,
    EvidenceReviewStatus,
    ProvenanceClass,
    parse_enum,
)


def _set(obj, name, value) -> None:
    object.__setattr__(obj, name, value)


@dataclass(frozen=True)
class EvidenceRecord:
    """One immutable evidence record supporting one or more field bindings.

    Capture metadata is text/date only — document uploads and blob storage are
    out of scope for GW-003.
    """

    evidence_id: str
    provenance_class: ProvenanceClass
    confidence: EvidenceConfidence
    review_status: EvidenceReviewStatus
    source_description: str
    captured_date: Optional[str] = None
    notes: Optional[str] = None
    database_id: Optional[str] = None
    regulatory_authority: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "evidence_id",
             P.check_stable_id(self.evidence_id, path="evidence[].evidence_id"))
        _set(self, "provenance_class",
             parse_enum(ProvenanceClass, self.provenance_class,
                        path="evidence[].provenance_class"))
        _set(self, "confidence",
             parse_enum(EvidenceConfidence, self.confidence,
                        path="evidence[].confidence"))
        _set(self, "review_status",
             parse_enum(EvidenceReviewStatus, self.review_status,
                        path="evidence[].review_status"))
        _set(self, "source_description",
             P.check_nonempty_str(self.source_description,
                                  path="evidence[].source_description"))
        _set(self, "captured_date",
             P.check_optional_str(self.captured_date, path="evidence[].captured_date"))
        _set(self, "notes", P.check_optional_str(self.notes, path="evidence[].notes"))
        _set(self, "database_id",
             P.check_optional_str(self.database_id, path="evidence[].database_id"))
        _set(self, "regulatory_authority",
             P.check_optional_str(self.regulatory_authority,
                                  path="evidence[].regulatory_authority"))


@dataclass(frozen=True)
class FieldEvidenceBinding:
    """Binds a canonical field path to evidence and a provenance class.

    ``evidence_id`` may be omitted when the binding carries a ``database_id``
    (database_derived) or ``regulatory_authority`` citation
    (regulatory_default). Exactly one resolution route must be present.
    """

    field_path: str
    provenance_class: ProvenanceClass
    review_status: EvidenceReviewStatus
    evidence_id: Optional[str] = None
    database_id: Optional[str] = None
    regulatory_authority: Optional[str] = None
    assumption_id: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "field_path",
             P.check_nonempty_str(self.field_path, path="field_bindings[].field_path"))
        _set(self, "provenance_class",
             parse_enum(ProvenanceClass, self.provenance_class,
                        path="field_bindings[].provenance_class"))
        _set(self, "review_status",
             parse_enum(EvidenceReviewStatus, self.review_status,
                        path="field_bindings[].review_status"))
        if self.evidence_id is not None:
            _set(self, "evidence_id",
                 P.check_stable_id(self.evidence_id,
                                   path="field_bindings[].evidence_id"))
        _set(self, "database_id",
             P.check_optional_str(self.database_id,
                                  path="field_bindings[].database_id"))
        _set(self, "regulatory_authority",
             P.check_optional_str(self.regulatory_authority,
                                  path="field_bindings[].regulatory_authority"))
        if self.assumption_id is not None:
            _set(self, "assumption_id",
                 P.check_stable_id(self.assumption_id,
                                   path="field_bindings[].assumption_id"))
        _set(self, "notes",
             P.check_optional_str(self.notes, path="field_bindings[].notes"))

        has_evidence = self.evidence_id is not None
        has_db = self.database_id is not None and str(self.database_id).strip() != ""
        has_reg = (
            self.regulatory_authority is not None
            and str(self.regulatory_authority).strip() != ""
        )
        route_count = sum((has_evidence, has_db, has_reg))
        if route_count != 1:
            from .errors import ContractValidationError, FieldValidationError
            raise ContractValidationError([FieldValidationError(
                path="field_bindings[].evidence_id",
                code="ambiguous_resolution" if route_count > 1 else "required",
                message=(
                    "binding must carry exactly one resolution route: "
                    "evidence_id, database_id, or regulatory_authority"
                    + (
                        " (multiple routes present; citation fields belong on "
                        "the evidence record when evidence_id is set)"
                        if route_count > 1
                        else ""
                    )
                ),
            )])


def evidence_record_to_dict(rec: EvidenceRecord) -> dict:
    """Deterministic JSON-safe dict for an evidence record."""
    return {
        "evidence_id": rec.evidence_id,
        "provenance_class": rec.provenance_class.value,
        "confidence": rec.confidence.value,
        "review_status": rec.review_status.value,
        "source_description": rec.source_description,
        "captured_date": rec.captured_date,
        "notes": rec.notes,
        "database_id": rec.database_id,
        "regulatory_authority": rec.regulatory_authority,
    }


def field_binding_to_dict(binding: FieldEvidenceBinding) -> dict:
    """Deterministic JSON-safe dict for a field evidence binding."""
    return {
        "field_path": binding.field_path,
        "provenance_class": binding.provenance_class.value,
        "review_status": binding.review_status.value,
        "evidence_id": binding.evidence_id,
        "database_id": binding.database_id,
        "regulatory_authority": binding.regulatory_authority,
        "assumption_id": binding.assumption_id,
        "notes": binding.notes,
    }


__all__ = [
    "EvidenceRecord",
    "FieldEvidenceBinding",
    "evidence_record_to_dict",
    "field_binding_to_dict",
]
