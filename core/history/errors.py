"""
core/history/errors.py
======================

Typed exceptions for the governed case history ledger (OSSF-GW-005).
"""

from __future__ import annotations


class HistoryError(RuntimeError):
    """Base class for case-history failures."""


class HistoryContractError(HistoryError):
    """Frozen-record construction or enum/matrix contract violation."""


class HistoryConstructionError(HistoryError):
    """Builder could not assemble a valid revision (missing required digests)."""


class HistoryValidationError(HistoryError):
    """Loaded prior history failed schema, identity, or chain checks."""

    def __init__(self, message: str, *, path: str | None = None):
        self.path = path
        if path:
            message = f"{path}: {message}"
        super().__init__(message)


class HistoryIdentityError(HistoryValidationError):
    """site_id / history_id / chain identity incompatibility."""


__all__ = [
    "HistoryError",
    "HistoryContractError",
    "HistoryConstructionError",
    "HistoryValidationError",
    "HistoryIdentityError",
]
