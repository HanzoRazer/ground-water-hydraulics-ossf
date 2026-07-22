"""
test_history_serialization.py
=============================

Serialization, digests, schema, and prior-history validation (OSSF-GW-005).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.history import (
    HISTORY_SCHEMA_VERSION,
    AuthorityRecord,
    AuthorityType,
    CaseRevision,
    CreatedReason,
    DecisionCategory,
    DecisionOutcomeCode,
    DecisionRecord,
    HistoryEventType,
    HistoryIdentityError,
    HistoryValidationError,
    derive_decision_id,
    derive_history_id,
    derive_revision_id,
)
from core.history.digest import (
    compute_history_artifact_digest,
    compute_history_chain_digest,
    stamp_history_digests,
)
from core.history.serialization import (
    history_from_dict,
    history_to_dict,
    load_history,
    serialize_history,
    write_history,
)
from core.history.validate import (
    load_and_validate_history,
    validate_against_json_schema,
    validate_history_object,
)


def _authority():
    return AuthorityRecord(
        authority_type=AuthorityType.SYSTEM,
        authority_id="core.readiness",
    )


def _make_history(*, site_id="EX-001", site_digest=None, with_decision=True):
    site_digest = site_digest or ("a" * 16)
    evidence = "b" * 16
    readiness = "c" * 16
    hid = derive_history_id(site_id=site_id, initial_site_digest=site_digest)
    rid = derive_revision_id(
        history_id=hid,
        revision_number=1,
        parent_revision_id=None,
        site_digest=site_digest,
        evidence_digest=evidence,
        readiness_digest=readiness,
        authorization_id=None,
        created_reason=CreatedReason.INITIAL_RUN.value,
    )
    rev = CaseRevision(
        revision_id=rid,
        revision_number=1,
        parent_revision_id=None,
        site_digest=site_digest,
        evidence_digest=evidence,
        readiness_digest=readiness,
        authorization_id=None,
        result_digest=None,
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T12:00:00Z",
    )
    decisions = []
    if with_decision:
        related = ("RDY-004",)
        did = derive_decision_id(
            revision_id=rid,
            sequence=1,
            category=DecisionCategory.READINESS.value,
            event_type=HistoryEventType.READINESS_NOT_READY.value,
            authority=_authority().to_dict(),
            outcome_code=DecisionOutcomeCode.NOT_READY.value,
            related_ids=related,
        )
        decisions.append(DecisionRecord(
            decision_id=did,
            sequence=1,
            category=DecisionCategory.READINESS,
            event_type=HistoryEventType.READINESS_NOT_READY,
            authority=_authority(),
            outcome_code=DecisionOutcomeCode.NOT_READY,
            summary="Critical binding not accepted",
            related_revision_id=rid,
            related_ids=related,
        ))
    return stamp_history_digests(
        history_id=hid,
        site_id=site_id,
        revisions=[rev],
        decisions=decisions,
        executions=[],
        serialize_fn=history_to_dict,
    )


def test_chain_digest_excludes_timestamps():
    h = _make_history()
    chain = compute_history_chain_digest(
        history_id=h.history_id,
        revisions=h.revisions,
        decisions=h.decisions,
        executions=h.executions,
    )
    assert chain == h.history_chain_digest
    # Mutating created_utc must not change chain digest.
    rev = h.revisions[0]
    mutated = CaseRevision(
        revision_id=rev.revision_id,
        revision_number=rev.revision_number,
        parent_revision_id=rev.parent_revision_id,
        site_digest=rev.site_digest,
        evidence_digest=rev.evidence_digest,
        readiness_digest=rev.readiness_digest,
        authorization_id=rev.authorization_id,
        result_digest=rev.result_digest,
        created_reason=rev.created_reason,
        created_utc="2099-01-01T00:00:00Z",
    )
    chain2 = compute_history_chain_digest(
        history_id=h.history_id,
        revisions=[mutated],
        decisions=h.decisions,
        executions=h.executions,
    )
    assert chain2 == chain


def test_artifact_digest_includes_timestamps_and_chain():
    h = _make_history()
    serialized = history_to_dict(h)
    assert compute_history_artifact_digest(serialized) == h.history_artifact_digest
    # Changing created_utc changes artifact digest but not chain digest.
    rev = h.revisions[0]
    mutated_rev = CaseRevision(
        revision_id=rev.revision_id,
        revision_number=rev.revision_number,
        parent_revision_id=rev.parent_revision_id,
        site_digest=rev.site_digest,
        evidence_digest=rev.evidence_digest,
        readiness_digest=rev.readiness_digest,
        authorization_id=rev.authorization_id,
        result_digest=rev.result_digest,
        created_reason=rev.created_reason,
        created_utc="2099-01-01T00:00:00Z",
    )
    h2 = stamp_history_digests(
        history_id=h.history_id,
        site_id=h.site_id,
        revisions=[mutated_rev],
        decisions=h.decisions,
        executions=[],
        serialize_fn=history_to_dict,
    )
    assert h2.history_chain_digest == h.history_chain_digest
    assert h2.history_artifact_digest != h.history_artifact_digest


def test_round_trip_serialization(tmp_path):
    h = _make_history()
    path = tmp_path / "EX-001_history.json"
    write_history(h, path)
    loaded = load_and_validate_history(path, expected_site_id="EX-001")
    assert loaded.history_id == h.history_id
    assert loaded.history_chain_digest == h.history_chain_digest
    assert history_to_dict(loaded) == history_to_dict(h)


def test_stable_json_ordering():
    h = _make_history()
    a = serialize_history(h)
    b = serialize_history(h)
    assert a == b
    raw = json.loads(a)
    assert list(raw.keys()) == sorted(raw.keys())


def test_json_schema_accepts_valid_history():
    h = _make_history()
    validate_against_json_schema(history_to_dict(h))


def test_json_schema_rejects_bad_schema_version():
    h = _make_history()
    raw = history_to_dict(h)
    raw["schema_version"] = "screening-case-history-0.0.0"
    with pytest.raises(HistoryValidationError, match="schema validation"):
        validate_against_json_schema(raw)


def test_site_id_mismatch_rejected(tmp_path):
    h = _make_history(site_id="EX-001")
    path = tmp_path / "hist.json"
    write_history(h, path)
    with pytest.raises(HistoryIdentityError, match="site_id"):
        load_and_validate_history(path, expected_site_id="EX-OTHER")


def test_tampered_chain_digest_rejected(tmp_path):
    h = _make_history()
    raw = history_to_dict(h)
    raw["history_chain_digest"] = "0" * 16
    path = tmp_path / "hist.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(HistoryValidationError, match="history_chain_digest"):
        load_and_validate_history(path)


def test_broken_parent_linkage_rejected():
    h = _make_history()
    # Fabricate a second revision with wrong parent.
    r1 = h.revisions[0]
    bad_parent = "f" * 16
    r2_id = derive_revision_id(
        history_id=h.history_id,
        revision_number=2,
        parent_revision_id=bad_parent,
        site_digest="d" * 16,
        evidence_digest="b" * 16,
        readiness_digest="c" * 16,
        authorization_id=None,
        created_reason=CreatedReason.CASE_UPDATE.value,
    )
    r2 = CaseRevision(
        revision_id=r2_id,
        revision_number=2,
        parent_revision_id=bad_parent,
        site_digest="d" * 16,
        evidence_digest="b" * 16,
        readiness_digest="c" * 16,
        authorization_id=None,
        result_digest=None,
        created_reason=CreatedReason.CASE_UPDATE,
        created_utc="2026-07-21T13:00:00Z",
    )
    broken = stamp_history_digests(
        history_id=h.history_id,
        site_id=h.site_id,
        revisions=[r1, r2],
        decisions=h.decisions,
        executions=[],
        serialize_fn=history_to_dict,
    )
    with pytest.raises(HistoryValidationError, match="parent_revision_id"):
        validate_history_object(broken)


def test_invalid_json_prior_history(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(HistoryValidationError, match="invalid JSON"):
        load_history(path)


def test_history_id_mismatch_rejected():
    h = _make_history()
    raw = history_to_dict(h)
    raw["history_id"] = "0" * 16
    parsed = history_from_dict(raw)
    with pytest.raises((HistoryIdentityError, HistoryValidationError)):
        validate_history_object(parsed)
