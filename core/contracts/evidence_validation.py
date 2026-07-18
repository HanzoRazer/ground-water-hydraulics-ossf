"""
core/contracts/evidence_validation.py
=====================================

Evidence completeness, contradiction, and practitioner review-status gate
(OSSF-GW-003).

Invoked after structural/cross-field ``validate_site_case`` and before
preflight. Never calls the physics engine and never writes project state.

Critical missing or rejected evidence raises :class:`EvidenceValidationError`
(exit 1 / evidence-failure artifact). Important pending_review or rejected
evidence accumulates as warnings; the run may still authorize.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..governance import sha256_of_json_stable
from .enums import (
    EvidenceReviewStatus,
    FieldTier,
    ProvenanceClass,
)
from .errors import (
    ErrorCollector,
    EvidenceCompletenessError,
    EvidenceContradictionError,
    EvidenceReviewGateError,
    EvidenceValidationError,
    FieldValidationError,
)
from .evidence_records import (
    EvidenceRecord,
    FieldEvidenceBinding,
    evidence_record_to_dict,
    field_binding_to_dict,
)
from .evidence_registry import RequiredBinding, required_bindings_for_case
from .site_case_v1 import DeclaredAssumption, SiteCaseV1


@dataclass(frozen=True)
class EvidenceWarning:
    """Non-fatal evidence-layer warning (Important tier)."""

    path: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"path": self.path, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class EvidenceValidationResult:
    """Successful evidence-layer outcome (proceed or warn).

    ``disposition`` is ``proceed`` when there are no evidence warnings, else
    ``warn``. Critical failures raise rather than returning refuse.
    """

    disposition: str
    evidence_digest: str
    warnings: Tuple[EvidenceWarning, ...]
    review_summary: Dict[str, int]
    bound_fields: Tuple[str, ...]

    @property
    def permits_preflight(self) -> bool:
        return self.disposition in ("proceed", "warn")


def compute_evidence_digest(case: SiteCaseV1) -> str:
    """Canonical digest of evidence[], field_bindings[], and linked assumptions.

    Linked assumptions are those referenced by ``assumption_id`` on a binding.
    Uses the same stable JSON hash as authorization/attestation.
    """
    linked_ids = {
        b.assumption_id for b in case.field_bindings if b.assumption_id
    }
    assumptions = [
        {
            "assumption_id": a.assumption_id,
            "description": a.description,
            "basis": a.basis.value,
            "status": a.status.value,
        }
        for a in case.assumptions
        if a.assumption_id in linked_ids
    ]
    payload = {
        "evidence": [evidence_record_to_dict(e) for e in case.evidence],
        "field_bindings": [field_binding_to_dict(b) for b in case.field_bindings],
        "assumptions": assumptions,
    }
    return sha256_of_json_stable(payload)


def _review_summary(case: SiteCaseV1) -> Dict[str, int]:
    counts = {
        "accepted": 0,
        "pending_review": 0,
        "rejected": 0,
        "superseded": 0,
        "evidence_records": len(case.evidence),
        "field_bindings": len(case.field_bindings),
    }
    for e in case.evidence:
        key = e.review_status.value
        if key in counts:
            counts[key] += 1
    for b in case.field_bindings:
        key = b.review_status.value
        # Count binding review statuses under a separate prefix to avoid
        # double-counting with evidence records in the headline totals.
        # Headline accepted/pending/rejected/superseded count evidence records;
        # binding statuses are included in bound-field review checks only.
        _ = key
    # Prefer binding-centric summary for attestation (what was reviewed for use).
    binding_counts = {
        "accepted": 0,
        "pending_review": 0,
        "rejected": 0,
        "superseded": 0,
    }
    for b in case.field_bindings:
        binding_counts[b.review_status.value] = (
            binding_counts.get(b.review_status.value, 0) + 1
        )
    return {
        "accepted": binding_counts["accepted"],
        "pending_review": binding_counts["pending_review"],
        "rejected": binding_counts["rejected"],
        "superseded": binding_counts["superseded"],
        "evidence_records": len(case.evidence),
        "field_bindings": len(case.field_bindings),
    }


def _index_evidence(case: SiteCaseV1) -> Dict[str, EvidenceRecord]:
    return {e.evidence_id: e for e in case.evidence}


def _index_bindings(case: SiteCaseV1) -> Dict[str, List[FieldEvidenceBinding]]:
    out: Dict[str, List[FieldEvidenceBinding]] = {}
    for b in case.field_bindings:
        out.setdefault(b.field_path, []).append(b)
    return out


def _binding_resolvable(binding: FieldEvidenceBinding) -> bool:
    if binding.evidence_id:
        return True
    if binding.database_id and str(binding.database_id).strip():
        return True
    if binding.regulatory_authority and str(binding.regulatory_authority).strip():
        return True
    return False


def _effective_review(
    binding: FieldEvidenceBinding,
    evidence_by_id: Dict[str, EvidenceRecord],
) -> EvidenceReviewStatus:
    """Review status that gates the binding: prefer linked evidence status
    when an evidence_id is present; otherwise the binding's own status."""
    if binding.evidence_id and binding.evidence_id in evidence_by_id:
        return evidence_by_id[binding.evidence_id].review_status
    return binding.review_status


