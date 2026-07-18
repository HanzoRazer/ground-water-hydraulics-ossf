"""
test_case_history.py
====================

Immutable case-history contracts (OSSF-GW-005): revision / decision /
execution creation, content-derived ids, and immutability.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.history import (
    HISTORY_SCHEMA_VERSION,
    CaseHistory,
    CaseRevision,
    DecisionCategory,
    DecisionRecord,
    ExecutionRecord,
    HistoryChainError,
    HistoryEventType,
    HistoryValidationError,
    append_to_history,
    build_case_history,
    build_decision,
    build_execution,
    build_revision,
    compute_history_chain_digest,
    decision_for_event,
    derive_decision_id,
    derive_execution_id,
    derive_revision_id,
    history_chain_digest_payload,
    validate_case_history,
    validate_revision_chain,
    verify_record_ids,
)


def _rev1(**overrides) -> CaseRevision:
    kwargs = dict(
        revision_number=1,
        previous_revision_id=None,
        case_hash="casehash00000001",
        evidence_digest="evidigest0000001",
        readiness_digest="readydigest00001",
        authorization_id=None,
    )
    kwargs.update(overrides)
    return build_revision(**kwargs)


# ---------------------------------------------------------------------------
# Creation + content-derived ids
# ---------------------------------------------------------------------------

def test_build_revision_derives_deterministic_id():
    a = _rev1()
    b = _rev1()
    assert a.revision_id == b.revision_id
    assert len(a.revision_id) == 16
    assert a.revision_id == derive_revision_id(
        revision_number=1,
        previous_revision_id=None,
        case_hash="casehash00000001",
        evidence_digest="evidigest0000001",
        readiness_digest="readydigest00001",
        authorization_id=None,
    )


def test_revision_id_changes_with_content():
    a = _rev1(case_hash="aaa")
    b = _rev1(case_hash="bbb")
    assert a.revision_id != b.revision_id


def test_build_decision_excludes_timestamp_from_id():
    d1 = build_decision(
        category=DecisionCategory.AUTHORIZATION,
        summary="denied",
        timestamp="2020-01-01T00:00:00+00:00",
    )
    d2 = build_decision(
        category=DecisionCategory.AUTHORIZATION,
        summary="denied",
        timestamp="2026-07-18T12:00:00+00:00",
    )
    assert d1.decision_id == d2.decision_id
    assert d1.timestamp != d2.timestamp
    assert d1.decision_id == derive_decision_id(
        category=DecisionCategory.AUTHORIZATION, summary="denied"
    )


def test_build_execution_excludes_executed_utc_from_id():
    rev = _rev1(authorization_id="authid0000000001")
    e1 = build_execution(
        revision_id=rev.revision_id,
        engine_name="ogata_banks_1d",
        result_status="pass",
        result_artifact="output/EX-001_results.json",
        report_artifact="output/EX-001_report.txt",
        executed_utc="2020-01-01T00:00:00+00:00",
    )
    e2 = build_execution(
        revision_id=rev.revision_id,
        engine_name="ogata_banks_1d",
        result_status="pass",
        result_artifact="output/EX-001_results.json",
        report_artifact="output/EX-001_report.txt",
        executed_utc="2026-07-18T12:00:00+00:00",
    )
    assert e1.execution_id == e2.execution_id
    assert e1.executed_utc != e2.executed_utc
    assert e1.execution_id == derive_execution_id(
        revision_id=rev.revision_id,
        engine_name="ogata_banks_1d",
        result_status="pass",
        result_artifact="output/EX-001_results.json",
        report_artifact="output/EX-001_report.txt",
    )


def test_build_case_history_and_properties():
    rev = _rev1()
    dec = decision_for_event(HistoryEventType.AUTHORIZATION_DENIED)
    hist = build_case_history(revisions=[rev], decisions=[dec], executions=[])
    assert hist.schema_version == HISTORY_SCHEMA_VERSION
    assert hist.revision_count == 1
    assert hist.execution_count == 0
    assert hist.latest_revision_id == rev.revision_id
    assert isinstance(hist, CaseHistory)


def test_decision_for_event_maps_categories():
    d = decision_for_event(HistoryEventType.AUTHORIZATION_DENIED)
    assert d.category == DecisionCategory.AUTHORIZATION
    assert "denied" in d.summary.lower() or "not run" in d.summary.lower()
    e = decision_for_event(HistoryEventType.SCREENING_EXECUTED)
    assert e.category == DecisionCategory.EXECUTION


def test_enums_are_separate():
    assert set(HistoryEventType) != set(DecisionCategory)
    assert HistoryEventType.AUTHORIZATION_DENIED.value == "authorization_denied"
    assert DecisionCategory.AUTHORIZATION.value == "authorization"


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

def test_records_are_frozen():
    rev = _rev1()
    dec = build_decision(category=DecisionCategory.EVIDENCE, summary="ok")
    exe = build_execution(
        revision_id=rev.revision_id,
        engine_name="ogata_banks_1d",
        result_status="pass",
        result_artifact="output/x.json",
    )
    hist = build_case_history(revisions=[rev], decisions=[dec], executions=[exe])
    for obj, field in (
        (rev, "revision_id"),
        (dec, "decision_id"),
        (exe, "execution_id"),
        (hist, "schema_version"),
    ):
        assert dataclasses.is_dataclass(obj) and obj.__dataclass_params__.frozen
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, field, "mutated")


def test_history_tuples_are_immutable():
    rev = _rev1()
    hist = build_case_history(revisions=[rev])
    assert isinstance(hist.revisions, tuple)
    assert isinstance(hist.decisions, tuple)
    assert isinstance(hist.executions, tuple)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def test_build_revision_rejects_invalid_number():
    with pytest.raises(HistoryValidationError):
        build_revision(
            revision_number=0,
            previous_revision_id=None,
            case_hash="h",
            evidence_digest="e",
        )


def test_build_execution_rejects_non_pass_fail():
    with pytest.raises(HistoryValidationError):
        build_execution(
            revision_id="r1",
            engine_name="ogata_banks_1d",
            result_status="refused",
            result_artifact="output/x.json",
        )


def test_build_case_history_requires_revision():
    with pytest.raises(HistoryValidationError):
        build_case_history(revisions=[])


def test_verify_record_ids_detects_tamper():
    rev = _rev1()
    hist = build_case_history(revisions=[rev])
    tampered = CaseHistory(
        schema_version=hist.schema_version,
        revisions=(
            CaseRevision(
                revision_number=rev.revision_number,
                revision_id="deadbeefdeadbeef",
                previous_revision_id=rev.previous_revision_id,
                case_hash=rev.case_hash,
                evidence_digest=rev.evidence_digest,
                readiness_digest=rev.readiness_digest,
                authorization_id=rev.authorization_id,
            ),
        ),
        decisions=(),
        executions=(),
    )
    with pytest.raises(HistoryValidationError, match="revision_id"):
        verify_record_ids(tampered)


def test_chain_digest_excludes_timestamps():
    rev = _rev1()
    dec = build_decision(
        category=DecisionCategory.AUTHORIZATION,
        summary="denied",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    hist = build_case_history(revisions=[rev], decisions=[dec])
    payload = history_chain_digest_payload(hist)
    assert "timestamp" not in payload["decisions"][0]
    assert "executed_utc" not in str(payload)
    digest = compute_history_chain_digest(hist)
    assert len(digest) == 16
    # Same content, different timestamps → same chain digest
    dec2 = build_decision(
        category=DecisionCategory.AUTHORIZATION,
        summary="denied",
        timestamp="2099-01-01T00:00:00+00:00",
    )
    hist2 = build_case_history(revisions=[rev], decisions=[dec2])
    assert compute_history_chain_digest(hist2) == digest


# ---------------------------------------------------------------------------
# Append-only revision chain
# ---------------------------------------------------------------------------

def test_validate_revision_chain_accepts_single_revision():
    hist = build_case_history(revisions=[_rev1()])
    validate_revision_chain(hist)
    validate_case_history(hist)


def test_validate_rejects_non_starting_number():
    rev = build_revision(
        revision_number=2,
        previous_revision_id=None,
        case_hash="casehash00000001",
        evidence_digest="evidigest0000001",
    )
    hist = CaseHistory(
        schema_version=HISTORY_SCHEMA_VERSION,
        revisions=(rev,),
        decisions=(),
        executions=(),
    )
    with pytest.raises(HistoryChainError, match="strictly increasing"):
        validate_revision_chain(hist)


def test_validate_rejects_first_with_previous_id():
    # Build a content-valid revision that claims a previous id incorrectly.
    rev = CaseRevision(
        revision_number=1,
        revision_id=derive_revision_id(
            revision_number=1,
            previous_revision_id="aaaaaaaaaaaaaaaa",
            case_hash="casehash00000001",
            evidence_digest="evidigest0000001",
            readiness_digest=None,
            authorization_id=None,
        ),
        previous_revision_id="aaaaaaaaaaaaaaaa",
        case_hash="casehash00000001",
        evidence_digest="evidigest0000001",
        readiness_digest=None,
        authorization_id=None,
    )
    hist = CaseHistory(
        schema_version=HISTORY_SCHEMA_VERSION,
        revisions=(rev,),
        decisions=(),
        executions=(),
    )
    with pytest.raises(HistoryChainError, match="previous_revision_id=None"):
        validate_revision_chain(hist)


def test_validate_rejects_broken_previous_link():
    r1 = _rev1()
    r2 = build_revision(
        revision_number=2,
        previous_revision_id="deadbeefdeadbeef",
        case_hash="casehash00000002",
        evidence_digest="evidigest0000002",
        readiness_digest="readydigest00002",
        authorization_id="authid0000000002",
    )
    hist = CaseHistory(
        schema_version=HISTORY_SCHEMA_VERSION,
        revisions=(r1, r2),
        decisions=(),
        executions=(),
    )
    with pytest.raises(HistoryChainError, match="previous_revision_id"):
        validate_revision_chain(hist)


def test_validate_rejects_duplicate_revision_ids():
    r1 = _rev1()
    # Second revision with same id but wrong number — force duplicate id.
    r2 = CaseRevision(
        revision_number=2,
        revision_id=r1.revision_id,
        previous_revision_id=r1.revision_id,
        case_hash="casehash00000002",
        evidence_digest="evidigest0000002",
        readiness_digest=None,
        authorization_id=None,
    )
    hist = CaseHistory(
        schema_version=HISTORY_SCHEMA_VERSION,
        revisions=(r1, r2),
        decisions=(),
        executions=(),
    )
    with pytest.raises(HistoryChainError, match="duplicate revision_id"):
        validate_revision_chain(hist)


def test_validate_rejects_invalid_content_hash_as_validation_error():
    rev = _rev1()
    hist = CaseHistory(
        schema_version=HISTORY_SCHEMA_VERSION,
        revisions=(
            CaseRevision(
                revision_number=1,
                revision_id="0123456789abcdef",
                previous_revision_id=None,
                case_hash=rev.case_hash,
                evidence_digest=rev.evidence_digest,
                readiness_digest=rev.readiness_digest,
                authorization_id=rev.authorization_id,
            ),
        ),
        decisions=(),
        executions=(),
    )
    with pytest.raises(HistoryValidationError, match="revision_id"):
        validate_revision_chain(hist)


def test_append_to_history_extends_chain():
    prior = build_case_history(
        revisions=[_rev1()],
        decisions=[decision_for_event(HistoryEventType.AUTHORIZATION_DENIED)],
    )
    extended = append_to_history(
        prior,
        case_hash="casehash00000002",
        evidence_digest="evidigest0000002",
        readiness_digest="readydigest00002",
        authorization_id="authid0000000002",
        decisions=[
            decision_for_event(HistoryEventType.AUTHORIZATION_GRANTED),
        ],
    )
    assert extended.revision_count == 2
    assert extended.revisions[1].previous_revision_id == prior.latest_revision_id
    assert extended.revisions[1].revision_number == 2
    assert len(extended.decisions) == 2
    validate_case_history(extended)


def test_append_to_history_validates_prior_first():
    broken = CaseHistory(
        schema_version=HISTORY_SCHEMA_VERSION,
        revisions=(
            CaseRevision(
                revision_number=1,
                revision_id="0123456789abcdef",
                previous_revision_id=None,
                case_hash="casehash00000001",
                evidence_digest="evidigest0000001",
                readiness_digest=None,
                authorization_id=None,
            ),
        ),
        decisions=(),
        executions=(),
    )
    with pytest.raises(HistoryValidationError):
        append_to_history(
            broken,
            case_hash="casehash00000002",
            evidence_digest="evidigest0000002",
        )


def test_append_execution_must_bind_new_revision():
    prior = build_case_history(revisions=[_rev1()])
    orphan = build_execution(
        revision_id=prior.latest_revision_id,
        engine_name="ogata_banks_1d",
        result_status="pass",
        result_artifact="output/x.json",
    )
    with pytest.raises(HistoryValidationError, match="new revision_id"):
        append_to_history(
            prior,
            case_hash="casehash00000002",
            evidence_digest="evidigest0000002",
            authorization_id="authid0000000002",
            executions=[orphan],
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
