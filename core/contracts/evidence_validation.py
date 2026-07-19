"""
core/contracts/evidence_validation.py
=====================================

Evidence completeness, contradiction, and practitioner review-status gate
(OSSF-GW-003).

Invoked after structural/cross-field ``validate_site_case`` and before
preflight. Never calls the physics engine and never writes project state.

Critical missing bindings, provenance contradictions, or critical-tier
review failures (pending_review / rejected / superseded) raise
:class:`EvidenceValidationError` (exit 1 / evidence-failure artifact).
Important-tier pending_review or rejected evidence accumulates as warnings;
the run may still authorize.
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
from .site_case_v1 import SiteCaseV1


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

    Order of ``evidence``, ``field_bindings``, and linked ``assumptions`` is
    load-bearing: reordering changes the digest and therefore authorization
    identity.
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


def _review_summary(
    case: SiteCaseV1,
    evidence_by_id: Dict[str, EvidenceRecord],
) -> Dict[str, int]:
    """Binding-centric review summary for attestation.

    Counts use the effective review status for each binding (linked evidence
    status when ``evidence_id`` is present; otherwise the binding's own
    status). Totals for evidence_records / field_bindings are sizes only.
    """
    binding_counts = {
        "accepted": 0,
        "pending_review": 0,
        "rejected": 0,
        "superseded": 0,
    }
    for b in case.field_bindings:
        status = _effective_review(b, evidence_by_id)
        binding_counts[status.value] = binding_counts.get(status.value, 0) + 1
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
    """True when exactly one resolution route is present.

    Mirrors :class:`FieldEvidenceBinding` construction rules. When
    ``evidence_id`` is set, ``database_id`` / ``regulatory_authority`` on the
    binding are not auxiliary metadata — they are a second route and are
    rejected at record construction.
    """
    has_evidence = binding.evidence_id is not None
    has_db = (
        binding.database_id is not None and str(binding.database_id).strip() != ""
    )
    has_reg = (
        binding.regulatory_authority is not None
        and str(binding.regulatory_authority).strip() != ""
    )
    return sum((has_evidence, has_db, has_reg)) == 1


def effective_review_status(
    binding: FieldEvidenceBinding,
    evidence_by_id: Dict[str, EvidenceRecord],
) -> EvidenceReviewStatus:
    """Review status that gates the binding (canonical policy helper).

    When ``evidence_id`` is present and resolvable, the linked evidence
    record's ``review_status`` is authoritative (binding status is
    redundant local copy). Standalone citation bindings use their own
    ``review_status``.

    Shared by the evidence gate and readiness RDY-004 so acceptance
    semantics cannot drift across stages.
    """
    if binding.evidence_id and binding.evidence_id in evidence_by_id:
        return evidence_by_id[binding.evidence_id].review_status
    return binding.review_status


# Private alias retained for local call sites.
_effective_review = effective_review_status


def effective_provenance_class(
    binding: FieldEvidenceBinding,
    evidence_by_id: Dict[str, EvidenceRecord],
) -> ProvenanceClass:
    """Provenance that gates the binding (canonical policy helper).

    When ``evidence_id`` is present and resolvable, the linked evidence
    record's ``provenance_class`` is authoritative. Standalone citation
    bindings use their own ``provenance_class``.

    Mirrors :func:`effective_review_status` so review and provenance
    authority follow the same linked-evidence-first model.
    """
    if binding.evidence_id and binding.evidence_id in evidence_by_id:
        return evidence_by_id[binding.evidence_id].provenance_class
    return binding.provenance_class


@dataclass(frozen=True)
class CriticalBindingIssue:
    """One critical load-bearing binding acceptance problem.

    Shared between evidence validation and readiness RDY-004.
    """

    field_path: str
    code: str
    message: str


def _critical_multi_binding_issues(
    field_path: str,
    bound_list: List[FieldEvidenceBinding],
    evidence_by_id: Dict[str, EvidenceRecord],
) -> List[CriticalBindingIssue]:
    """Evaluate multiple bindings for one critical field.

    Policy:
    * conflicting provenance classes → ``conflicting_bindings``
    * exactly one ``accepted`` plus zero or more ``superseded`` (same
      provenance) → allowed (accepted replacement pattern)
    * ``rejected`` / ``pending_review`` always block
    * ``superseded`` without an accepted replacement → ``superseded``
    * any other multi-binding shape (e.g. two accepted) → ``duplicate_bindings``
    """
    classes = {b.provenance_class for b in bound_list}
    if len(classes) > 1:
        return [CriticalBindingIssue(
            field_path=field_path,
            code="conflicting_bindings",
            message=(
                f"field {field_path!r} has conflicting provenance "
                f"bindings: {sorted(c.value for c in classes)}"
            ),
        )]

    statuses = [
        effective_review_status(b, evidence_by_id) for b in bound_list
    ]
    accepted_count = sum(
        1 for s in statuses if s == EvidenceReviewStatus.ACCEPTED
    )
    blocking = [
        s for s in statuses
        if s in (
            EvidenceReviewStatus.REJECTED,
            EvidenceReviewStatus.PENDING_REVIEW,
        )
    ]
    only_accepted_or_superseded = all(
        s in (
            EvidenceReviewStatus.ACCEPTED,
            EvidenceReviewStatus.SUPERSEDED,
        )
        for s in statuses
    )

    # Accepted replacement: one accepted + any superseded history rows.
    if (
        accepted_count == 1
        and only_accepted_or_superseded
        and not blocking
    ):
        return []

    issues: List[CriticalBindingIssue] = []
    if blocking:
        for s in statuses:
            if s in (
                EvidenceReviewStatus.REJECTED,
                EvidenceReviewStatus.PENDING_REVIEW,
            ):
                issues.append(CriticalBindingIssue(
                    field_path=field_path,
                    code=s.value,
                    message=(
                        f"Critical load-bearing binding {field_path!r} "
                        f"has review_status {s.value!r}; must be "
                        "'accepted' before authorization."
                    ),
                ))
        return issues

    if accepted_count == 0 and any(
        s == EvidenceReviewStatus.SUPERSEDED for s in statuses
    ):
        return [CriticalBindingIssue(
            field_path=field_path,
            code="superseded",
            message=(
                f"critical field {field_path!r} evidence is superseded "
                f"without an accepted replacement"
            ),
        )]

    return [CriticalBindingIssue(
        field_path=field_path,
        code="duplicate_bindings",
        message=(
            f"field {field_path!r} has {len(bound_list)} "
            f"bindings with provenance "
            f"{next(iter(classes)).value!r}; exactly one accepted "
            f"binding per load-bearing field is required "
            f"(superseded history rows may accompany one accepted "
            f"replacement)"
        ),
    )]


def iter_critical_binding_acceptance_issues(
    case: SiteCaseV1,
) -> Tuple[CriticalBindingIssue, ...]:
    """Return critical-binding acceptance issues for ``case``.

    Canonical policy used by both ``validate_evidence_layer`` (as hard
    errors) and readiness RDY-004 (as block findings). Covers:

    * missing binding
    * duplicate / conflicting multi-bindings
    * non-accepted effective review status
    * superseded-without-accepted-replacement

    Multiple bindings for one critical field are allowed only when they
    form an accepted-replacement pattern: exactly one ``accepted`` binding
    plus zero or more ``superseded`` history rows (same provenance class).

    Does not cover Important-tier warnings or provenance contradictions.
    """
    evidence_by_id = _index_evidence(case)
    bindings_by_path = _index_bindings(case)
    issues: List[CriticalBindingIssue] = []
    for req in required_bindings_for_case(case):
        if req.tier != FieldTier.CRITICAL:
            continue
        bound_list = bindings_by_path.get(req.field_path, [])
        if not bound_list:
            issues.append(CriticalBindingIssue(
                field_path=req.field_path,
                code="missing_binding",
                message=(
                    f"Critical load-bearing field {req.field_path!r} has no "
                    f"evidence binding ({req.rationale})"
                ),
            ))
            continue
        if len(bound_list) > 1:
            issues.extend(_critical_multi_binding_issues(
                req.field_path, bound_list, evidence_by_id
            ))
            continue
        for b in bound_list:
            status = effective_review_status(b, evidence_by_id)
            if status == EvidenceReviewStatus.ACCEPTED:
                continue
            if status == EvidenceReviewStatus.SUPERSEDED:
                issues.append(CriticalBindingIssue(
                    field_path=req.field_path,
                    code="superseded",
                    message=(
                        f"critical field {req.field_path!r} evidence is "
                        f"superseded without an accepted replacement"
                    ),
                ))
                continue
            issues.append(CriticalBindingIssue(
                field_path=req.field_path,
                code=status.value,
                message=(
                    f"Critical load-bearing binding {req.field_path!r} "
                    f"has review_status {status.value!r}; must be "
                    "'accepted' before authorization."
                ),
            ))
    return tuple(issues)


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
    """Validate resolution routes and provenance alignment.

    Authority model after this pass:
    * linked-evidence bindings: binding.provenance_class must equal the
      evidence record's provenance_class (enforced here), so subsequent
      checks may read either equivalently;
    * standalone database_id / regulatory_authority bindings: provenance
      must match the citation type;
    * citation fields on the binding are never auxiliary when evidence_id
      is set — FieldEvidenceBinding construction already rejects that.
    """
    assumption_ids = {a.assumption_id for a in case.assumptions}
    for i, b in enumerate(case.field_bindings):
        base = f"field_bindings[{i}]"
        if not _binding_resolvable(b):
            contradictions.add(
                f"{base}.evidence_id",
                "unresolvable",
                "binding must carry exactly one of evidence_id, database_id, "
                "or regulatory_authority",
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

        elif b.database_id:
            if b.provenance_class != ProvenanceClass.DATABASE_DERIVED:
                contradictions.add(
                    f"{base}.provenance_class",
                    "provenance_mismatch",
                    "database_id citation requires provenance_class "
                    "'database_derived'",
                    invalid_value=b.provenance_class.value,
                )

        elif b.regulatory_authority:
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
    evidence_by_id: Dict[str, EvidenceRecord],
    contradictions: ErrorCollector,
) -> None:
    # Compare against effective provenance (linked evidence when present).
    # _check_binding_resolution already requires binding/evidence provenance
    # equality for evidence_id routes; using effective_provenance_class keeps
    # the authority model consistent with effective_review_status.
    for c in case.constituents:
        path = f"constituents[{c.constituent_id}].source_basis"
        bound = bindings_by_path.get(path, [])
        if not bound:
            continue
        for b in bound:
            effective = effective_provenance_class(b, evidence_by_id)
            if effective != c.source_basis:
                contradictions.add(
                    path,
                    "provenance_mismatch",
                    (
                        f"constituent source_basis {c.source_basis.value!r} "
                        f"contradicts effective binding provenance_class "
                        f"{effective.value!r}"
                    ),
                    invalid_value=c.source_basis.value,
                )


def _check_completeness_and_review(
    case: SiteCaseV1,
    required: List[RequiredBinding],
    bindings_by_path: Dict[str, List[FieldEvidenceBinding]],
    evidence_by_id: Dict[str, EvidenceRecord],
    critical_missing: ErrorCollector,
    critical_conflicts: ErrorCollector,
    critical_review: ErrorCollector,
    warnings: List[EvidenceWarning],
) -> None:
    # Critical-tier acceptance uses the shared helper so readiness RDY-004
    # cannot drift from this gate.
    for issue in iter_critical_binding_acceptance_issues(case):
        if issue.code in ("conflicting_bindings", "duplicate_bindings"):
            critical_conflicts.add(
                issue.field_path, issue.code, issue.message
            )
        elif issue.code == "missing_binding":
            critical_missing.add(
                issue.field_path, issue.code, issue.message
            )
        else:
            critical_review.add(
                issue.field_path, issue.code, issue.message
            )

    # Important-tier completeness / review remains evidence-gate local
    # (readiness surfaces these via RDY-003 from evidence warnings).
    for req in required:
        if req.tier != FieldTier.IMPORTANT:
            continue
        bound_list = bindings_by_path.get(req.field_path, [])
        if not bound_list:
            warnings.append(EvidenceWarning(
                path=req.field_path,
                code="missing_binding",
                message=(
                    f"load-bearing field {req.field_path!r} has no evidence "
                    f"binding ({req.tier.value}: {req.rationale})"
                ),
            ))
            continue
        if len(bound_list) > 1:
            # Important duplicates: warn rather than block; critical path
            # already rejects duplicates via the shared helper.
            warnings.append(EvidenceWarning(
                path=req.field_path,
                code="duplicate_bindings",
                message=(
                    f"important field {req.field_path!r} has "
                    f"{len(bound_list)} bindings; prefer exactly one"
                ),
            ))
            continue
        for b in bound_list:
            status = effective_review_status(b, evidence_by_id)
            if status == EvidenceReviewStatus.ACCEPTED:
                continue
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
    _check_source_basis_alignment(
        case, bindings_by_path, evidence_by_id, contradictions
    )

    critical_missing = ErrorCollector()
    critical_conflicts = ErrorCollector()
    critical_review = ErrorCollector()
    warnings: List[EvidenceWarning] = []

    required = required_bindings_for_case(case)
    _check_completeness_and_review(
        case, required, bindings_by_path, evidence_by_id,
        critical_missing, critical_conflicts, critical_review, warnings,
    )

    if contradictions or critical_conflicts:
        merged = list(contradictions.errors) + list(critical_conflicts.errors)
        raise EvidenceContradictionError(
            merged, message="Evidence provenance contradiction"
        )
    if critical_missing:
        raise EvidenceCompletenessError(
            critical_missing.errors,
            message="Critical load-bearing evidence binding missing",
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
        review_summary=_review_summary(case, evidence_by_id),
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
    "CriticalBindingIssue",
    "compute_evidence_digest",
    "effective_review_status",
    "effective_provenance_class",
    "iter_critical_binding_acceptance_issues",
    "validate_evidence_layer",
    "evidence_result_summary_dict",
    "evidence_failure_artifact",
]