def _effective_provenance(
    binding: FieldEvidenceBinding,
    evidence_by_id: Dict[str, EvidenceRecord],
) -> ProvenanceClass:
    if binding.evidence_id and binding.evidence_id in evidence_by_id:
        return evidence_by_id[binding.evidence_id].provenance_class
    return binding.provenance_class


def _check_duplicate_evidence_ids(case: SiteCaseV1, ec: ErrorCollector) -> None:
    seen: Dict[str, int] = {}
    for i, e in enumerate(case.evidence):
        if e.evidence_id in seen:
            ec.add(
                f"evidence[{i}].evidence_id",
                "duplicate_id",
                f"duplicate evidence_id {e.evidence_id!r}",
                invalid_value=e.evidence_id,
            )
        else:
            seen[e.evidence_id] = i


def _check_binding_resolution(
    case: SiteCaseV1,
    evidence_by_id: Dict[str, EvidenceRecord],
    contradictions: ErrorCollector,
) -> None:
    assumption_ids = {a.assumption_id for a in case.assumptions}
    for i, b in enumerate(case.field_bindings):
        base = f"field_bindings[{i}]"
        if not _binding_resolvable(b):
            contradictions.add(
                f"{base}.evidence_id",
                "unresolvable",
                "binding has no evidence_id, database_id, or regulatory_authority",
            )
            continue

        if b.evidence_id is not None:
            if b.evidence_id not in evidence_by_id:
                contradictions.add(
                    f"{base}.evidence_id",
                    "unknown_evidence",
                    f"evidence_id {b.evidence_id!r} is not in evidence[]",
                    invalid_value=b.evidence_id,
                )
            else:
                ev = evidence_by_id[b.evidence_id]
                if ev.provenance_class != b.provenance_class:
                    contradictions.add(
                        f"{base}.provenance_class",
                        "provenance_mismatch",
                        (
                            f"binding provenance_class {b.provenance_class.value!r} "
                            f"contradicts evidence {ev.evidence_id!r} "
                            f"({ev.provenance_class.value!r})"
                        ),
                        invalid_value=b.provenance_class.value,
                    )

        if b.database_id and b.evidence_id is None:
            if b.provenance_class != ProvenanceClass.DATABASE_DERIVED:
                contradictions.add(
                    f"{base}.provenance_class",
                    "provenance_mismatch",
                    "database_id citation requires provenance_class "
                    "'database_derived'",
                    invalid_value=b.provenance_class.value,
                )

        if b.regulatory_authority and b.evidence_id is None:
            if b.provenance_class != ProvenanceClass.REGULATORY_DEFAULT:
                contradictions.add(
                    f"{base}.provenance_class",
                    "provenance_mismatch",
                    "regulatory_authority citation requires provenance_class "
                    "'regulatory_default'",
                    invalid_value=b.provenance_class.value,
                )

        if b.assumption_id is not None and b.assumption_id not in assumption_ids:
            contradictions.add(
                f"{base}.assumption_id",
                "unknown_assumption",
                f"assumption_id {b.assumption_id!r} is not in assumptions[]",
                invalid_value=b.assumption_id,
            )


