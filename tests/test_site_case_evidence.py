"""
test_site_case_evidence.py
==========================

Evidence completeness, contradiction, and review-gate tests (OSSF-GW-003).

Run: python -m pytest tests/test_site_case_evidence.py -v
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

from _v1_helpers import attach_complete_evidence, load_dbs, v1_dict
from core.contracts import (
    EvidenceCompletenessError,
    EvidenceContradictionError,
    EvidenceReviewGateError,
    EvidenceValidationError,
    UnsupportedSchemaVersionError,
    parse_site_case_dict,
    validate_evidence_layer,
)
import simulate

SOILS, CONS = load_dbs()


def _parse(cfg: dict):
    return parse_site_case_dict(cfg, soil_database=SOILS, constituent_database=CONS)


def test_complete_bindings_proceed():
    case = _parse(v1_dict())
    result = validate_evidence_layer(case)
    assert result.disposition == "proceed"
    assert result.permits_preflight
    assert len(result.evidence_digest) == 16
    assert result.warnings == ()


def test_missing_critical_binding_raises():
    cfg = v1_dict()
    cfg["field_bindings"] = [
        b for b in cfg["field_bindings"]
        if b["field_path"] != "groundwater.hydraulic_gradient"
    ]
    case = _parse(cfg)
    with pytest.raises(EvidenceCompletenessError) as ei:
        validate_evidence_layer(case)
    assert any("hydraulic_gradient" in e.path for e in ei.value.errors)


def test_provenance_mismatch_raises_contradiction():
    cfg = v1_dict()
    for b in cfg["field_bindings"]:
        if b["field_path"] == "groundwater.hydraulic_gradient":
            b["provenance_class"] = "measured"  # evidence is assumed
    case = _parse(cfg)
    with pytest.raises(EvidenceContradictionError):
        validate_evidence_layer(case)


def test_critical_rejected_raises_review_gate():
    cfg = v1_dict()
    for e in cfg["evidence"]:
        if e["evidence_id"] == "ev_site_assumed":
            e["review_status"] = "rejected"
    for b in cfg["field_bindings"]:
        if b["field_path"] == "groundwater.hydraulic_gradient":
            b["review_status"] = "rejected"
    case = _parse(cfg)
    with pytest.raises(EvidenceReviewGateError):
        validate_evidence_layer(case)


def test_important_pending_review_warns_but_permits():
    cfg = v1_dict()
    # Point treatment bindings at a pending evidence record.
    cfg["evidence"].append({
        "evidence_id": "ev_treatment_pending",
        "provenance_class": "documented",
        "confidence": "medium",
        "review_status": "pending_review",
        "source_description": "Treatment docs awaiting PE review",
        "captured_date": None,
        "notes": None,
        "database_id": None,
        "regulatory_authority": None,
    })
    for b in cfg["field_bindings"]:
        if b["field_path"].startswith("treatment."):
            b["evidence_id"] = "ev_treatment_pending"
            b["review_status"] = "pending_review"
    case = _parse(cfg)
    result = validate_evidence_layer(case)
    assert result.disposition == "warn"
    assert result.permits_preflight
    assert any("treatment" in w.path for w in result.warnings)


def test_reference_only_skips_source_concentration_requirement():
    cfg = v1_dict()
    # nitrate is reference_only — remove any nitrate bindings if present
    cfg["field_bindings"] = [
        b for b in cfg["field_bindings"]
        if "nitrate_as_N" not in b["field_path"]
    ]
    case = _parse(cfg)
    result = validate_evidence_layer(case)
    assert result.disposition == "proceed"


def test_inactive_receptor_skips_distance_requirement():
    cfg = v1_dict()
    cfg["receptors"].append({
        "receptor_id": "inactive_well",
        "receptor_type": "private_well",
        "distance_m": 5.0,
        "display_name": "Inactive",
        "active": False,
    })
    # No binding for inactive_well — must still proceed
    case = _parse(cfg)
    result = validate_evidence_layer(case)
    assert result.disposition == "proceed"


def test_schema_1_0_0_rejected_with_migration_message():
    cfg = v1_dict()
    cfg["schema_version"] = "ossf-site-case-1.0.0"
    with pytest.raises(UnsupportedSchemaVersionError) as ei:
        _parse(cfg)
    assert "Migrate explicitly" in str(ei.value)
    assert "1.1.0" in str(ei.value)


def _superseded_evidence(eid: str) -> dict:
    return {
        "evidence_id": eid,
        "provenance_class": "assumed",
        "confidence": "low",
        "review_status": "superseded",
        "source_description": "Prior gradient estimate, replaced",
        "captured_date": None,
        "notes": None,
        "database_id": None,
        "regulatory_authority": None,
    }


def test_superseded_critical_binding_with_accepted_replacement_proceeds():
    # A critical field may carry a superseded binding alongside an accepted
    # one: the accepted binding IS the replacement the gate asks for.
    cfg = v1_dict()
    cfg["evidence"].append(_superseded_evidence("ev_gradient_old"))
    cfg["field_bindings"].append({
        "field_path": "groundwater.hydraulic_gradient",
        "provenance_class": "assumed",
        "review_status": "superseded",
        "evidence_id": "ev_gradient_old",
        "database_id": None,
        "regulatory_authority": None,
        "assumption_id": None,
        "notes": None,
    })
    case = _parse(cfg)
    result = validate_evidence_layer(case)  # accepted ev_site_assumed remains
    assert result.disposition == "proceed"


def test_superseded_critical_binding_without_replacement_raises():
    # Point the only gradient binding at a superseded record: no accepted
    # replacement exists, so the review gate must fail.
    cfg = v1_dict()
    cfg["evidence"].append(_superseded_evidence("ev_gradient_old"))
    for b in cfg["field_bindings"]:
        if b["field_path"] == "groundwater.hydraulic_gradient":
            b["evidence_id"] = "ev_gradient_old"
            b["provenance_class"] = "assumed"
            b["review_status"] = "superseded"
    case = _parse(cfg)
    with pytest.raises(EvidenceReviewGateError) as ei:
        validate_evidence_layer(case)
    assert any(e.code == "superseded" for e in ei.value.errors)
    assert any(
        "without an accepted replacement" in e.message for e in ei.value.errors
    )


def test_effective_provenance_prefers_linked_evidence_record():
    from core.contracts import (
        EvidenceRecord,
        FieldEvidenceBinding,
        effective_provenance_class,
    )
    ev = EvidenceRecord(
        evidence_id="ev1",
        provenance_class="documented",
        confidence="high",
        review_status="accepted",
        source_description="Design docs",
    )
    binding = FieldEvidenceBinding(
        field_path="constituents[e_coli].source_basis",
        provenance_class="documented",
        review_status="accepted",
        evidence_id="ev1",
    )
    assert effective_provenance_class(binding, {"ev1": ev}).value == "documented"


def test_driver_writes_evidence_failure_artifact(tmp_path):
    cfg = v1_dict()
    cfg["field_bindings"] = [
        b for b in cfg["field_bindings"]
        if b["field_path"] != "groundwater.hydraulic_gradient"
    ]
    cfg_path = tmp_path / "missing_gradient.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    out_json = tmp_path / "out.json"
    code = simulate.main([str(cfg_path), "--output", str(out_json),
                          "--text", str(tmp_path / "out.txt")])
    assert code == 1
    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["status"] == "evidence_failure"
    assert artifact["error_type"] == "EvidenceCompletenessError"
    assert any("hydraulic_gradient" in e["path"] for e in artifact["errors"])


def test_conflicting_provenance_duplicate_bindings_raise():
    cfg = v1_dict()
    gradient = next(
        b for b in cfg["field_bindings"]
        if b["field_path"] == "groundwater.hydraulic_gradient"
    )
    duplicate = copy.deepcopy(gradient)
    duplicate["evidence_id"] = "ev_treatment_docs"
    duplicate["provenance_class"] = "documented"
    cfg["field_bindings"].append(duplicate)
    case = _parse(cfg)
    with pytest.raises(EvidenceContradictionError) as ei:
        validate_evidence_layer(case)
    assert any(e.code == "conflicting_bindings" for e in ei.value.errors)


def test_same_provenance_duplicate_bindings_raise():
    cfg = v1_dict()
    gradient = next(
        b for b in cfg["field_bindings"]
        if b["field_path"] == "groundwater.hydraulic_gradient"
    )
    cfg["field_bindings"].append(copy.deepcopy(gradient))
    case = _parse(cfg)
    with pytest.raises(EvidenceContradictionError) as ei:
        validate_evidence_layer(case)
    assert any(e.code == "duplicate_bindings" for e in ei.value.errors)


def test_standalone_database_id_route_is_accepted():
    cfg = v1_dict()
    for b in cfg["field_bindings"]:
        if b["field_path"] == "subsurface.soil_id":
            b["evidence_id"] = None
            b["database_id"] = cfg["subsurface"]["soil_id"]
            b["provenance_class"] = "database_derived"
    case = _parse(cfg)
    result = validate_evidence_layer(case)
    assert result.disposition == "proceed"
