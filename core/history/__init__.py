"""
core/history
============

Governed case history and decision ledger (OSSF-GW-005).

Observational only: records revision chronology, engineering decisions,
execution outcomes, and artifact lineage. Never authorizes, validates, or
interprets engineering data. Append-only, file-based, no persistence layer.
"""

from .decision_categories import (
    ALLOWED_DECISION_COMBINATIONS,
    AuthorityType,
    CreatedReason,
    DecisionCategory,
    DecisionOutcomeCode,
    ExecutionStatus,
    is_allowed_decision_combination,
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
    "derive_history_id",
    "derive_revision_id",
    "derive_decision_id",
    "derive_execution_id",
    "canonical_artifact_bindings",
]
