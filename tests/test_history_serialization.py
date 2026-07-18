"""
test_history_serialization.py
=============================

Round-trip, schema validation, and canonical ordering for CaseHistory
serialization (OSSF-GW-005).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.history import (
    HISTORY_SCHEMA_VERSION,
    DecisionCategory,
    HistoryEventType,
    HistoryValidationError,
    build_case_history,
    build_decision,
    build_execution,
    build_revision,
    case_history_from_dict,
    case_history_to_canonical_json,
    case_history_to_dict,
    decision_for_event,
    load_case_history_json,
    load_history_schema,
    validate_case_history_schema,
    write_case_history_json,
)


def _sample_history(*, with_execution: bool = False):
    rev = build_revision(
        revision_number=1,
        previous_revision_id=None,
        case_hash="0123456789abcdef",
        evidence_digest="fedcba9876543210",
        readiness_digest="aaaabbbbccccdddd",
        authorization_id=None if not with_execution else "1111222233334444",
    )
    decisions = [
        decision_for_event(
            HistoryEventType.AUTHORIZATION_DENIED
            if not with_execution
            else HistoryEventType.AUTHORIZATION_GRANTED,
            timestamp="2026-07-18T00:00:00+00:00",
        )
    ]
    executions = []
    if with_execution:
        executions.append(
            build_execution(
                revision_id=rev.revision_id,
                engine_name="ogata_banks_1d",
                result_status="pass",
                result_artifact="output/EX-001_results.json",
                report_artifact="output/EX-001_report.txt",
                executed_utc="2026-07-18T00:00:01+00:00",
            )
        )
        decisions.append(
            decision_for_event(
                HistoryEventType.SCREENING_EXECUTED,
                timestamp="2026-07-18T00:00:01+00:00",
            )
        )
    return build_case_history(
        revisions=[rev], decisions=decisions, executions=executions
    )


def test_to_dict_has_stable_top_level_keys():
    d = case_history_to_dict(_sample_history())
    assert list(d.keys()) == [
        "schema_version",
        "revisions",
        "decisions",
        "executions",
    ]
    assert d["schema_version"] == HISTORY_SCHEMA_VERSION
    rev = d["revisions"][0]
    assert list(rev.keys()) == [
        "revision_number",
        "revision_id",
        "previous_revision_id",
        "case_hash",
        "evidence_digest",
        "readiness_digest",
        "authorization_id",
    ]


def test_round_trip_dict():
    hist = _sample_history(with_execution=True)
    again = case_history_from_dict(case_history_to_dict(hist))
    assert case_history_to_dict(again) == case_history_to_dict(hist)


def test_canonical_json_is_sorted_and_stable():
    hist = _sample_history(with_execution=True)
    text = case_history_to_canonical_json(hist)
    assert text == case_history_to_canonical_json(hist)
    parsed = json.loads(text)
    assert json.dumps(parsed, sort_keys=True, separators=(",", ":")) == text


def test_schema_validates_refusal_and_execution_histories():
    for hist in (_sample_history(), _sample_history(with_execution=True)):
        d = case_history_to_dict(hist)
        validate_case_history_schema(d)


def test_schema_rejects_bad_schema_version():
    d = case_history_to_dict(_sample_history())
    d["schema_version"] = "ossf-case-history-9.9.9"
    with pytest.raises(Exception):
        validate_case_history_schema(d)


def test_from_dict_rejects_bad_schema_version():
    d = case_history_to_dict(_sample_history())
    d["schema_version"] = "nope"
    with pytest.raises(HistoryValidationError, match="schema_version"):
        case_history_from_dict(d)


def test_from_dict_rejects_tampered_revision_id():
    d = case_history_to_dict(_sample_history())
    d["revisions"][0]["revision_id"] = "0000000000000000"
    with pytest.raises(HistoryValidationError, match="revision_id"):
        case_history_from_dict(d)


def test_load_history_schema_has_const_version():
    schema = load_history_schema()
    assert schema["properties"]["schema_version"]["const"] == HISTORY_SCHEMA_VERSION


def test_write_and_load_round_trip(tmp_path):
    hist = _sample_history(with_execution=True)
    path = tmp_path / "EX-001_history.json"
    write_case_history_json(hist, path)
    loaded = load_case_history_json(path)
    assert case_history_to_dict(loaded) == case_history_to_dict(hist)
    validate_case_history_schema(json.loads(path.read_text(encoding="utf-8")))


def test_decision_category_serializes_as_string():
    d = case_history_to_dict(_sample_history())
    assert d["decisions"][0]["category"] == DecisionCategory.AUTHORIZATION.value


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
