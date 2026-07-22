"""
test_history_builder.py
=======================

History builder / append paths for OSSF-GW-005.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import load_dbs, make_case, v1_dict
from core.contracts import (
    compute_evidence_digest,
    parse_site_case_dict,
    validate_evidence_layer,
)
from core.history import (
    CreatedReason,
    DecisionOutcomeCode,
    ExecutionStatus,
    HistoryConstructionError,
    HistoryEventType,
    HistoryIdentityError,
    load_and_validate_history,
    write_history,
)
from core.history.builder import (
    AuthorizationDenial,
    ExecutionOutcome,
    append_revision,
    build_history,
    compute_result_digest,
    revision_lookup,
)
from core.readiness import NOT_READY, assess_readiness

SOILS, CONS = load_dbs()


def _ready_case():
    cfg = v1_dict()
    case = parse_site_case_dict(cfg, soil_database=SOILS, constituent_database=CONS)
    evidence = validate_evidence_layer(case)
    readiness = assess_readiness(case, evidence)
    return case, evidence, readiness


def _not_ready_case():
    cfg = v1_dict()
    cfg["field_bindings"] = [
        b for b in cfg["field_bindings"]
        if b["field_path"] != "groundwater.hydraulic_gradient"
    ]
    case = parse_site_case_dict(cfg, soil_database=SOILS, constituent_database=CONS)
    # Bypass evidence gate with synthetic permitting result that still has digest.
    from core.contracts import EvidenceValidationResult
    evidence = EvidenceValidationResult(
        disposition="proceed",
        evidence_digest=compute_evidence_digest(case),
        warnings=(),
        review_summary={
            "accepted": 0, "pending_review": 0, "rejected": 0, "superseded": 0,
            "evidence_records": len(case.evidence),
            "field_bindings": len(case.field_bindings),
        },
        bound_fields=tuple(sorted({b.field_path for b in case.field_bindings})),
    )
    readiness = assess_readiness(case, evidence)
    assert readiness.disposition == NOT_READY
    return case, evidence, readiness


def test_build_history_not_ready_revision_one():
    case, evidence, readiness = _not_ready_case()
    history = build_history(
        case=case,
        evidence_summary=evidence,
        readiness_result=readiness,
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T12:00:00Z",
    )
    assert len(history.revisions) == 1
    assert history.revisions[0].revision_number == 1
    assert history.revisions[0].authorization_id is None
    assert history.revisions[0].result_digest is None
    assert len(history.executions) == 0
    assert len(history.decisions) == 1
    d = history.decisions[0]
    assert d.event_type is HistoryEventType.READINESS_NOT_READY
    assert d.outcome_code is DecisionOutcomeCode.NOT_READY
    assert d.related_ids  # blocking finding refs


def test_build_history_authorization_denied():
    case, evidence, readiness = _ready_case()
    assert readiness.permits_authorization
    denial = AuthorizationDenial(
        findings=(
            SimpleNamespace(rule_id="SAD-001", disposition="refuse", message="x"),
            SimpleNamespace(rule_id="SAD-002", disposition="refuse", message="y"),
        ),
        message="Site refused by preflight",
    )
    history = build_history(
        case=case,
        evidence_summary=evidence,
        readiness_result=readiness,
        authorization_denial=denial,
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T12:00:00Z",
    )
    assert len(history.executions) == 0
    assert history.revisions[0].authorization_id is None
    assert history.decisions[0].event_type is HistoryEventType.AUTHORIZATION_DENIED
    assert history.decisions[0].related_ids == ("SAD-001", "SAD-002")


def test_build_history_proceed_with_execution_and_report():
    case, evidence, readiness = _ready_case()
    auth = SimpleNamespace(
        authorization_id="a" * 16,
        disposition="proceed",
        findings=(),
    )
    result_digest = compute_result_digest({
        "schema_version": "screening-result-2.0",
        "status": "pass",
        "project": {"site_id": case.site_id},
        "generated_utc": "SHOULD_BE_EXCLUDED",
    })
    history = build_history(
        case=case,
        evidence_summary=evidence,
        readiness_result=readiness,
        authorization_result=auth,
        execution_result=ExecutionOutcome(
            status=ExecutionStatus.PASSED,
            result_digest=result_digest,
            started_utc="2026-07-21T12:00:00Z",
            completed_utc="2026-07-21T12:00:01Z",
        ),
        generated_artifacts=(
            {
                "artifact_type": "result_json",
                "relative_path": f"output/{case.site_id}_results.json",
                "sha256": "1" * 16,
            },
            {
                "artifact_type": "report_text",
                "relative_path": f"output/{case.site_id}_report.txt",
                "sha256": "2" * 16,
            },
        ),
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T12:00:00Z",
    )
    assert len(history.revisions) == 1
    assert len(history.executions) == 1
    assert history.executions[0].status is ExecutionStatus.PASSED
    events = [d.event_type for d in history.decisions]
    assert events == [
        HistoryEventType.AUTHORIZATION_PROCEEDED,
        HistoryEventType.SCREENING_EXECUTED,
        HistoryEventType.REPORT_GENERATED,
    ]


def test_build_history_warn_uses_distinct_event():
    case, evidence, readiness = _ready_case()
    auth = SimpleNamespace(
        authorization_id="a" * 16,
        disposition="warn",
        findings=(SimpleNamespace(rule_id="SAD-010"),),
    )
    history = build_history(
        case=case,
        evidence_summary=evidence,
        readiness_result=readiness,
        authorization_result=auth,
        execution_result=ExecutionOutcome(
            status=ExecutionStatus.FAILED,
            result_digest="d" * 16,
            started_utc="2026-07-21T12:00:00Z",
            completed_utc="2026-07-21T12:00:01Z",
        ),
        generated_artifacts=(),
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T12:00:00Z",
    )
    assert history.decisions[0].event_type is (
        HistoryEventType.AUTHORIZATION_PROCEEDED_WITH_WARNINGS
    )
    assert history.decisions[1].event_type is HistoryEventType.SCREENING_FAILED
    assert HistoryEventType.REPORT_GENERATED not in [
        d.event_type for d in history.decisions
    ]


def test_append_revision_increments(tmp_path):
    case, evidence, readiness = _not_ready_case()
    h1 = build_history(
        case=case,
        evidence_summary=evidence,
        readiness_result=readiness,
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T12:00:00Z",
    )
    path = tmp_path / f"{case.site_id}_history.json"
    write_history(h1, path)
    prior = load_and_validate_history(path, expected_site_id=case.site_id)

    h2 = append_revision(
        prior,
        case=case,
        evidence_summary=evidence,
        readiness_result=readiness,
        created_reason=CreatedReason.READINESS_REASSESSMENT,
        created_utc="2026-07-21T13:00:00Z",
    )
    assert len(h2.revisions) == 2
    assert h2.revisions[1].parent_revision_id == h2.revisions[0].revision_id
    assert h2.history_id == h1.history_id
    assert len(h2.decisions) == 2


def test_incompatible_site_id_rejected():
    case, evidence, readiness = _not_ready_case()
    h1 = build_history(
        case=case,
        evidence_summary=evidence,
        readiness_result=readiness,
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T12:00:00Z",
    )
    other = make_case()
    # Force different site_id via parse of modified dict
    cfg = v1_dict()
    cfg["site_id"] = "OTHER-SITE"
    cfg["field_bindings"] = [
        b for b in cfg["field_bindings"]
        if b["field_path"] != "groundwater.hydraulic_gradient"
    ]
    other_case = parse_site_case_dict(
        cfg, soil_database=SOILS, constituent_database=CONS
    )
    other_evidence = type(evidence)(
        disposition=evidence.disposition,
        evidence_digest=compute_evidence_digest(other_case),
        warnings=evidence.warnings,
        review_summary=evidence.review_summary,
        bound_fields=evidence.bound_fields,
    )
    other_readiness = assess_readiness(other_case, other_evidence)
    with pytest.raises(HistoryIdentityError, match="site_id"):
        append_revision(
            h1,
            case=other_case,
            evidence_summary=other_evidence,
            readiness_result=other_readiness,
            created_reason=CreatedReason.CASE_UPDATE,
            created_utc="2026-07-21T13:00:00Z",
        )


def test_result_digest_excludes_history_and_timestamps():
    payload = {
        "status": "pass",
        "history": {"chain_digest": "x"},
        "generated_utc": "2026-01-01T00:00:00Z",
        "project": {"site_id": "EX-001"},
    }
    a = compute_result_digest(payload)
    b = compute_result_digest({
        "status": "pass",
        "project": {"site_id": "EX-001"},
        "generated_utc": "2099-01-01T00:00:00Z",
        "history": {"chain_digest": "different"},
    })
    assert a == b


def test_revision_lookup():
    case, evidence, readiness = _not_ready_case()
    h = build_history(
        case=case,
        evidence_summary=evidence,
        readiness_result=readiness,
        created_reason=CreatedReason.INITIAL_RUN,
        created_utc="2026-07-21T12:00:00Z",
    )
    rev = revision_lookup(h, h.revisions[0].revision_id)
    assert rev.revision_number == 1
    with pytest.raises(HistoryIdentityError):
        revision_lookup(h, "0" * 16)


def test_missing_evidence_digest_raises():
    case, evidence, readiness = _not_ready_case()
    with pytest.raises(HistoryConstructionError, match="evidence_digest"):
        build_history(
            case=case,
            evidence_summary=SimpleNamespace(),
            readiness_result=readiness,
            created_reason=CreatedReason.INITIAL_RUN,
        )
