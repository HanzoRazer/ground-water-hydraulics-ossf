"""
test_readiness_digest.py
========================

Determinism and payload-shape tests for ``readiness_digest`` (OSSF-GW-004).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import evidence_result_for, load_fixture_case, make_case
from core.contracts import validate_evidence_layer
from core.governance import sha256_of_json_stable
from core.readiness import (
    READINESS_SCHEMA_VERSION,
    READY,
    ReadinessFinding,
    assess_readiness,
    compute_readiness_digest,
    readiness_digest_payload,
)


def test_digest_is_sixteen_hex_and_deterministic():
    case = load_fixture_case("proceed")
    ev = validate_evidence_layer(case)
    a1 = assess_readiness(case, ev)
    a2 = assess_readiness(case, ev)
    assert len(a1.readiness_digest) == 16
    assert a1.readiness_digest == a2.readiness_digest
    # assessed_utc may differ; digest must ignore it.
    assert a1.assessed_utc  # factual
    assert a1.readiness_digest == compute_readiness_digest(
        schema_version=a1.schema_version,
        case_hash=a1.case_hash,
        evidence_digest=a1.evidence_digest,
        disposition=a1.disposition,
        findings=a1.findings,
    )


def test_digest_excludes_assessed_utc():
    findings = (
        ReadinessFinding("RDY-003", "warn", "pending_review", "msg", path="x"),
    )
    payload = readiness_digest_payload(
        schema_version=READINESS_SCHEMA_VERSION,
        case_hash="abc",
        evidence_digest="def",
        disposition=READY,
        findings=findings,
    )
    assert "assessed_utc" not in payload
    assert payload["findings"] == [
        {"finding_id": "RDY-003", "severity": "warn", "code": "pending_review"}
    ]
    # message/path excluded from digest projection
    assert "message" not in payload["findings"][0]
    assert "path" not in payload["findings"][0]


def test_digest_changes_with_disposition_or_findings():
    base = compute_readiness_digest(
        schema_version=READINESS_SCHEMA_VERSION,
        case_hash="h1",
        evidence_digest="e1",
        disposition=READY,
        findings=(),
    )
    with_findings = compute_readiness_digest(
        schema_version=READINESS_SCHEMA_VERSION,
        case_hash="h1",
        evidence_digest="e1",
        disposition=READY,
        findings=(
            ReadinessFinding("RDY-003", "warn", "pending_review", "m"),
        ),
    )
    assert base != with_findings


def test_digest_matches_sha256_of_json_stable():
    findings = (
        ReadinessFinding("RDY-001", "block", "evidence_not_permitting", "m"),
    )
    payload = readiness_digest_payload(
        schema_version=READINESS_SCHEMA_VERSION,
        case_hash="c",
        evidence_digest="e",
        disposition="not_ready",
        findings=findings,
    )
    assert compute_readiness_digest(
        schema_version=READINESS_SCHEMA_VERSION,
        case_hash="c",
        evidence_digest="e",
        disposition="not_ready",
        findings=findings,
    ) == sha256_of_json_stable(payload)


def test_digest_changes_when_case_hash_changes():
    a = assess_readiness(make_case(site_id="A"), evidence_result_for(make_case(site_id="A")))
    b = assess_readiness(make_case(site_id="B"), evidence_result_for(make_case(site_id="B")))
    # Bare cases → synthetic path via RDY-004 not_ready for both, but digests
    # still differ by case_hash.
    assert a.case_hash != b.case_hash
    assert a.readiness_digest != b.readiness_digest


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
