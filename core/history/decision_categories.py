"""
core/history/decision_categories.py
===================================

Decision category and outcome-code enums, plus the closed category /
event / outcome matrix for OSSF-GW-005.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Tuple

from .events import HistoryEventType


class DecisionCategory(str, Enum):
    """Engineering decision category (not a mirror of every history event)."""

    READINESS = "readiness"
    AUTHORIZATION = "authorization"
    EXECUTION = "execution"
    REPORTING = "reporting"


class DecisionOutcomeCode(str, Enum):
    """Closed outcome codes for DecisionRecord (v1)."""

    NOT_READY = "not_ready"
    DENIED = "denied"
    PROCEED = "proceed"
    PROCEED_WITH_WARNINGS = "proceed_with_warnings"
    EXECUTED = "executed"
    FAILED = "failed"
    REPORT_GENERATED = "report_generated"


class CreatedReason(str, Enum):
    """Why a CaseRevision was appended."""

    INITIAL_RUN = "initial_run"
    CASE_UPDATE = "case_update"
    READINESS_REASSESSMENT = "readiness_reassessment"
    AUTHORIZATION_REASSESSMENT = "authorization_reassessment"
    RERUN = "rerun"


class AuthorityType(str, Enum):
    """Who/what issued a governed decision."""

    SYSTEM = "system"
    POLICY = "policy"
    PRACTITIONER = "practitioner"


class ExecutionStatus(str, Enum):
    """Closed execution outcome for ExecutionRecord."""

    PASSED = "passed"
    FAILED = "failed"


# (category, event_type, outcome_code) — only these combinations validate.
ALLOWED_DECISION_COMBINATIONS: FrozenSet[
    Tuple[DecisionCategory, HistoryEventType, DecisionOutcomeCode]
] = frozenset({
    (
        DecisionCategory.READINESS,
        HistoryEventType.READINESS_NOT_READY,
        DecisionOutcomeCode.NOT_READY,
    ),
    (
        DecisionCategory.AUTHORIZATION,
        HistoryEventType.AUTHORIZATION_DENIED,
        DecisionOutcomeCode.DENIED,
    ),
    (
        DecisionCategory.AUTHORIZATION,
        HistoryEventType.AUTHORIZATION_PROCEEDED,
        DecisionOutcomeCode.PROCEED,
    ),
    (
        DecisionCategory.AUTHORIZATION,
        HistoryEventType.AUTHORIZATION_PROCEEDED_WITH_WARNINGS,
        DecisionOutcomeCode.PROCEED_WITH_WARNINGS,
    ),
    (
        DecisionCategory.EXECUTION,
        HistoryEventType.SCREENING_EXECUTED,
        DecisionOutcomeCode.EXECUTED,
    ),
    (
        DecisionCategory.EXECUTION,
        HistoryEventType.SCREENING_FAILED,
        DecisionOutcomeCode.FAILED,
    ),
    (
        DecisionCategory.REPORTING,
        HistoryEventType.REPORT_GENERATED,
        DecisionOutcomeCode.REPORT_GENERATED,
    ),
})


def is_allowed_decision_combination(
    category: DecisionCategory,
    event_type: HistoryEventType,
    outcome_code: DecisionOutcomeCode,
) -> bool:
    return (category, event_type, outcome_code) in ALLOWED_DECISION_COMBINATIONS


__all__ = [
    "DecisionCategory",
    "DecisionOutcomeCode",
    "CreatedReason",
    "AuthorityType",
    "ExecutionStatus",
    "ALLOWED_DECISION_COMBINATIONS",
    "is_allowed_decision_combination",
]
