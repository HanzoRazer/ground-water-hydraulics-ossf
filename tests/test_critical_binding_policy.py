"""
test_critical_binding_policy.py
===============================

Shared critical-binding acceptance policy used by evidence and readiness
(OSSF-GW-003 / OSSF-GW-004). Ensures the two stages cannot drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import load_dbs, make_case, v1_dict
from core.contracts import (
    CriticalBindingBucket,
    EvidenceCompletenessError,
    EvidenceValidationResult,
    compute_evidence_digest,
    critical_binding_issue_bucket,
    iter_critical_binding_acceptance_issues,
    parse_site_case_dict,
    validate_evidence_layer,
)
from core.readiness import NOT_READY, assess_readiness

SOILS, CONS = load_dbs()


def test_critical_binding_issue_bucket_mapping():
    assert critical_binding_issue_bucket("missing_binding") is (
        CriticalBindingBucket.MISSING
    )
    assert critical_binding_issue_bucket("duplicate_bindings") is (
        CriticalBindingBucket.STRUCTURAL_CONFLICT
    )
    assert critical_binding_issue_bucket("conflicting_bindings") is (
        CriticalBindingBucket.STRUCTURAL_CONFLICT
    )
    assert critical_binding_issue_bucket("unknown_evidence") is (
        CriticalBindingBucket.STRUCTURAL_CONFLICT
    )
    assert critical_binding_issue_bucket("pending_review") is (
        CriticalBindingBucket.REVIEW_BLOCK
    )
    assert critical_binding_issue_bucket("rejected") is (
        CriticalBindingBucket.REVIEW_BLOCK
    )
    assert critical_binding_issue_bucket("superseded") is (
        CriticalBindingBucket.REVIEW_BLOCK
    )


def test_unregistered_critical_binding_code_raises():
    with pytest.raises(ValueError, match="unregistered"):
        critical_binding_issue_bucket("not_a_real_code")


def test_shared_helper_flags_missing_critical_on_bare_case():
    issues = iter_critical_binding_acceptance_issues(make_case())
    assert issues
    assert any(i.code == "missing_binding" for i in issues)
    assert any("hydraulic_gradient" in i.field_path for i in issues)


def test_evidence_and_readiness_agree_on_missing_critical():
    cfg = v1_dict()
    cfg["field_bindings"] = [
        b for b in cfg["field_bindings"]
        if b["field_path"] != "groundwater.hydraulic_gradient"
    ]
    case = parse_site_case_dict(cfg, soil_database=SOILS, constituent_database=CONS)
    issues = iter_critical_binding_acceptance_issues(case)
    assert any(
        i.field_path == "groundwater.hydraulic_gradient"
        and i.code == "missing_binding"
        for i in issues
    )
    with pytest.raises(EvidenceCompletenessError):
        validate_evidence_layer(case)
    # Readiness RDY-004 uses the same helper (defense in depth even if
    # evidence were bypassed with a synthetic permitting result).
    synthetic = EvidenceValidationResult(
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
    readiness = assess_readiness(case, synthetic)
    assert readiness.disposition == NOT_READY
    assert any(
        f.path == "groundwater.hydraulic_gradient" for f in readiness.blocks()
    )


def test_ready_fixture_has_no_critical_acceptance_issues():
    cfg = v1_dict()
    case = parse_site_case_dict(cfg, soil_database=SOILS, constituent_database=CONS)
    assert iter_critical_binding_acceptance_issues(case) == ()
    evidence = validate_evidence_layer(case)
    readiness = assess_readiness(case, evidence)
    assert readiness.permits_authorization