def _check_source_basis_alignment(
    case: SiteCaseV1,
    bindings_by_path: Dict[str, List[FieldEvidenceBinding]],
    contradictions: ErrorCollector,
) -> None:
    for c in case.constituents:
        path = f"constituents[{c.constituent_id}].source_basis"
        bound = bindings_by_path.get(path, [])
        if not bound:
            continue
        for b in bound:
            if b.provenance_class != c.source_basis:
                contradictions.add(
                    path,
                    "provenance_mismatch",
                    (
                        f"constituent source_basis {c.source_basis.value!r} "
                        f"contradicts binding provenance_class "
                        f"{b.provenance_class.value!r}"
                    ),
                    invalid_value=c.source_basis.value,
                )


def _check_completeness_and_review(
    required: List[RequiredBinding],
    bindings_by_path: Dict[str, List[FieldEvidenceBinding]],
    evidence_by_id: Dict[str, EvidenceRecord],
    critical_missing: ErrorCollector,
    critical_review: ErrorCollector,
    warnings: List[EvidenceWarning],
) -> None:
    for req in required:
        bound_list = bindings_by_path.get(req.field_path, [])
        if not bound_list:
            msg = (
                f"load-bearing field {req.field_path!r} has no evidence binding "
                f"({req.tier.value}: {req.rationale})"
            )
            if req.tier == FieldTier.CRITICAL:
                critical_missing.add(
                    req.field_path, "missing_binding", msg
                )
            else:
                warnings.append(EvidenceWarning(
                    path=req.field_path, code="missing_binding", message=msg
                ))
            continue

        if len(bound_list) > 1:
            # Multiple bindings for one field: contradiction if provenance differs.
            classes = {b.provenance_class for b in bound_list}
            if len(classes) > 1:
                critical_missing.add(  # treated as contradiction via raise path
                    req.field_path,
                    "conflicting_bindings",
                    (
                        f"field {req.field_path!r} has conflicting provenance "
                        f"bindings: {sorted(c.value for c in classes)}"
                    ),
                )
                continue

        for b in bound_list:
            status = _effective_review(b, evidence_by_id)
            if status == EvidenceReviewStatus.ACCEPTED:
                continue
            if req.tier == FieldTier.CRITICAL:
                if status == EvidenceReviewStatus.REJECTED:
                    critical_review.add(
                        req.field_path,
                        "rejected",
                        (
                            f"critical field {req.field_path!r} evidence is "
                            f"rejected"
                        ),
                    )
                elif status == EvidenceReviewStatus.PENDING_REVIEW:
                    critical_review.add(
                        req.field_path,
                        "pending_review",
                        (
                            f"critical field {req.field_path!r} evidence is "
                            f"pending_review"
                        ),
                    )
                elif status == EvidenceReviewStatus.SUPERSEDED:
                    critical_review.add(
                        req.field_path,
                        "superseded",
                        (
                            f"critical field {req.field_path!r} evidence is "
                            f"superseded without an accepted replacement"
                        ),
                    )
            else:
                warnings.append(EvidenceWarning(
                    path=req.field_path,
                    code=status.value,
                    message=(
                        f"important field {req.field_path!r} evidence is "
                        f"{status.value}"
                    ),
                ))


