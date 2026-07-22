"""
core/history/events.py
======================

Closed history event vocabulary for the governed case history ledger
(OSSF-GW-005).

These events attach to :class:`~core.history.models.DecisionRecord` (and
execution pairing). Case creation / revision is revision chronology via
``created_reason`` + ``revision_number`` — not events and not decisions.
"""

from __future__ import annotations

from enum import Enum


class HistoryEventType(str, Enum):
    """Governed decision/execution event types (v1 closed set)."""

    READINESS_NOT_READY = "readiness_not_ready"
    AUTHORIZATION_DENIED = "authorization_denied"
    AUTHORIZATION_PROCEEDED = "authorization_proceeded"
    AUTHORIZATION_PROCEEDED_WITH_WARNINGS = "authorization_proceeded_with_warnings"
    SCREENING_EXECUTED = "screening_executed"
    SCREENING_FAILED = "screening_failed"
    REPORT_GENERATED = "report_generated"


__all__ = ["HistoryEventType"]
