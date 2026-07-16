"""
core/contracts/evidence_records.py
====================================

Immutable evidence-domain records for OSSF-GW-003 (SiteCase 1.1.0).

These records own data shape and record-local validity. Cross-record
completeness, contradiction detection, and review gating live in
``evidence_validation.py`` (later commits).

The legacy 1.0.0 ``DeclaredAssumption`` in ``site_case_v1`` is unchanged;
1.1.0 uses :class:`GovernedDeclaredAssumption` with field bindings and
review status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

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
    """Metadata describing the source of a load-bearing engineering value.

    Stores provenance and review metadata only — not file blobs or measured
    numeric values (those remain on canonical ``SiteCase`` fields).
    """

    evidence_id: str
    title: str
    provenance_class: ProvenanceClass
    confidence: EvidenceConfidence
    review_status: EvidenceReviewStatus
    source_reference: Optional[str] = None
    source_author: Optional[str] = None
    source_organization: Optional[str] = None
    source_date: Optional[str] = None
    captured_at_utc: Optional[str] = None
    notes: Optional[str] = None
    supersedes_evidence_id: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "evidence_id",
             P.check_stable_id(self.evidence_id, path="evidence[].evidence_id"))
        _set(self, "title", P.check_nonempty_str(self.title, path="evidence[].title"))
        _set(self, "provenance_class",
             parse_enum(ProvenanceClass, self.provenance_class,
                        path="evidence[].provenance_class"))
        _set(self, "confidence",
             parse_enum(EvidenceConfidence, self.confidence, path="evidence[].confidence"))
        _set(self, "review_status",
             parse_enum(EvidenceReviewStatus, self.review_status,
                        path="evidence[].review_status"))
        _set(self, "source_reference",
             P.check_optional_str(self.source_reference, path="evidence[].source_reference"))
        _set(self, "source_author",
             P.check_optional_str(self.source_author, path="evidence[].source_author"))
        _set(self, "source_organization",
             P.check_optional_str(self.source_organization, path="evidence[].source_organization"))
        _set(self, "source_date",
             P.check_optional_str(self.source_date, path="evidence[].source_date"))
        _set(self, "captured_at_utc",
             P.check_optional_str(self.captured_at_utc, path="evidence[].captured_at_utc"))
        _set(self, "notes", P.check_optional_str(self.notes, path="evidence[].notes"))
        if self.supersedes_evidence_id is not None:
            _set(self, "supersedes_evidence_id",
                 P.check_stable_id(self.supersedes_evidence_id,
                                   path="evidence[].supersedes_evidence_id"))


@dataclass(frozen=True)
class FieldEvidenceBinding:
    """Binds a canonical field path to provenance and review metadata."""

    binding_id: str
    field_path: str
    provenance_class: ProvenanceClass
    review_status: EvidenceReviewStatus
    is_primary: bool = True
    evidence_id: Optional[str] = None
    assumption_id: Optional[str] = None
    database_id: Optional[str] = None
    regulatory_authority: Optional[str] = None
    rationale: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "binding_id",
             P.check_stable_id(self.binding_id, path="evidence_bindings[].binding_id"))
        _set(self, "field_path",
             P.check_nonempty_str(self.field_path, path="evidence_bindings[].field_path"))
        _set(self, "provenance_class",
             parse_enum(ProvenanceClass, self.provenance_class,
                        path="evidence_bindings[].provenance_class"))
        _set(self, "review_status",
             parse_enum(EvidenceReviewStatus, self.review_status,
                        path="evidence_bindings[].review_status"))
        _set(self, "is_primary",
             P.check_bool(self.is_primary, path="evidence_bindings[].is_primary"))
        if self.evidence_id is not None:
            _set(self, "evidence_id",
                 P.check_stable_id(self.evidence_id,
                                   path="evidence_bindings[].evidence_id"))
        if self.assumption_id is not None:
            _set(self, "assumption_id",
                 P.check_stable_id(self.assumption_id,
                                   path="evidence_bindings[].assumption_id"))
        if self.database_id is not None:
            _set(self, "database_id",
                 P.check_stable_id(self.database_id,
                                   path="evidence_bindings[].database_id"))
        _set(self, "regulatory_authority",
             P.check_optional_str(self.regulatory_authority,
                                  path="evidence_bindings[].regulatory_authority"))
        _set(self, "rationale",
             P.check_optional_str(self.rationale, path="evidence_bindings[].rationale"))


@dataclass(frozen=True)
class GovernedDeclaredAssumption:
    """1.1.0 assumption record with explicit field bindings and review status."""

    assumption_id: str
    field_paths: Tuple[str, ...]
    provenance_class: ProvenanceClass
    rationale: str
    review_status: EvidenceReviewStatus
    supporting_evidence_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _set(self, "assumption_id",
             P.check_stable_id(self.assumption_id, path="assumptions[].assumption_id"))
        paths = self.field_paths
        if isinstance(paths, list):
            paths = tuple(paths)
        if not isinstance(paths, tuple) or len(paths) == 0:
            from .errors import ContractValidationError, FieldValidationError
            raise ContractValidationError([FieldValidationError(
                path="assumptions[].field_paths", code="required",
                message="must contain at least one field path",
                invalid_value=paths,
            )])
        _set(self, "field_paths",
             tuple(P.check_nonempty_str(p, path=f"assumptions[].field_paths[{i}]")
                   for i, p in enumerate(paths)))
        _set(self, "provenance_class",
             parse_enum(ProvenanceClass, self.provenance_class,
                        path="assumptions[].provenance_class"))
        _set(self, "rationale",
             P.check_nonempty_str(self.rationale, path="assumptions[].rationale"))
        _set(self, "review_status",
             parse_enum(EvidenceReviewStatus, self.review_status,
                        path="assumptions[].review_status"))
        ids = self.supporting_evidence_ids
        if isinstance(ids, list):
            ids = tuple(ids)
        _set(self, "supporting_evidence_ids",
             tuple(P.check_stable_id(x, path=f"assumptions[].supporting_evidence_ids[{i}]")
                   for i, x in enumerate(ids)))


__all__ = [
    "EvidenceRecord",
    "FieldEvidenceBinding",
    "GovernedDeclaredAssumption",
]
