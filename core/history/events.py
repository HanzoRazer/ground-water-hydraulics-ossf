"""
core/history/events.py
======================

Separate vocabularies for case-history chronology (OSSF-GW-005).

``HistoryEventType`` records *what happened* in the governed pipeline.
``DecisionCategory`` records *why a judgment was made*. They are intentionally
distinct enums (locked decision 5-separate) and must not be collapsed.
"""

from __future__ import annotations

from enum import Enum


class HistoryEventType(str, Enum):
    """What happened in the case chronology (pipeline event)."""

    CASE_CREATED = "case_created"
    EVIDENCE_VALIDATED = "evidence_validated"
    READINESS_ASSESSED = "readiness_assessed"
    AUTHORIZATION_GRANTED = "authorization_granted"
    AUTHORIZATION_DENIED = "authorization_denied"
    SCREENING_EXECUTED = "screening_executed"
    REPORT_EMITTED = "report_emitted"


class DecisionCategory(str, Enum):
    """Why an engineering judgment was recorded (decision ledger)."""

    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    READINESS = "readiness"
    AUTHORIZATION = "authorization"
    EXECUTION = "execution"
    REPORTING = "reporting"


__all__ = [
    "HistoryEventType",
    "DecisionCategory",
]
