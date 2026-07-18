"""
test_history_digest.py
======================

Split digests for CaseHistory (OSSF-GW-005 locked decision 6C):

* ``history_chain_digest`` — content-only; excludes timestamps
* ``history_artifact_digest`` — full serialized instance; includes timestamps
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.governance import sha256_of_json_stable
from core.history import (
    DecisionCategory,
    build_case_history,
    build_decision,
    build_execution,
    build_revision,
    case_history_to_dict,
    compute_history_artifact_digest,
    compute_history_chain_digest,
    history_chain_digest_payload,
    history_summary_dict,
)


def _history(ts_decision: str, ts_exec: str):
    rev = build_revision(
        revision_number=1,
        previous_revision_id=None,
        case_hash="0123456789abcdef",
        evidence_digest="fedcba9876543210",
        readiness_digest="aaaabbbbccccdddd",
        authorization_id="1111222233334444",
    )
    dec = build_decision(
        category=DecisionCategory.EXECUTION,
        summary="Authorized screening executed.",
        timestamp=ts_decision,
    )
    exe = build_execution(
        revision_id=rev.revision_id,
        engine_name="ogata_banks_1d",
        result_status="pass",
        result_artifact="output/EX-001_results.json",
        report_artifact="output/EX-001_report.txt",
        executed_utc=ts_exec,
    )
    return build_case_history(revisions=[rev], decisions=[dec], executions=[exe])


def test_chain_digest_is_sixteen_hex_and_deterministic():
    h = _history("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00")
    d1 = compute_history_chain_digest(h)
    d2 = compute_history_chain_digest(h)
    assert d1 == d2
    assert len(d1) == 16
    assert all(c in "0123456789abcdef" for c in d1)


def test_chain_digest_excludes_timestamps():
    a = _history("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:01+00:00")
    b = _history("2099-12-31T23:59:59+00:00", "2099-12-31T23:59:59+00:00")
    assert compute_history_chain_digest(a) == compute_history_chain_digest(b)
    payload = history_chain_digest_payload(a)
    assert "timestamp" not in payload["decisions"][0]
    assert "executed_utc" not in payload["executions"][0]


def test_artifact_digest_includes_timestamps():
    a = _history("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:01+00:00")
    b = _history("2099-12-31T23:59:59+00:00", "2099-12-31T23:59:59+00:00")
    assert compute_history_artifact_digest(a) != compute_history_artifact_digest(b)
    assert compute_history_chain_digest(a) == compute_history_chain_digest(b)


def test_artifact_digest_matches_sha256_of_json_stable():
    h = _history("2026-07-18T00:00:00+00:00", "2026-07-18T00:00:01+00:00")
    assert compute_history_artifact_digest(h) == sha256_of_json_stable(
        case_history_to_dict(h)
    )


def test_chain_digest_matches_payload_hash():
    h = _history("2026-07-18T00:00:00+00:00", "2026-07-18T00:00:01+00:00")
    assert compute_history_chain_digest(h) == sha256_of_json_stable(
        history_chain_digest_payload(h)
    )


def test_chain_digest_changes_with_revision_content():
    base = _history("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00")
    rev = build_revision(
        revision_number=1,
        previous_revision_id=None,
        case_hash="ffffffffffffffff",
        evidence_digest="fedcba9876543210",
        readiness_digest="aaaabbbbccccdddd",
        authorization_id="1111222233334444",
    )
    other = build_case_history(
        revisions=[rev],
        decisions=base.decisions,
        executions=[
            build_execution(
                revision_id=rev.revision_id,
                engine_name="ogata_banks_1d",
                result_status="pass",
                result_artifact="output/EX-001_results.json",
                report_artifact="output/EX-001_report.txt",
                executed_utc="2026-01-01T00:00:01+00:00",
            )
        ],
    )
    assert compute_history_chain_digest(base) != compute_history_chain_digest(other)


def test_history_summary_dict_fields():
    h = _history("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00")
    summary = history_summary_dict(h, history_artifact="output/EX-001_history.json")
    assert summary == {
        "schema_version": h.schema_version,
        "chain_digest": compute_history_chain_digest(h),
        "artifact_digest": compute_history_artifact_digest(h),
        "revision_count": 1,
        "latest_revision_id": h.latest_revision_id,
        "execution_count": 1,
        "history_artifact": "output/EX-001_history.json",
    }


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
