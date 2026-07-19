"""
core/readiness/assessment.py
============================

Practitioner readiness assessment (OSSF-GW-004).

Invoked after ``validate_evidence_layer`` and before preflight SAD.
Produces a deterministic :class:`ReadinessAssessment` with a
``readiness_digest`` that authorization and attestation later bind.

Does not own SiteCase validation, evidence completeness, SAD thresholds, or
physics. Rules are code-owned and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..contracts.enums import AssumptionStatus, FieldTier
from ..contracts.evidence_registry import required_bindings_for_case
from ..contracts.evidence_validation import (
    compute_evidence_digest,
    iter_critical_binding_acceptance_issues,
)
from ..contracts.serialization import site_case_hash
from ..contracts.site_case_v1 import SiteCaseV1
from .digest import (
    READINESS_SCHEMA_VERSION,
    compute_readiness_digest,
)
from .errors import ReadinessError, ReadinessNotReadyError


# ---------------------------------------------------------------------------
# Dispositions
# ---------------------------------------------------------------------------

READY = "ready"
READY_WITH_WARNINGS = "ready_with_warnings"
NOT_READY = "not_ready"

PERMITTING_DISPOSITIONS: Tuple[str, ...] = (READY, READY_WITH_WARNINGS)

_DISPOSITION_RANK = {
    READY: 0,
    READY_WITH_WARNINGS: 1,
    NOT_READY: 2,
}


def _worse(a: str, b: str) -> str:
    """Return the worse of two dispositions (NOT_READY > WARNINGS > READY)."""
    return a if _DISPOSITION_RANK[a] >= _DISPOSITION_RANK[b] else b


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReadinessFinding:
    """One readiness rule finding."""

    finding_id: str          # e.g. RDY-003
    severity: str            # "block" | "warn" | "info"
    code: str
    message: str
    path: str | None = None

    def as_dict(self) -> dict:
        d = {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.path is not None:
            d["path"] = self.path
        return d


@dataclass(frozen=True)
class ReadinessAssessment:
    """Outcome of practitioner readiness assessment.

    ``assessed_utc`` is factual wall-clock and is excluded from
    ``readiness_digest``.
    """

    schema_version: str
    disposition: str
    readiness_digest: str
    case_hash: str
    evidence_digest: str
    findings: tuple[ReadinessFinding, ...]
    assessed_utc: str

    @property
    def permits_authorization(self) -> bool:
        return self.disposition in PERMITTING_DISPOSITIONS

    def warnings(self) -> tuple[ReadinessFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "warn")

    def blocks(self) -> tuple[ReadinessFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "block")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _index_bindings(case: SiteCaseV1) -> Dict[str, list]:
    out: Dict[str, list] = {}
    for b in case.field_bindings:
        out.setdefault(b.field_path, []).append(b)
    return out


def _index_assumptions(case: SiteCaseV1) -> dict:
    return {a.assumption_id: a for a in case.assumptions}


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _apply_rdy_001(evidence_result, findings: List[ReadinessFinding]) -> str:
    """RDY-001 — evidence_result must permit preflight."""
    if evidence_result is None:
        findings.append(ReadinessFinding(
            finding_id="RDY-001",
            severity="block",
            code="missing_evidence_result",
            message=(
                "Readiness requires an EvidenceValidationResult that permits "
                "preflight; none was supplied."
            ),
        ))
        return NOT_READY
    if not getattr(evidence_result, "permits_preflight", False):
        findings.append(ReadinessFinding(
            finding_id="RDY-001",
            severity="block",
            code="evidence_not_permitting",
            message=(
                "Evidence layer does not permit preflight "
                f"(disposition={getattr(evidence_result, 'disposition', None)!r}); "
                "practitioner readiness is not_ready."
            ),
        ))
        return NOT_READY
    return READY


def _apply_rdy_002(
    case: SiteCaseV1,
    evidence_result,
    findings: List[ReadinessFinding],
) -> str:
    """RDY-002 — recomputed evidence_digest must match evidence_result."""
    expected = compute_evidence_digest(case)
    actual = getattr(evidence_result, "evidence_digest", None)
    if actual != expected:
        findings.append(ReadinessFinding(
            finding_id="RDY-002",
            severity="block",
            code="evidence_digest_mismatch",
            message=(
                "evidence_digest does not match the site case "
                f"(result {actual!r}, recomputed {expected!r}); "
                "treating as tamper / inconsistency."
            ),
        ))
        return NOT_READY
    return READY


def _apply_rdy_003(evidence_result, findings: List[ReadinessFinding]) -> str:
    """RDY-003 — Important-tier evidence warnings → ready_with_warnings."""
    warnings = tuple(getattr(evidence_result, "warnings", ()) or ())
    if not warnings:
        return READY
    for w in warnings:
        findings.append(ReadinessFinding(
            finding_id="RDY-003",
            severity="warn",
            code=getattr(w, "code", "evidence_warning"),
            message=(
                "Important-tier evidence warning carried into readiness: "
                f"{getattr(w, 'message', str(w))}"
            ),
            path=getattr(w, "path", None),
        ))
    return READY_WITH_WARNINGS


def _apply_rdy_004(
    case: SiteCaseV1,
    findings: List[ReadinessFinding],
) -> str:
    """RDY-004 — every critical load-bearing binding must be accepted.

    Uses :func:`iter_critical_binding_acceptance_issues` — the same
    canonical policy helper as the evidence gate — so acceptance semantics
    cannot drift between stages (OSSF-GW-003 / OSSF-GW-004).
    """
    disposition = READY
    for issue in iter_critical_binding_acceptance_issues(case):
        code = (
            "missing_critical_binding"
            if issue.code == "missing_binding"
            else issue.code
        )
        findings.append(ReadinessFinding(
            finding_id="RDY-004",
            severity="block",
            code=code,
            message=issue.message,
            path=issue.field_path,
        ))
        disposition = NOT_READY
    return disposition


def _apply_rdy_005(
    case: SiteCaseV1,
    findings: List[ReadinessFinding],
) -> str:
    """RDY-005 — pending_verification assumptions on critical bindings warn."""
    assumptions = _index_assumptions(case)
    bindings_by_path = _index_bindings(case)
    disposition = READY
    for req in required_bindings_for_case(case):
        if req.tier != FieldTier.CRITICAL:
            continue
        for b in bindings_by_path.get(req.field_path, []):
            if not b.assumption_id:
                continue
            asm = assumptions.get(b.assumption_id)
            if asm is None:
                continue
            if asm.status == AssumptionStatus.PENDING_VERIFICATION:
                findings.append(ReadinessFinding(
                    finding_id="RDY-005",
                    severity="warn",
                    code="pending_verification",
                    message=(
                        f"Critical binding {req.field_path!r} links assumption "
                        f"{b.assumption_id!r} with status pending_verification; "
                        "proceeding with warnings."
                    ),
                    path=req.field_path,
                ))
                disposition = READY_WITH_WARNINGS
    return disposition


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assess_readiness(case: SiteCaseV1, evidence_result) -> ReadinessAssessment:
    """Assess practitioner readiness after evidence validation.

    Returns a :class:`ReadinessAssessment` for every outcome, including
    ``not_ready``. Callers that require a permitting disposition should check
    ``permits_authorization`` or call :func:`require_readiness`.
    """
    if not isinstance(case, SiteCaseV1):
        raise ReadinessError(
            "assess_readiness requires a validated SiteCaseV1, not a "
            f"raw {type(case).__name__}."
        )

    findings: List[ReadinessFinding] = []
    disposition = READY

    disposition = _worse(disposition, _apply_rdy_001(evidence_result, findings))
    # RDY-002 needs a digest to compare; still run when result exists.
    if evidence_result is not None:
        disposition = _worse(
            disposition, _apply_rdy_002(case, evidence_result, findings)
        )
        disposition = _worse(
            disposition, _apply_rdy_003(evidence_result, findings)
        )
    disposition = _worse(disposition, _apply_rdy_004(case, findings))
    disposition = _worse(disposition, _apply_rdy_005(case, findings))

    case_hash = site_case_hash(case)
    if evidence_result is not None and getattr(
        evidence_result, "evidence_digest", None
    ):
        evidence_digest = evidence_result.evidence_digest
    else:
        evidence_digest = compute_evidence_digest(case)

    findings_t = tuple(findings)
    digest = compute_readiness_digest(
        schema_version=READINESS_SCHEMA_VERSION,
        case_hash=case_hash,
        evidence_digest=evidence_digest,
        disposition=disposition,
        findings=findings_t,
    )

    return ReadinessAssessment(
        schema_version=READINESS_SCHEMA_VERSION,
        disposition=disposition,
        readiness_digest=digest,
        case_hash=case_hash,
        evidence_digest=evidence_digest,
        findings=findings_t,
        assessed_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def require_readiness(case: SiteCaseV1, evidence_result) -> ReadinessAssessment:
    """Assess readiness and raise :class:`ReadinessNotReadyError` if blocked."""
    assessment = assess_readiness(case, evidence_result)
    if not assessment.permits_authorization:
        raise ReadinessNotReadyError(assessment)
    return assessment


def readiness_result_summary_dict(result: ReadinessAssessment) -> dict:
    """JSON-safe readiness block for success / refusal / failure artifacts."""
    return {
        "schema_version": result.schema_version,
        "disposition": result.disposition,
        "readiness_digest": result.readiness_digest,
        "case_hash": result.case_hash,
        "evidence_digest": result.evidence_digest,
        "permits_authorization": result.permits_authorization,
        "findings": [f.as_dict() for f in result.findings],
        "assessed_utc": result.assessed_utc,
    }


def readiness_failure_artifact(
    case: Optional[SiteCaseV1],
    assessment: ReadinessAssessment,
    *,
    generated_utc: str,
) -> dict:
    """Build the exit-1 readiness-failure JSON artifact (not preflight refusal)."""
    site_id = getattr(case, "site_id", None) if case is not None else None
    input_schema = (
        getattr(case, "schema_version", None) if case is not None else None
    )
    return {
        "schema_version": "screening-readiness-failure-1.0",
        "status": "readiness_failure",
        "generated_utc": generated_utc,
        "site_id": site_id,
        "input_schema_version": input_schema,
        "readiness": readiness_result_summary_dict(assessment),
        "notice": (
            "Practitioner readiness assessment failed before preflight. "
            "The screening physics engine did not run. Resolve blocking "
            "readiness findings (OSSF-GW-004) before authorization."
        ),
    }


__all__ = [
    "READY",
    "READY_WITH_WARNINGS",
    "NOT_READY",
    "PERMITTING_DISPOSITIONS",
    "ReadinessFinding",
    "ReadinessAssessment",
    "assess_readiness",
    "require_readiness",
    "readiness_result_summary_dict",
    "readiness_failure_artifact",
]
