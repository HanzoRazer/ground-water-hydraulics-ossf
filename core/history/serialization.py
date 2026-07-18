"""
core/history/serialization.py
=============================

Canonical serialization for :class:`~core.history.history.CaseHistory`
(OSSF-GW-005).

Single route for dict / canonical JSON / artifact digest / schema validation.
``history_artifact_digest`` hashes the full serialized instance (including
timestamps). ``history_chain_digest`` remains content-only in ``history.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..governance import sha256_of_json_stable
from .errors import HistoryValidationError
from .events import DecisionCategory
from .history import (
    HISTORY_SCHEMA_VERSION,
    CaseHistory,
    CaseRevision,
    DecisionRecord,
    ExecutionRecord,
    build_case_history,
    compute_history_chain_digest,
    verify_record_ids,
)

_SCHEMA_FILENAME = "ossf-case-history-1.0.0.schema.json"
_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"


# ---------------------------------------------------------------------------
# To / from dict
# ---------------------------------------------------------------------------

def revision_to_dict(revision: CaseRevision) -> dict:
    return {
        "revision_number": revision.revision_number,
        "revision_id": revision.revision_id,
        "previous_revision_id": revision.previous_revision_id,
        "case_hash": revision.case_hash,
        "evidence_digest": revision.evidence_digest,
        "readiness_digest": revision.readiness_digest,
        "authorization_id": revision.authorization_id,
    }


def decision_to_dict(decision: DecisionRecord) -> dict:
    return {
        "decision_id": decision.decision_id,
        "category": decision.category.value,
        "summary": decision.summary,
        "timestamp": decision.timestamp,
    }


def execution_to_dict(execution: ExecutionRecord) -> dict:
    return {
        "execution_id": execution.execution_id,
        "revision_id": execution.revision_id,
        "engine_name": execution.engine_name,
        "result_status": execution.result_status,
        "result_artifact": execution.result_artifact,
        "report_artifact": execution.report_artifact,
        "executed_utc": execution.executed_utc,
    }


def case_history_to_dict(history: CaseHistory) -> dict:
    """Deterministic dict form (stable key order within each record)."""
    return {
        "schema_version": history.schema_version,
        "revisions": [revision_to_dict(r) for r in history.revisions],
        "decisions": [decision_to_dict(d) for d in history.decisions],
        "executions": [execution_to_dict(e) for e in history.executions],
    }


def _require_mapping(raw: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise HistoryValidationError(
            f"{label} must be a JSON object; got {type(raw).__name__}."
        )
    return raw


def revision_from_dict(raw: Mapping[str, Any]) -> CaseRevision:
    data = _require_mapping(raw, "revision")
    try:
        return CaseRevision(
            revision_number=int(data["revision_number"]),
            revision_id=str(data["revision_id"]),
            previous_revision_id=(
                None if data["previous_revision_id"] is None
                else str(data["previous_revision_id"])
            ),
            case_hash=str(data["case_hash"]),
            evidence_digest=str(data["evidence_digest"]),
            readiness_digest=(
                None if data.get("readiness_digest") is None
                else str(data["readiness_digest"])
            ),
            authorization_id=(
                None if data.get("authorization_id") is None
                else str(data["authorization_id"])
            ),
        )
    except KeyError as exc:
        raise HistoryValidationError(
            f"revision missing required field {exc.args[0]!r}."
        ) from exc


def decision_from_dict(raw: Mapping[str, Any]) -> DecisionRecord:
    data = _require_mapping(raw, "decision")
    try:
        category = DecisionCategory(data["category"])
        return DecisionRecord(
            decision_id=str(data["decision_id"]),
            category=category,
            summary=str(data["summary"]),
            timestamp=str(data["timestamp"]),
        )
    except KeyError as exc:
        raise HistoryValidationError(
            f"decision missing required field {exc.args[0]!r}."
        ) from exc
    except ValueError as exc:
        raise HistoryValidationError(
            f"invalid decision category: {data.get('category')!r}."
        ) from exc


def execution_from_dict(raw: Mapping[str, Any]) -> ExecutionRecord:
    data = _require_mapping(raw, "execution")
    try:
        return ExecutionRecord(
            execution_id=str(data["execution_id"]),
            revision_id=str(data["revision_id"]),
            engine_name=str(data["engine_name"]),
            result_status=str(data["result_status"]),
            result_artifact=str(data["result_artifact"]),
            report_artifact=(
                None if data.get("report_artifact") is None
                else str(data["report_artifact"])
            ),
            executed_utc=str(data["executed_utc"]),
        )
    except KeyError as exc:
        raise HistoryValidationError(
            f"execution missing required field {exc.args[0]!r}."
        ) from exc


def case_history_from_dict(raw: Mapping[str, Any]) -> CaseHistory:
    """Parse a dict into :class:`CaseHistory` and verify content-derived ids."""
    data = _require_mapping(raw, "case history")
    schema_version = data.get("schema_version")
    if schema_version != HISTORY_SCHEMA_VERSION:
        raise HistoryValidationError(
            f"Unsupported history schema_version {schema_version!r}; "
            f"expected {HISTORY_SCHEMA_VERSION!r}."
        )
    revisions_raw = data.get("revisions")
    decisions_raw = data.get("decisions", [])
    executions_raw = data.get("executions", [])
    if not isinstance(revisions_raw, list):
        raise HistoryValidationError("'revisions' must be an array.")
    if not isinstance(decisions_raw, list):
        raise HistoryValidationError("'decisions' must be an array.")
    if not isinstance(executions_raw, list):
        raise HistoryValidationError("'executions' must be an array.")

    history = build_case_history(
        schema_version=schema_version,
        revisions=[revision_from_dict(r) for r in revisions_raw],
        decisions=[decision_from_dict(d) for d in decisions_raw],
        executions=[execution_from_dict(e) for e in executions_raw],
    )
    verify_record_ids(history)
    return history


# ---------------------------------------------------------------------------
# Canonical JSON + digests
# ---------------------------------------------------------------------------

def case_history_to_canonical_json(history: CaseHistory) -> str:
    """Canonical JSON (sorted keys, compact separators)."""
    return json.dumps(
        case_history_to_dict(history),
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_history_artifact_digest(history: CaseHistory) -> str:
    """SHA-256 (16 hex) of the full serialized CaseHistory (includes timestamps)."""
    return sha256_of_json_stable(case_history_to_dict(history))


def history_summary_dict(
    history: CaseHistory,
    *,
    history_artifact: str,
) -> dict:
    """Compact result-JSON ``history`` block (locked decision 7)."""
    return {
        "schema_version": history.schema_version,
        "chain_digest": compute_history_chain_digest(history),
        "artifact_digest": compute_history_artifact_digest(history),
        "revision_count": history.revision_count,
        "latest_revision_id": history.latest_revision_id,
        "execution_count": history.execution_count,
        "history_artifact": history_artifact,
    }


# ---------------------------------------------------------------------------
# Schema load / validate / file I/O
# ---------------------------------------------------------------------------

def load_history_schema() -> dict:
    """Load the checked-in JSON Schema for ossf-case-history-1.0.0."""
    path = _SCHEMA_DIR / _SCHEMA_FILENAME
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_case_history_schema(instance: Any) -> None:
    """Validate a dict against the checked-in history JSON Schema."""
    try:
        import jsonschema  # type: ignore
    except ImportError as exc:
        raise HistoryValidationError(
            "jsonschema is required for validate_case_history_schema; "
            "install project dependencies."
        ) from exc
    jsonschema.validate(instance=instance, schema=load_history_schema())


def load_case_history_json(path: Path | str) -> CaseHistory:
    """Load and parse a history artifact from disk (ids verified)."""
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError as exc:
        raise HistoryValidationError(
            f"Prior history file not found: {p}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise HistoryValidationError(
            f"Prior history file is not valid JSON ({p}): {exc.msg}"
        ) from exc
    return case_history_from_dict(raw)


def write_case_history_json(history: CaseHistory, path: Path | str) -> None:
    """Write a history artifact as indented JSON (never mutates prior in place)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(case_history_to_dict(history), f, indent=2)
        f.write("\n")


__all__ = [
    "revision_to_dict",
    "decision_to_dict",
    "execution_to_dict",
    "case_history_to_dict",
    "revision_from_dict",
    "decision_from_dict",
    "execution_from_dict",
    "case_history_from_dict",
    "case_history_to_canonical_json",
    "compute_history_artifact_digest",
    "history_summary_dict",
    "load_history_schema",
    "validate_case_history_schema",
    "load_case_history_json",
    "write_case_history_json",
]
