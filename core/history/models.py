"""
core/history/models.py
======================

Immutable CaseHistory contracts (OSSF-GW-005).

History is observational: it records governed actions. It never authorizes,
validates engineering data, or mutates prior revisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..contracts.enums import parse_enum
from .decision_categories import (
    AuthorityType,
    CreatedReason,
    DecisionCategory,
    DecisionOutcomeCode,
    ExecutionStatus,
    is_allowed_decision_combination,
)
from .errors import HistoryContractError
from .events import HistoryEventType
from .identity import HISTORY_SCHEMA_VERSION


def _set(obj, name, value) -> None:
    object.__setattr__(obj, name, value)


def _require_nonempty_str(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoryContractError(f"{field} must be a non-empty string")
    return value.strip()


def _require_hex16(value: object, *, field: str) -> str:
    s = _require_nonempty_str(value, field=field)
    if len(s) != 16 or any(c not in "0123456789abcdef" for c in s):
        raise HistoryContractError(
            f"{field} must be a lowercase 16-hex digest, got {value!r}"
        )
    return s


def _optional_hex16(value: object, *, field: str) -> Optional[str]:
    if value is None:
        return None
    return _require_hex16(value, field=field)


@dataclass(frozen=True)
class AuthorityRecord:
    """Structured decision authority (closed types; not free-form prose)."""

    authority_type: AuthorityType
    authority_id: str
    authority_role: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "authority_type",
             parse_enum(AuthorityType, self.authority_type, path="authority.authority_type"))
        _set(self, "authority_id",
             _require_nonempty_str(self.authority_id, field="authority.authority_id"))
        role = self.authority_role
        if role is not None:
            role = _require_nonempty_str(role, field="authority.authority_role")
        _set(self, "authority_role", role)
        if self.authority_type is AuthorityType.PRACTITIONER:
            if not self.authority_role:
                raise HistoryContractError(
                    "practitioner authority requires authority_role"
                )

    def to_dict(self) -> dict:
        return {
            "authority_type": self.authority_type.value,
            "authority_id": self.authority_id,
            "authority_role": self.authority_role,
        }


@dataclass(frozen=True)
class ArtifactBinding:
    """Relative path + digest for an artifact written by one invocation."""

    artifact_type: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        _set(self, "artifact_type",
             _require_nonempty_str(self.artifact_type, field="artifact_type"))
        path = _require_nonempty_str(self.relative_path, field="relative_path")
        if path.startswith("/") or ":\\" in path or path.startswith("\\\\"):
            raise HistoryContractError(
                f"relative_path must be relative, got {path!r}"
            )
        _set(self, "relative_path", path)
        digest = _require_nonempty_str(self.sha256, field="sha256")
        # File digests may be full (64) or truncated (16) lowercase hex.
        if len(digest) not in (16, 64) or any(
            c not in "0123456789abcdef" for c in digest
        ):
            raise HistoryContractError(
                f"sha256 must be lowercase 16- or 64-hex, got {digest!r}"
            )
        _set(self, "sha256", digest)

    def to_dict(self) -> dict:
        return {
            "artifact_type": self.artifact_type,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class CaseRevision:
    """One append-only revision of a screening case chronology."""

    revision_id: str
    revision_number: int
    parent_revision_id: Optional[str]
    site_digest: str
    evidence_digest: str
    readiness_digest: str
    authorization_id: Optional[str]
    result_digest: Optional[str]
    created_reason: CreatedReason
    created_utc: str

    def __post_init__(self) -> None:
        _set(self, "revision_id",
             _require_hex16(self.revision_id, field="revision_id"))
        if not isinstance(self.revision_number, int) or isinstance(
            self.revision_number, bool
        ):
            raise HistoryContractError("revision_number must be an int")
        if self.revision_number < 1:
            raise HistoryContractError("revision_number must be >= 1")
        _set(self, "parent_revision_id",
             _optional_hex16(self.parent_revision_id, field="parent_revision_id"))
        if self.revision_number == 1 and self.parent_revision_id is not None:
            raise HistoryContractError(
                "revision 1 must have parent_revision_id=null"
            )
        if self.revision_number > 1 and self.parent_revision_id is None:
            raise HistoryContractError(
                "revision > 1 requires parent_revision_id"
            )
        _set(self, "site_digest",
             _require_hex16(self.site_digest, field="site_digest"))
        _set(self, "evidence_digest",
             _require_hex16(self.evidence_digest, field="evidence_digest"))
        _set(self, "readiness_digest",
             _require_hex16(self.readiness_digest, field="readiness_digest"))
        _set(self, "authorization_id",
             _optional_hex16(self.authorization_id, field="authorization_id"))
        _set(self, "result_digest",
             _optional_hex16(self.result_digest, field="result_digest"))
        _set(self, "created_reason",
             parse_enum(CreatedReason, self.created_reason, path="created_reason"))
        if self.revision_number == 1 and self.created_reason is not CreatedReason.INITIAL_RUN:
            raise HistoryContractError(
                "revision 1 created_reason must be initial_run"
            )
        _set(self, "created_utc",
             _require_nonempty_str(self.created_utc, field="created_utc"))


@dataclass(frozen=True)
class DecisionRecord:
    """One aggregate governed decision within a revision."""

    decision_id: str
    sequence: int
    category: DecisionCategory
    event_type: HistoryEventType
    authority: AuthorityRecord
    outcome_code: DecisionOutcomeCode
    summary: str
    related_revision_id: str
    related_ids: Tuple[str, ...]

    def __post_init__(self) -> None:
        _set(self, "decision_id",
             _require_hex16(self.decision_id, field="decision_id"))
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool):
            raise HistoryContractError("sequence must be an int")
        if self.sequence < 1:
            raise HistoryContractError("sequence must be >= 1")
        _set(self, "category",
             parse_enum(DecisionCategory, self.category, path="category"))
        _set(self, "event_type",
             parse_enum(HistoryEventType, self.event_type, path="event_type"))
        if not isinstance(self.authority, AuthorityRecord):
            raise HistoryContractError("authority must be an AuthorityRecord")
        _set(self, "outcome_code",
             parse_enum(DecisionOutcomeCode, self.outcome_code, path="outcome_code"))
        if not is_allowed_decision_combination(
            self.category, self.event_type, self.outcome_code
        ):
            raise HistoryContractError(
                f"disallowed decision combination: "
                f"category={self.category.value}, "
                f"event_type={self.event_type.value}, "
                f"outcome_code={self.outcome_code.value}"
            )
        _set(self, "summary",
             _require_nonempty_str(self.summary, field="summary"))
        _set(self, "related_revision_id",
             _require_hex16(self.related_revision_id, field="related_revision_id"))
        if not isinstance(self.related_ids, tuple):
            _set(self, "related_ids", tuple(self.related_ids))
        for i, rid in enumerate(self.related_ids):
            if not isinstance(rid, str) or not rid.strip():
                raise HistoryContractError(
                    f"related_ids[{i}] must be a non-empty string"
                )


@dataclass(frozen=True)
class ExecutionRecord:
    """One screening execution attached to a revision (at most one in v1)."""

    execution_id: str
    revision_id: str
    authorization_id: str
    result_digest: str
    status: ExecutionStatus
    generated_artifacts: Tuple[ArtifactBinding, ...]
    started_utc: str
    completed_utc: str

    def __post_init__(self) -> None:
        _set(self, "execution_id",
             _require_hex16(self.execution_id, field="execution_id"))
        _set(self, "revision_id",
             _require_hex16(self.revision_id, field="revision_id"))
        _set(self, "authorization_id",
             _require_hex16(self.authorization_id, field="authorization_id"))
        _set(self, "result_digest",
             _require_hex16(self.result_digest, field="result_digest"))
        _set(self, "status",
             parse_enum(ExecutionStatus, self.status, path="status"))
        if not isinstance(self.generated_artifacts, tuple):
            _set(self, "generated_artifacts", tuple(self.generated_artifacts))
        for a in self.generated_artifacts:
            if not isinstance(a, ArtifactBinding):
                raise HistoryContractError(
                    "generated_artifacts must contain ArtifactBinding only"
                )
        _set(self, "started_utc",
             _require_nonempty_str(self.started_utc, field="started_utc"))
        _set(self, "completed_utc",
             _require_nonempty_str(self.completed_utc, field="completed_utc"))


@dataclass(frozen=True)
class CaseHistory:
    """Append-only governed case chronology (file-based; no persistence)."""

    schema_version: str
    history_id: str
    site_id: str
    history_chain_digest: str
    history_artifact_digest: str
    revisions: Tuple[CaseRevision, ...]
    decisions: Tuple[DecisionRecord, ...]
    executions: Tuple[ExecutionRecord, ...]

    def __post_init__(self) -> None:
        if self.schema_version != HISTORY_SCHEMA_VERSION:
            raise HistoryContractError(
                f"schema_version must be {HISTORY_SCHEMA_VERSION!r}, "
                f"got {self.schema_version!r}"
            )
        _set(self, "history_id",
             _require_hex16(self.history_id, field="history_id"))
        _set(self, "site_id",
             _require_nonempty_str(self.site_id, field="site_id"))
        _set(self, "history_chain_digest",
             _require_hex16(self.history_chain_digest, field="history_chain_digest"))
        _set(self, "history_artifact_digest",
             _require_hex16(
                 self.history_artifact_digest, field="history_artifact_digest"
             ))
        if not isinstance(self.revisions, tuple):
            _set(self, "revisions", tuple(self.revisions))
        if not isinstance(self.decisions, tuple):
            _set(self, "decisions", tuple(self.decisions))
        if not isinstance(self.executions, tuple):
            _set(self, "executions", tuple(self.executions))
        if not self.revisions:
            raise HistoryContractError("CaseHistory requires at least one revision")
        for r in self.revisions:
            if not isinstance(r, CaseRevision):
                raise HistoryContractError("revisions must contain CaseRevision only")
        for d in self.decisions:
            if not isinstance(d, DecisionRecord):
                raise HistoryContractError("decisions must contain DecisionRecord only")
        for e in self.executions:
            if not isinstance(e, ExecutionRecord):
                raise HistoryContractError("executions must contain ExecutionRecord only")


__all__ = [
    "HISTORY_SCHEMA_VERSION",
    "AuthorityRecord",
    "ArtifactBinding",
    "CaseRevision",
    "DecisionRecord",
    "ExecutionRecord",
    "CaseHistory",
]
