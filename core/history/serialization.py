"""
core/history/serialization.py
=============================

Stable JSON serialization and loading for CaseHistory (OSSF-GW-005).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .decision_categories import (
    AuthorityType,
    CreatedReason,
    DecisionCategory,
    DecisionOutcomeCode,
    ExecutionStatus,
)
from .digest import (
    compute_history_artifact_digest,
    compute_history_chain_digest,
)
from .errors import HistoryValidationError
from .events import HistoryEventType
from .identity import HISTORY_SCHEMA_VERSION
from .models import (
    ArtifactBinding,
    AuthorityRecord,
    CaseHistory,
    CaseRevision,
    DecisionRecord,
    ExecutionRecord,
)


def authority_to_dict(authority: AuthorityRecord) -> dict:
    return authority.to_dict()


def artifact_binding_to_dict(binding: ArtifactBinding) -> dict:
    return binding.to_dict()


def revision_to_dict(revision: CaseRevision) -> dict:
    return {
        "revision_id": revision.revision_id,
        "revision_number": revision.revision_number,
        "parent_revision_id": revision.parent_revision_id,
        "site_digest": revision.site_digest,
        "evidence_digest": revision.evidence_digest,
        "readiness_digest": revision.readiness_digest,
        "authorization_id": revision.authorization_id,
        "result_digest": revision.result_digest,
        "created_reason": revision.created_reason.value,
        "created_utc": revision.created_utc,
    }


def decision_to_dict(decision: DecisionRecord) -> dict:
    return {
        "decision_id": decision.decision_id,
        "sequence": decision.sequence,
        "category": decision.category.value,
        "event_type": decision.event_type.value,
        "authority": authority_to_dict(decision.authority),
        "outcome_code": decision.outcome_code.value,
        "summary": decision.summary,
        "related_revision_id": decision.related_revision_id,
        "related_ids": list(decision.related_ids),
    }


def execution_to_dict(execution: ExecutionRecord) -> dict:
    return {
        "execution_id": execution.execution_id,
        "revision_id": execution.revision_id,
        "authorization_id": execution.authorization_id,
        "result_digest": execution.result_digest,
        "status": execution.status.value,
        "generated_artifacts": [
            artifact_binding_to_dict(a) for a in execution.generated_artifacts
        ],
        "started_utc": execution.started_utc,
        "completed_utc": execution.completed_utc,
    }


def history_to_dict(history: CaseHistory) -> dict:
    """Serialize CaseHistory to a JSON-ready dict (includes both digests)."""
    return {
        "schema_version": history.schema_version,
        "history_id": history.history_id,
        "site_id": history.site_id,
        "history_chain_digest": history.history_chain_digest,
        "history_artifact_digest": history.history_artifact_digest,
        "revisions": [revision_to_dict(r) for r in history.revisions],
        "decisions": [decision_to_dict(d) for d in history.decisions],
        "executions": [execution_to_dict(e) for e in history.executions],
    }


def serialize_history(history: CaseHistory, *, indent: Optional[int] = 2) -> str:
    """Stable JSON text (sorted keys for artifact-digest reproducibility)."""
    return json.dumps(
        history_to_dict(history),
        indent=indent,
        sort_keys=True,
        ensure_ascii=False,
    ) + ("\n" if indent is not None else "")


def _parse_authority(raw: Mapping[str, Any]) -> AuthorityRecord:
    return AuthorityRecord(
        authority_type=AuthorityType(raw["authority_type"]),
        authority_id=raw["authority_id"],
        authority_role=raw.get("authority_role"),
    )


def _parse_artifact_binding(raw: Mapping[str, Any]) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_type=raw["artifact_type"],
        relative_path=raw["relative_path"],
        sha256=raw["sha256"],
    )


def _parse_revision(raw: Mapping[str, Any]) -> CaseRevision:
    return CaseRevision(
        revision_id=raw["revision_id"],
        revision_number=raw["revision_number"],
        parent_revision_id=raw.get("parent_revision_id"),
        site_digest=raw["site_digest"],
        evidence_digest=raw["evidence_digest"],
        readiness_digest=raw["readiness_digest"],
        authorization_id=raw.get("authorization_id"),
        result_digest=raw.get("result_digest"),
        created_reason=CreatedReason(raw["created_reason"]),
        created_utc=raw["created_utc"],
    )


def _parse_decision(raw: Mapping[str, Any]) -> DecisionRecord:
    return DecisionRecord(
        decision_id=raw["decision_id"],
        sequence=raw["sequence"],
        category=DecisionCategory(raw["category"]),
        event_type=HistoryEventType(raw["event_type"]),
        authority=_parse_authority(raw["authority"]),
        outcome_code=DecisionOutcomeCode(raw["outcome_code"]),
        summary=raw["summary"],
        related_revision_id=raw["related_revision_id"],
        related_ids=tuple(raw.get("related_ids") or ()),
    )


def _parse_execution(raw: Mapping[str, Any]) -> ExecutionRecord:
    return ExecutionRecord(
        execution_id=raw["execution_id"],
        revision_id=raw["revision_id"],
        authorization_id=raw["authorization_id"],
        result_digest=raw["result_digest"],
        status=ExecutionStatus(raw["status"]),
        generated_artifacts=tuple(
            _parse_artifact_binding(a) for a in (raw.get("generated_artifacts") or [])
        ),
        started_utc=raw["started_utc"],
        completed_utc=raw["completed_utc"],
    )


def history_from_dict(raw: Mapping[str, Any]) -> CaseHistory:
    """Parse a dict into CaseHistory without re-validating digests/chain."""
    try:
        return CaseHistory(
            schema_version=raw["schema_version"],
            history_id=raw["history_id"],
            site_id=raw["site_id"],
            history_chain_digest=raw["history_chain_digest"],
            history_artifact_digest=raw["history_artifact_digest"],
            revisions=tuple(_parse_revision(r) for r in raw["revisions"]),
            decisions=tuple(_parse_decision(d) for d in raw.get("decisions", [])),
            executions=tuple(_parse_execution(e) for e in raw.get("executions", [])),
        )
    except KeyError as exc:
        raise HistoryValidationError(
            f"missing required field {exc.args[0]!r}"
        ) from exc
    except (TypeError, ValueError, HistoryValidationError) as exc:
        raise HistoryValidationError(str(exc)) from exc


def load_history(path: Union[str, Path]) -> CaseHistory:
    """Read JSON from disk and parse into CaseHistory (no chain validation)."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise HistoryValidationError(
            f"cannot read history file: {exc}", path=str(p)
        ) from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HistoryValidationError(
            f"invalid JSON: {exc}", path=str(p)
        ) from exc
    if not isinstance(raw, dict):
        raise HistoryValidationError(
            "history root must be a JSON object", path=str(p)
        )
    return history_from_dict(raw)


def write_history(history: CaseHistory, path: Union[str, Path]) -> None:
    """Atomically write serialized history to ``path``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(serialize_history(history), encoding="utf-8")
    tmp.replace(p)


def recompute_digests_for_dict(raw: Mapping[str, Any]) -> tuple[str, str]:
    """Recompute chain and artifact digests from a serialized dict."""
    history = history_from_dict(raw)
    chain = compute_history_chain_digest(
        history_id=history.history_id,
        revisions=history.revisions,
        decisions=history.decisions,
        executions=history.executions,
        schema_version=history.schema_version,
    )
    artifact = compute_history_artifact_digest({
        **history_to_dict(history),
        "history_chain_digest": chain,
    })
    return chain, artifact


__all__ = [
    "history_to_dict",
    "history_from_dict",
    "serialize_history",
    "load_history",
    "write_history",
    "revision_to_dict",
    "decision_to_dict",
    "execution_to_dict",
    "recompute_digests_for_dict",
]