def validate_evidence_layer(case: SiteCaseV1) -> EvidenceValidationResult:
    """Validate evidence completeness, contradictions, and review status.

    Returns an :class:`EvidenceValidationResult` on proceed/warn. Raises
    :class:`EvidenceValidationError` (or a subclass) on critical failure.
    """
    if not isinstance(case, SiteCaseV1):
        raise EvidenceValidationError(
            [FieldValidationError(
                path="(root)", code="type",
                message="validate_evidence_layer requires a SiteCaseV1",
            )]
        )

    structural = ErrorCollector()
    _check_duplicate_evidence_ids(case, structural)
    if structural:
        raise EvidenceValidationError(
            structural.errors, message="Evidence layer structural failure"
        )

    evidence_by_id = _index_evidence(case)
    bindings_by_path = _index_bindings(case)

    contradictions = ErrorCollector()
    _check_binding_resolution(case, evidence_by_id, contradictions)
    _check_source_basis_alignment(case, bindings_by_path, contradictions)

    # Conflicting multi-bindings also checked in completeness pass.
    critical_missing = ErrorCollector()
    critical_review = ErrorCollector()
    warnings: List[EvidenceWarning] = []

    required = required_bindings_for_case(case)
    _check_completeness_and_review(
        required, bindings_by_path, evidence_by_id,
        critical_missing, critical_review, warnings,
    )

    # Promote conflicting_bindings into contradiction errors.
    conflict_errors = [
        e for e in critical_missing.errors if e.code == "conflicting_bindings"
    ]
    missing_errors = [
        e for e in critical_missing.errors if e.code != "conflicting_bindings"
    ]

    if contradictions or conflict_errors:
        merged = list(contradictions.errors) + conflict_errors
        raise EvidenceContradictionError(
            merged, message="Evidence provenance contradiction"
        )
    if missing_errors:
        raise EvidenceCompletenessError(
            missing_errors, message="Critical load-bearing evidence binding missing"
        )
    if critical_review:
        raise EvidenceReviewGateError(
            critical_review.errors,
            message="Critical evidence failed practitioner review gate",
        )

    digest = compute_evidence_digest(case)
    disposition = "warn" if warnings else "proceed"
    bound = tuple(sorted({b.field_path for b in case.field_bindings}))
    return EvidenceValidationResult(
        disposition=disposition,
        evidence_digest=digest,
        warnings=tuple(warnings),
        review_summary=_review_summary(case),
        bound_fields=bound,
    )


def evidence_result_summary_dict(result: EvidenceValidationResult) -> dict:
    """JSON-safe evidence block for success / refusal-auth artifacts."""
    return {
        "disposition": result.disposition,
        "evidence_digest": result.evidence_digest,
        "review_summary": dict(result.review_summary),
        "bound_field_count": len(result.bound_fields),
        "evidence_warnings": [w.as_dict() for w in result.warnings],
    }


def evidence_failure_artifact(
    case: Optional[SiteCaseV1],
    exc: EvidenceValidationError,
    *,
    generated_utc: str,
) -> dict:
    """Build the exit-1 evidence-failure JSON artifact (not a preflight refusal)."""
    digest = None
    input_schema = None
    site_id = None
    if case is not None:
        try:
            digest = compute_evidence_digest(case)
        except Exception:  # pragma: no cover — best-effort
            digest = None
        input_schema = getattr(case, "schema_version", None)
        site_id = getattr(case, "site_id", None)
    return {
        "schema_version": "screening-evidence-failure-1.0",
        "status": "evidence_failure",
        "generated_utc": generated_utc,
        "site_id": site_id,
        "input_schema_version": input_schema,
        "evidence_digest": digest,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "errors": [
            {
                "path": e.path,
                "code": e.code,
                "message": e.message,
            }
            for e in exc.errors
        ],
        "notice": (
            "Evidence layer validation failed before preflight. The screening "
            "physics engine did not run. Supply complete, non-contradictory, "
            "review-accepted bindings for all critical load-bearing fields "
            "(OSSF-GW-003)."
        ),
    }


__all__ = [
    "EvidenceWarning",
    "EvidenceValidationResult",
    "compute_evidence_digest",
    "validate_evidence_layer",
    "evidence_result_summary_dict",
    "evidence_failure_artifact",
]
