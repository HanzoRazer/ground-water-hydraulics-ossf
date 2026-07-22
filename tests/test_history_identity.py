"""
test_history_identity.py
========================

Deterministic ID derivation and frozen contract checks for OSSF-GW-005.
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
    HISTORY_SCHEMA_VERSION,
    ALLOWED_DECISION_COMBINATIONS,
    AuthorityRecord,
    AuthorityType,
    ArtifactBinding,
    CaseRevision,
    CreatedReason,
    DecisionCategory,
    DecisionOutcomeCode,
    DecisionRecord,
    ExecutionRecord,
    ExecutionStatus,
    HistoryContractError,
    HistoryEventType,
    canonical_artifact_bindings,
    derive_decision_id,
    derive_execution_id,
    derive_history_id,
    derive_revision_id,
)


def test_history_schema_version():
    assert HISTORY_SCHEMA_VERSION == "screening-case-history-1.0.0"


def test_history_id_stable_across_calls():
    a = derive_history_id(site_id="EX-001", initial_site_digest="a" * 16)
    b = derive_history_id(site_id="EX-001", initial_site_digest="a" * 16)
    assert a == b
    assert len(a) == 16
    assert a == sha256_of_json_stable({
        "schema_version": HISTORY_SCHEMA_VERSION,
        "site_id": "EX-001",
        "initial_site_digest": "a" * 16,
    })


def test_history_id_changes_with_site_or_initial_digest():
    base = derive_history_id(site_id="EX-001", initial_site_digest="a" * 16)
    other_site = derive_history_id(site_id="EX-002", initial_site_digest="a" * 16)
    other_digest = derive_history_id(site_id="EX-001", initial_site_digest="b" * 16)
    assert base != other_site
    assert base != other_digest


def test_revision_id_includes_explicit_nulls():
    # Authorization not reached — authorization_id must be JSON null in material.
    with_null = derive_revision_id(
        history_id="c" * 16,
        revision_number=1,
        parent_revision_id=None,
        site_digest="d" * 16,
        evidence_digest="e" * 16,
        readiness_digest="f" * 16,
        authorization_id=None,
        created_reason=CreatedReason.INITIAL_RUN.value,
    )
    # Empty string must NOT be treated as equivalent to null.
    with_empty = derive_revision_id(
        history_id="c" * 16,
        revision_number=1,
        parent_revision_id=None,
        site_digest="d" * 16,
        evidence_digest="e" * 16,
        readiness_digest="f" * 16,
        authorization_id="",
        created_reason=CreatedReason.INITIAL_RUN.value,
    )
    assert with_null != with_empty
    assert len(with_null) == 16


def test_revision_id_parent_and_number_affect_identity():
    common = dict(
        history_id="c" * 16,
        site_digest="d" * 16,
        evidence_digest="e" * 16,
        readiness_digest="f" * 16,
        authorization_id="a" * 16,
        created_reason=CreatedReason.CASE_UPDATE.value,
    )
    r1 = derive_revision_id(
        revision_number=2, parent_revision_id="1" * 16, **common
    )
    r2 = derive_revision_id(
        revision_number=3, parent_revision_id="1" * 16, **common
    )
    r3 = derive_revision_id(
        revision_number=2, parent_revision_id="2" * 16, **common
    )
    assert r1 != r2
    assert r1 != r3


def test_decision_id_stable_and_sequence_sensitive():
    authority = {
        "authority_type": "system",
        "authority_id": "simulate.py",
        "authority_role": None,
    }
    a = derive_decision_id(
        revision_id="r" * 16,
        sequence=1,
        category=DecisionCategory.AUTHORIZATION.value,
        event_type=HistoryEventType.AUTHORIZATION_DENIED.value,
        authority=authority,
        outcome_code=DecisionOutcomeCode.DENIED.value,
        related_ids=("SAD-001", "SAD-002"),
    )
    b = derive_decision_id(
        revision_id="r" * 16,
        sequence=1,
        category=DecisionCategory.AUTHORIZATION.value,
        event_type=HistoryEventType.AUTHORIZATION_DENIED.value,
        authority=authority,
        outcome_code=DecisionOutcomeCode.DENIED.value,
        related_ids=("SAD-001", "SAD-002"),
    )
    c = derive_decision_id(
        revision_id="r" * 16,
        sequence=2,
        category=DecisionCategory.AUTHORIZATION.value,
        event_type=HistoryEventType.AUTHORIZATION_DENIED.value,
        authority=authority,
        outcome_code=DecisionOutcomeCode.DENIED.value,
        related_ids=("SAD-001", "SAD-002"),
    )
    assert a == b
    assert a != c


def test_execution_id_uses_canonical_artifact_order():
    bindings_a = [
        {"artifact_type": "report_text", "relative_path": "output/a.txt", "sha256": "1" * 16},
        {"artifact_type": "result_json", "relative_path": "output/a.json", "sha256": "2" * 16},
    ]
    bindings_b = list(reversed(bindings_a))
    canon_a = canonical_artifact_bindings(bindings_a)
    canon_b = canonical_artifact_bindings(bindings_b)
    assert canon_a == canon_b
    ea = derive_execution_id(
        revision_id="r" * 16,
        authorization_id="a" * 16,
        result_digest="z" * 16,
        artifact_bindings=canon_a,
    )
    eb = derive_execution_id(
        revision_id="r" * 16,
        authorization_id="a" * 16,
        result_digest="z" * 16,
        artifact_bindings=canon_b,
    )
    assert ea == eb


def test_allowed_decision_matrix_is_closed():
    assert len(ALLOWED_DECISION_COMBINATIONS) == 7
    # Disallowed combo rejected at DecisionRecord construction.
    with pytest.raises(HistoryContractError, match="disallowed"):
        DecisionRecord(
            decision_id="d" * 16,
            sequence=1,
            category=DecisionCategory.READINESS,
            event_type=HistoryEventType.AUTHORIZATION_DENIED,
            authority=AuthorityRecord(
                authority_type=AuthorityType.SYSTEM,
                authority_id="core.readiness",
            ),
            outcome_code=DecisionOutcomeCode.NOT_READY,
            summary="mismatch",
            related_revision_id="r" * 16,
            related_ids=(),
        )


def test_case_revision_frozen_and_revision1_rules():
    rev = CaseRevision(
        revision_id="1" * 16,
        revision_number=1,
        parent_revision_id=None,
        site_digest="a" * 16,
        evidence_digest="b" * 16,
        readiness_digest="c" * 16,
        authorization_id=None,
        result_digest=None,
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T00:00:00Z",
    )
    with pytest.raises(Exception):
        rev.revision_number = 2  # type: ignore[misc]
    with pytest.raises(HistoryContractError, match="parent_revision_id=null"):
        CaseRevision(
            revision_id="1" * 16,
            revision_number=1,
            parent_revision_id="0" * 16,
            site_digest="a" * 16,
            evidence_digest="b" * 16,
            readiness_digest="c" * 16,
            authorization_id=None,
            result_digest=None,
            created_reason=CreatedReason.INITIAL_RUN,
            created_utc="2026-07-21T00:00:00Z",
        )


def test_practitioner_authority_requires_role():
    with pytest.raises(HistoryContractError, match="authority_role"):
        AuthorityRecord(
            authority_type=AuthorityType.PRACTITIONER,
            authority_id="jane.doe",
            authority_role=None,
        )
    ok = AuthorityRecord(
        authority_type=AuthorityType.PRACTITIONER,
        authority_id="jane.doe",
        authority_role="PE",
    )
    assert ok.authority_role == "PE"


def test_artifact_binding_rejects_absolute_path():
    with pytest.raises(HistoryContractError, match="relative"):
        ArtifactBinding(
            artifact_type="result_json",
            relative_path="/tmp/out.json",
            sha256="a" * 16,
        )


def test_execution_record_requires_status_enum():
    exe = ExecutionRecord(
        execution_id="e" * 16,
        revision_id="1" * 16,
        authorization_id="a" * 16,
        result_digest="0" * 16,
        status=ExecutionStatus.PASSED,
        generated_artifacts=(),
        started_utc="2026-07-21T00:00:00Z",
        completed_utc="2026-07-21T00:00:01Z",
    )
    assert exe.status is ExecutionStatus.PASSED
