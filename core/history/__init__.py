"""
core/history
============

Governed case history and engineering decision ledger (OSSF-GW-005).

Records immutable revisions, decisions, and executions for an OSSF screening
case. Does not provide persistence, collaboration, or user accounts.
"""

from .errors import HistoryChainError, HistoryError, HistoryValidationError
from .events import DecisionCategory, HistoryEventType
from .history import (
    HISTORY_SCHEMA_VERSION,
    CaseHistory,
    CaseRevision,
    DecisionRecord,
    ExecutionRecord,
    build_case_history,
    build_decision,
    build_execution,
    build_revision,
    compute_history_chain_digest,
    decision_for_event,
    derive_decision_id,
    derive_execution_id,
    derive_revision_id,
    history_chain_digest_payload,
    verify_record_ids,
)
from .serialization import (
    case_history_from_dict,
    case_history_to_canonical_json,
    case_history_to_dict,
    compute_history_artifact_digest,
    history_summary_dict,
    load_case_history_json,
    load_history_schema,
    validate_case_history_schema,
    write_case_history_json,
)

__all__ = [
    "HISTORY_SCHEMA_VERSION",
    "HistoryEventType",
    "DecisionCategory",
    "HistoryError",
    "HistoryValidationError",
    "HistoryChainError",
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
    "case_history_to_dict",
    "case_history_from_dict",
    "case_history_to_canonical_json",
    "compute_history_artifact_digest",
    "history_summary_dict",
    "load_history_schema",
    "validate_case_history_schema",
    "load_case_history_json",
    "write_case_history_json",
]
