"""
core/readiness/errors.py
========================

Exceptions for the practitioner readiness workflow (OSSF-GW-004).
"""

from __future__ import annotations


class ReadinessError(RuntimeError):
    """Base class for readiness-workflow failures."""


class ReadinessNotReadyError(ReadinessError):
    """Raised when a case is not ready for authorization / screening.

    Distinct from evidence-layer failures (exit 1, evidence-failure artifact)
    and from preflight refusal (exit 2). The driver writes a readiness-failure
    artifact and exits 1 without running preflight or physics.
    """

    def __init__(self, assessment, message: str | None = None):
        self.assessment = assessment
        if message is None:
            message = (
                f"Practitioner readiness disposition is "
                f"'{getattr(assessment, 'disposition', 'not_ready')}'; "
                "screening is not authorizable (OSSF-GW-004)."
            )
        super().__init__(message)


__all__ = [
    "ReadinessError",
    "ReadinessNotReadyError",
]
