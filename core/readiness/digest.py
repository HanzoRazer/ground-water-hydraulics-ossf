"""
core/readiness/digest.py
========================

Deterministic ``readiness_digest`` for the practitioner readiness assessment
(OSSF-GW-004). Same 16-hex ``sha256_of_json_stable`` style as evidence and
authorization digests. Wall-clock timestamps are excluded from the payload.
"""

from __future__ import annotations

from typing import Iterable

from ..governance import sha256_of_json_stable

READINESS_SCHEMA_VERSION = "screening-readiness-1.0.0"


def _normalized_findings_for_digest(findings: Iterable) -> list:
    """Stable finding projection for the digest: id, severity, code only."""
    out = []
    for f in findings:
        out.append({
            "finding_id": getattr(f, "finding_id"),
            "severity": getattr(f, "severity"),
            "code": getattr(f, "code"),
        })
    return out


def readiness_digest_payload(
    *,
    schema_version: str,
    case_hash: str,
    evidence_digest: str,
    disposition: str,
    findings: Iterable,
) -> dict:
    """Canonical payload hashed into ``readiness_digest`` (no timestamps)."""
    return {
        "schema_version": schema_version,
        "case_hash": case_hash,
        "evidence_digest": evidence_digest,
        "disposition": disposition,
        "findings": _normalized_findings_for_digest(findings),
    }


def compute_readiness_digest(
    *,
    schema_version: str,
    case_hash: str,
    evidence_digest: str,
    disposition: str,
    findings: Iterable,
) -> str:
    """SHA-256 (16 hex) of the canonical readiness payload."""
    return sha256_of_json_stable(
        readiness_digest_payload(
            schema_version=schema_version,
            case_hash=case_hash,
            evidence_digest=evidence_digest,
            disposition=disposition,
            findings=findings,
        )
    )


__all__ = [
    "READINESS_SCHEMA_VERSION",
    "readiness_digest_payload",
    "compute_readiness_digest",
]
