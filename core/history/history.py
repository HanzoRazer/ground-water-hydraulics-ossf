"""
core/history/history.py
=======================

Immutable case-history and decision-ledger contracts (OSSF-GW-005).

Records the evolution of a screening case as append-only revisions,
engineering decisions, and (when authorized) execution records. Does not
own SiteCase, evidence, readiness, authorization, or physics — it only
binds their digests and identifiers.

Digests (locked decision 6C):

* ``history_chain_digest`` — content-only chain identity (no timestamps)
* ``history_artifact_digest`` — computed over the serialized artifact in
  ``serialization.py`` (may include timestamps)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

from ..governance import sha256_of_json_stable
from .events import DecisionCategory, HistoryEventType
from .errors import HistoryValidationError

HISTORY_SCHEMA_VERSION = "ossf-case-history-1.0.0"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CaseRevision:
    """One immutable snapshot binding in the case chronology."""

    revision_number: int
    revision_id: str
    previous_revision_id: str | None
    case_hash: str
    evidence_digest: str
    readiness_digest: str | None
    authorization_id: str | None


@dataclass(frozen=True)
class DecisionRecord:
    """One engineering judgment entry in the decision ledger.

    ``timestamp`` is factual wall-clock and is excluded from
    ``history_chain_digest``.
    """

    decision_id: str
    category: DecisionCategory
    summary: str
    timestamp: str


@dataclass(frozen=True)
class ExecutionRecord:
    """One authorized screening execution bound to a revision.

    ``executed_utc`` is factual wall-clock and is excluded from
    ``history_chain_digest``.
    """

    execution_id: str
    revision_id: str
    engine_name: str
    result_status: str  # pass | fail (authorized paths)
    result_artifact: str
    report_artifact: str | None
    executed_utc: str


@dataclass(frozen=True)
class CaseHistory:
    """Governed case history: revisions, decisions, and executions."""

    schema_version: str
    revisions: tuple[CaseRevision, ...]
    decisions: tuple[DecisionRecord, ...]
    executions: tuple[ExecutionRecord, ...]

    @property
    def revision_count(self) -> int:
        return len(self.revisions)

    @property
    def execution_count(self) -> int:
        return len(self.executions)

    @property
    def latest_revision(self) -> CaseRevision:
        if not self.revisions:
            raise HistoryValidationError(
                "CaseHistory has no revisions; latest_revision is undefined."
            )
        return self.revisions[-1]

    @property
    def latest_revision_id(self) -> str:
        return self.latest_revision.revision_id


# ---------------------------------------------------------------------------
# Content-derived identifiers
# ---------------------------------------------------------------------------

def derive_revision_id(
    *,
    revision_number: int,
    previous_revision_id: str | None,
    case_hash: str,
    evidence_digest: str,
    readiness_digest: str | None,
    authorization_id: str | None,
) -> str:
    """Deterministic 16-hex revision id from content fields (no timestamps)."""
    return sha256_of_json_stable({
        "authorization_id": authorization_id,
        "case_hash": case_hash,
        "evidence_digest": evidence_digest,
        "previous_revision_id": previous_revision_id,
        "readiness_digest": readiness_digest,
        "revision_number": revision_number,
    })


def derive_decision_id(
    *,
    category: DecisionCategory,
    summary: str,
) -> str:
    """Deterministic 16-hex decision id (category + summary; no timestamp)."""
    return sha256_of_json_stable({
        "category": category.value if isinstance(category, DecisionCategory) else category,
        "summary": summary,
    })


def derive_execution_id(
    *,
    revision_id: str,
    engine_name: str,
    result_status: str,
    result_artifact: str,
    report_artifact: str | None,
) -> str:
    """Deterministic 16-hex execution id (no executed_utc)."""
    return sha256_of_json_stable({
        "engine_name": engine_name,
        "report_artifact": report_artifact,
        "result_artifact": result_artifact,
        "result_status": result_status,
        "revision_id": revision_id,
    })


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_revision(
    *,
    revision_number: int,
    previous_revision_id: str | None,
    case_hash: str,
    evidence_digest: str,
    readiness_digest: str | None = None,
    authorization_id: str | None = None,
) -> CaseRevision:
    """Build a :class:`CaseRevision` with a content-derived ``revision_id``."""
    if not isinstance(revision_number, int) or revision_number < 1:
        raise HistoryValidationError(
            f"revision_number must be an integer >= 1; got {revision_number!r}."
        )
    if not case_hash or not isinstance(case_hash, str):
        raise HistoryValidationError("case_hash is required.")
    if not evidence_digest or not isinstance(evidence_digest, str):
        raise HistoryValidationError("evidence_digest is required.")

    revision_id = derive_revision_id(
        revision_number=revision_number,
        previous_revision_id=previous_revision_id,
        case_hash=case_hash,
        evidence_digest=evidence_digest,
        readiness_digest=readiness_digest,
        authorization_id=authorization_id,
    )
    return CaseRevision(
        revision_number=revision_number,
        revision_id=revision_id,
        previous_revision_id=previous_revision_id,
        case_hash=case_hash,
        evidence_digest=evidence_digest,
        readiness_digest=readiness_digest,
        authorization_id=authorization_id,
    )


def build_decision(
    *,
    category: DecisionCategory,
    summary: str,
    timestamp: str | None = None,
) -> DecisionRecord:
    """Build a :class:`DecisionRecord` with a content-derived ``decision_id``."""
    if not isinstance(category, DecisionCategory):
        raise HistoryValidationError(
            f"category must be a DecisionCategory; got {type(category).__name__}."
        )
    if not summary or not isinstance(summary, str):
        raise HistoryValidationError("decision summary is required.")
    decision_id = derive_decision_id(category=category, summary=summary)
    return DecisionRecord(
        decision_id=decision_id,
        category=category,
        summary=summary,
        timestamp=timestamp if timestamp is not None else _utc_now(),
    )


def build_execution(
    *,
    revision_id: str,
    engine_name: str,
    result_status: str,
    result_artifact: str,
    report_artifact: str | None = None,
    executed_utc: str | None = None,
) -> ExecutionRecord:
    """Build an :class:`ExecutionRecord` with a content-derived ``execution_id``."""
    if result_status not in ("pass", "fail"):
        raise HistoryValidationError(
            f"result_status must be 'pass' or 'fail'; got {result_status!r}."
        )
    if not revision_id or not engine_name or not result_artifact:
        raise HistoryValidationError(
            "revision_id, engine_name, and result_artifact are required."
        )
    execution_id = derive_execution_id(
        revision_id=revision_id,
        engine_name=engine_name,
        result_status=result_status,
        result_artifact=result_artifact,
        report_artifact=report_artifact,
    )
    return ExecutionRecord(
        execution_id=execution_id,
        revision_id=revision_id,
        engine_name=engine_name,
        result_status=result_status,
        result_artifact=result_artifact,
        report_artifact=report_artifact,
        executed_utc=executed_utc if executed_utc is not None else _utc_now(),
    )


def build_case_history(
    *,
    revisions: Sequence[CaseRevision],
    decisions: Sequence[DecisionRecord] = (),
    executions: Sequence[ExecutionRecord] = (),
    schema_version: str = HISTORY_SCHEMA_VERSION,
) -> CaseHistory:
    """Assemble an immutable :class:`CaseHistory` (does not validate chain)."""
    if schema_version != HISTORY_SCHEMA_VERSION:
        raise HistoryValidationError(
            f"Unsupported history schema_version {schema_version!r}; "
            f"expected {HISTORY_SCHEMA_VERSION!r}."
        )
    if not revisions:
        raise HistoryValidationError(
            "CaseHistory requires at least one CaseRevision."
        )
    return CaseHistory(
        schema_version=schema_version,
        revisions=tuple(revisions),
        decisions=tuple(decisions),
        executions=tuple(executions),
    )


def decision_for_event(
    event: HistoryEventType,
    *,
    summary: str | None = None,
    timestamp: str | None = None,
) -> DecisionRecord:
    """Map a pipeline event to a categorized decision ledger entry."""
    if not isinstance(event, HistoryEventType):
        raise HistoryValidationError(
            f"event must be a HistoryEventType; got {type(event).__name__}."
        )
    category_map = {
        HistoryEventType.CASE_CREATED: DecisionCategory.REPORTING,
        HistoryEventType.EVIDENCE_VALIDATED: DecisionCategory.EVIDENCE,
        HistoryEventType.READINESS_ASSESSED: DecisionCategory.READINESS,
        HistoryEventType.AUTHORIZATION_GRANTED: DecisionCategory.AUTHORIZATION,
        HistoryEventType.AUTHORIZATION_DENIED: DecisionCategory.AUTHORIZATION,
        HistoryEventType.SCREENING_EXECUTED: DecisionCategory.EXECUTION,
        HistoryEventType.REPORT_EMITTED: DecisionCategory.REPORTING,
    }
    default_summaries = {
        HistoryEventType.CASE_CREATED: "Site case entered governed history.",
        HistoryEventType.EVIDENCE_VALIDATED: "Evidence layer validated.",
        HistoryEventType.READINESS_ASSESSED: "Practitioner readiness assessed.",
        HistoryEventType.AUTHORIZATION_GRANTED: "Screening authorization granted.",
        HistoryEventType.AUTHORIZATION_DENIED: (
            "Screening authorization denied; physics did not run."
        ),
        HistoryEventType.SCREENING_EXECUTED: "Authorized screening executed.",
        HistoryEventType.REPORT_EMITTED: "Screening report artifacts emitted.",
    }
    return build_decision(
        category=category_map[event],
        summary=summary if summary is not None else default_summaries[event],
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Chain digest (content-only; no timestamps)
# ---------------------------------------------------------------------------

def history_chain_digest_payload(history: CaseHistory) -> dict:
    """Canonical payload hashed into ``history_chain_digest``.

    Includes revision content bindings, decision ids/categories/summaries,
    and execution ids/revision bindings/artifact paths. Excludes all
    wall-clock timestamps.
    """
    return {
        "decisions": [
            {
                "category": d.category.value,
                "decision_id": d.decision_id,
                "summary": d.summary,
            }
            for d in history.decisions
        ],
        "executions": [
            {
                "engine_name": e.engine_name,
                "execution_id": e.execution_id,
                "report_artifact": e.report_artifact,
                "result_artifact": e.result_artifact,
                "result_status": e.result_status,
                "revision_id": e.revision_id,
            }
            for e in history.executions
        ],
        "revisions": [
            {
                "authorization_id": r.authorization_id,
                "case_hash": r.case_hash,
                "evidence_digest": r.evidence_digest,
                "previous_revision_id": r.previous_revision_id,
                "readiness_digest": r.readiness_digest,
                "revision_id": r.revision_id,
                "revision_number": r.revision_number,
            }
            for r in history.revisions
        ],
        "schema_version": history.schema_version,
    }


def compute_history_chain_digest(history: CaseHistory) -> str:
    """SHA-256 (16 hex) content-only chain digest (no timestamps)."""
    return sha256_of_json_stable(history_chain_digest_payload(history))


def verify_record_ids(history: CaseHistory) -> None:
    """Recompute content-derived ids and raise if any stored id mismatches."""
    for r in history.revisions:
        expected = derive_revision_id(
            revision_number=r.revision_number,
            previous_revision_id=r.previous_revision_id,
            case_hash=r.case_hash,
            evidence_digest=r.evidence_digest,
            readiness_digest=r.readiness_digest,
            authorization_id=r.authorization_id,
        )
        if r.revision_id != expected:
            raise HistoryValidationError(
                f"revision_id mismatch at revision {r.revision_number}: "
                f"stored {r.revision_id!r}, recomputed {expected!r}."
            )
    for d in history.decisions:
        expected = derive_decision_id(category=d.category, summary=d.summary)
        if d.decision_id != expected:
            raise HistoryValidationError(
                f"decision_id mismatch: stored {d.decision_id!r}, "
                f"recomputed {expected!r}."
            )
    for e in history.executions:
        expected = derive_execution_id(
            revision_id=e.revision_id,
            engine_name=e.engine_name,
            result_status=e.result_status,
            result_artifact=e.result_artifact,
            report_artifact=e.report_artifact,
        )
        if e.execution_id != expected:
            raise HistoryValidationError(
                f"execution_id mismatch: stored {e.execution_id!r}, "
                f"recomputed {expected!r}."
            )


__all__ = [
    "HISTORY_SCHEMA_VERSION",
    "CaseRevision",
    "DecisionRecord",
    "ExecutionRecord",
    "CaseHistory",
    "derive_revision_id",
    "derive_decision_id",
    "derive_execution_id",
    "build_revision",
    "build_decision",
    "build_execution",
    "build_case_history",
    "decision_for_event",
    "history_chain_digest_payload",
    "compute_history_chain_digest",
    "verify_record_ids",
]
