"""
test_readiness_assessment.py
============================

Unit tests for practitioner readiness assessment (OSSF-GW-004):
RDY-001..005 dispositions, permits_authorization, and failure artifacts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import (
    attach_complete_evidence,
    evidence_result_for,
    load_dbs,
    load_fixture_case,
    make_case,
    v1_dict,
)
from core.contracts import (
    EvidenceValidationResult,
    EvidenceWarning,
    parse_site_case_dict,
)
from core.readiness import (
    NOT_READY,
    READY,
    READY_WITH_WARNINGS,
    ReadinessAssessment,
    assess_readiness,
    readiness_failure_artifact,
    readiness_result_summary_dict,
    require_readiness,
)
from core.readiness.errors import ReadinessNotReadyError


def _case_from_v1(**overrides):
    soils, cons = load_dbs()
    return parse_site_case_dict(
        v1_dict(**overrides), soil_database=soils, constituent_database=cons
    )


def test_ready_fixture_is_ready():
    case = load_fixture_case("proceed")
    ev = evidence_result_for(case)  # digest-aligned; fixture is complete
    # Prefer real evidence validation outcome for a proceed fixture.
    from core.contracts import validate_evidence_layer
    ev = validate_evidence_layer(case)
    result = assess_readiness(case, ev)
    assert result.disposition == READY
    assert result.permits_authorization is True
    assert result.schema_version == "screening-readiness-1.0.0"
    assert len(result.readiness_digest) == 16
    assert result.findings == ()


def test_rdy_001_blocks_when_evidence_does_not_permit():
    case = make_case()
    ev = EvidenceValidationResult(
        disposition="refuse",
        evidence_digest="0000000000000000",
        warnings=(),
        review_summary={},
        bound_fields=(),
    )
    # Override permits_preflight via a simple namespace object.
    class _Bad:
        permits_preflight = False
        disposition = "refuse"
        evidence_digest = "0000000000000000"
        warnings = ()

    result = assess_readiness(case, _Bad())
    assert result.disposition == NOT_READY
    assert result.permits_authorization is False
    assert any(f.finding_id == "RDY-001" for f in result.blocks())


def test_rdy_002_blocks_on_evidence_digest_mismatch():
    case = make_case()
    ev = evidence_result_for(case)
    bad = EvidenceValidationResult(
        disposition="proceed",
        evidence_digest="deadbeefdeadbeef",
        warnings=(),
        review_summary=dict(ev.review_summary),
        bound_fields=ev.bound_fields,
    )
    result = assess_readiness(case, bad)
    assert result.disposition == NOT_READY
    assert any(f.finding_id == "RDY-002" and f.code == "evidence_digest_mismatch"
               for f in result.findings)


def test_rdy_003_warns_on_important_evidence_warnings():
    case = _case_from_v1()
    ev = evidence_result_for(case)
    warned = EvidenceValidationResult(
        disposition="warn",
        evidence_digest=ev.evidence_digest,
        warnings=(
            EvidenceWarning(
                path="treatment.treatment_level",
                code="pending_review",
                message="important field pending",
            ),
        ),
        review_summary=dict(ev.review_summary),
        bound_fields=ev.bound_fields,
    )
    result = assess_readiness(case, warned)
    assert result.disposition == READY_WITH_WARNINGS
    assert result.permits_authorization is True
    assert any(f.finding_id == "RDY-003" for f in result.warnings())


def test_rdy_004_blocks_when_critical_binding_not_accepted():
    soils, cons = load_dbs()
    raw = attach_complete_evidence(v1_dict())
    # Force critical gradient binding + linked evidence to pending_review.
    for e in raw["evidence"]:
        if e["evidence_id"] == "ev_site_assumed":
            e["review_status"] = "pending_review"
    for b in raw["field_bindings"]:
        if b["field_path"] == "groundwater.hydraulic_gradient":
            b["review_status"] = "pending_review"
    case = parse_site_case_dict(raw, soil_database=soils, constituent_database=cons)
    # Synthetic permitting evidence result (bypasses evidence completeness gate).
    ev = EvidenceValidationResult(
        disposition="proceed",
        evidence_digest=evidence_result_for(case).evidence_digest,
        warnings=(),
        review_summary={"accepted": 0, "pending_review": 1, "rejected": 0,
                        "superseded": 0, "evidence_records": len(case.evidence),
                        "field_bindings": len(case.field_bindings)},
        bound_fields=tuple(sorted({b.field_path for b in case.field_bindings})),
    )
    result = assess_readiness(case, ev)
    assert result.disposition == NOT_READY
    assert any(f.finding_id == "RDY-004" for f in result.blocks())


def test_rdy_005_warns_on_pending_verification_assumption():
    soils, cons = load_dbs()
    raw = attach_complete_evidence(v1_dict())
    raw["assumptions"] = [
        {
            "assumption_id": "asm_grad",
            "description": "Gradient pending field verification",
            "basis": "assumed",
            "status": "pending_verification",
        }
    ]
    for b in raw["field_bindings"]:
        if b["field_path"] == "groundwater.hydraulic_gradient":
            b["assumption_id"] = "asm_grad"
    case = parse_site_case_dict(raw, soil_database=soils, constituent_database=cons)
    from core.contracts import validate_evidence_layer
    ev = validate_evidence_layer(case)
    result = assess_readiness(case, ev)
    assert result.disposition == READY_WITH_WARNINGS
    assert result.permits_authorization is True
    assert any(f.finding_id == "RDY-005" for f in result.warnings())


def test_worst_disposition_wins_not_ready_over_warnings():
    soils, cons = load_dbs()
    raw = attach_complete_evidence(v1_dict())
    for e in raw["evidence"]:
        if e["evidence_id"] == "ev_site_assumed":
            e["review_status"] = "pending_review"
    for b in raw["field_bindings"]:
        if b["field_path"] == "groundwater.hydraulic_gradient":
            b["review_status"] = "pending_review"
    case = parse_site_case_dict(raw, soil_database=soils, constituent_database=cons)
    ev = EvidenceValidationResult(
        disposition="warn",
        evidence_digest=evidence_result_for(case).evidence_digest,
        warnings=(
            EvidenceWarning(path="treatment.treatment_level", code="pending_review",
                            message="important pending"),
        ),
        review_summary={},
        bound_fields=(),
    )
    result = assess_readiness(case, ev)
    assert result.disposition == NOT_READY
    assert any(f.finding_id == "RDY-003" for f in result.findings)
    assert any(f.finding_id == "RDY-004" for f in result.findings)


def test_require_readiness_raises_on_not_ready():
    case = make_case()
    class _Bad:
        permits_preflight = False
        disposition = "refuse"
        evidence_digest = "0" * 16
        warnings = ()
    with pytest.raises(ReadinessNotReadyError) as ei:
        require_readiness(case, _Bad())
    assert isinstance(ei.value.assessment, ReadinessAssessment)
    assert ei.value.assessment.disposition == NOT_READY


def test_summary_and_failure_artifact_shape():
    case = load_fixture_case("proceed")
    from core.contracts import validate_evidence_layer
    ev = validate_evidence_layer(case)
    result = assess_readiness(case, ev)
    summary = readiness_result_summary_dict(result)
    assert summary["disposition"] == READY
    assert summary["readiness_digest"] == result.readiness_digest
    assert "assessed_utc" in summary

    # Failure artifact for a forced not_ready assessment.
    bad = assess_readiness(make_case(), type("E", (), {
        "permits_preflight": False,
        "disposition": "refuse",
        "evidence_digest": "0" * 16,
        "warnings": (),
    })())
    art = readiness_failure_artifact(
        make_case(site_id="T-FAIL"), bad, generated_utc="2026-01-01T00:00:00+00:00"
    )
    assert art["status"] == "readiness_failure"
    assert art["schema_version"] == "screening-readiness-failure-1.0"
    assert art["readiness"]["disposition"] == NOT_READY
    assert "notice" in art


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
