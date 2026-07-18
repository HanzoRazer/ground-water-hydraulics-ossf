"""
core/readiness
==============

Practitioner readiness workflow (OSSF-GW-004).

Sits between evidence validation and preflight / authorization. Produces a
deterministic ``readiness_digest`` that authorization and attestation bind.
"""

from .assessment import (
    NOT_READY,
    PERMITTING_DISPOSITIONS,
    READY,
    READY_WITH_WARNINGS,
    ReadinessAssessment,
    ReadinessFinding,
    assess_readiness,
    readiness_failure_artifact,
    readiness_result_summary_dict,
    require_readiness,
)
from .digest import (
    READINESS_SCHEMA_VERSION,
    compute_readiness_digest,
    readiness_digest_payload,
)
from .errors import ReadinessError, ReadinessNotReadyError

__all__ = [
    "READINESS_SCHEMA_VERSION",
    "READY",
    "READY_WITH_WARNINGS",
    "NOT_READY",
    "PERMITTING_DISPOSITIONS",
    "ReadinessFinding",
    "ReadinessAssessment",
    "ReadinessError",
    "ReadinessNotReadyError",
    "assess_readiness",
    "require_readiness",
    "compute_readiness_digest",
    "readiness_digest_payload",
    "readiness_result_summary_dict",
    "readiness_failure_artifact",
]
