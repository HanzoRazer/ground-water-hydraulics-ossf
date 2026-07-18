"""
core/history/errors.py
======================

Typed exceptions for the governed case-history / decision ledger
(OSSF-GW-005).
"""

from __future__ import annotations


class HistoryError(RuntimeError):
    """Base class for case-history failures."""


class HistoryValidationError(HistoryError):
    """Raised when a history record fails structural or content validation.

    Examples: invalid content-derived id, empty revision chain, bad
    schema_version, or a digest that does not recompute.
    """


class HistoryChainError(HistoryError):
    """Raised when the append-only revision chain is broken.

    Examples: non-increasing revision numbers, mismatched
    ``previous_revision_id``, or duplicate ``revision_id`` values.
    """


__all__ = [
    "HistoryError",
    "HistoryValidationError",
    "HistoryChainError",
]
