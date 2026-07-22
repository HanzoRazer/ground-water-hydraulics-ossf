"""
core/history
============

Governed case history and decision ledger (OSSF-GW-005).

Observational only: records revision chronology, engineering decisions,
execution outcomes, and artifact lineage. Never authorizes, validates, or
interprets engineering data. Append-only, file-based, no persistence layer.
"""

from .builder import (
    AuthorizationDenial,
    ExecutionOutcome,
    append_revision,
    build_history,
    compute_result_digest,
    revision_lookup,
    semantic_result_payload,
)
from .decision_categories import (
    ALLOWED_DECISION_COMBINATIONS,
    AuthorityType,
    CreatedReason,
    DecisionCategory,
    DecisionOutcomeCode,
    ExecutionStatus,
    is_allowed_decision_combination,
)
from .digest import (
    compute_history_artifact_digest,
    compute_history_chain_digest,
    stamp_history_digests,
)
from .errors import (
    HistoryConstructionError,
    HistoryContractError,
    HistoryError,
    HistoryIdentityError,
    HistoryValidationError,
)
from .events import HistoryEventType
from .identity import (
    HISTORY_SCHEMA_VERSION,
    canonical_artifact_bindings,
    derive_decision_id,
    derive_execution_id,
    derive_history_id,
    derive_revision_id,
)
from .models import (
    ArtifactBinding,
    AuthorityRecord,
    CaseHistory,
    CaseRevision,
    DecisionRecord,
    ExecutionRecord,
)
from .serialization import (
    history_from_dict,
    history_to_dict,
    load_history,
    serialize_history,
    write_history,
)
from .validate import (
    load_and_validate_history,
    validate_against_json_schema,
    validate_history_dict,
    validate_history_object,
)

__all__ = [
    "HISTORY_SCHEMA_VERSION",
    "HistoryEventType",
    "DecisionCategory",
    "DecisionOutcomeCode",
    "CreatedReason",
    "AuthorityType",
    "ExecutionStatus",
    "ALLOWED_DECISION_COMBINATIONS",
    "is_allowed_decision_combination",
    "HistoryError",
    "HistoryContractError",
    "HistoryConstructionError",
    "HistoryValidationError",
    "HistoryIdentityError",
    "AuthorityRecord",
    "ArtifactBinding",
    "CaseRevision",
    "DecisionRecord",
    "ExecutionRecord",
    "CaseHistory",
    "AuthorizationDenial",
    "ExecutionOutcome",
    "derive_history_id",
    "derive_revision_id",
    "derive_decision_id",
    "derive_execution_id",
    "canonical_artifact_bindings",
    "compute_history_chain_digest",
    "compute_history_artifact_digest",
    "stamp_history_digests",
    "history_to_dict",
    "history_from_dict",
    "serialize_history",
    "load_history",
    "write_history",
    "validate_history_object",
    "validate_history_dict",
    "load_and_validate_history",
    "validate_against_json_schema",
    "semantic_result_payload",
    "compute_result_digest",
    "build_history",
    "append_revision",
    "revision_lookup",
]
