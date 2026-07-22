"""
test_history_driver.py
======================

Driver integration for OSSF-GW-005 CaseHistory emission.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import simulate
from _v1_helpers import v1_dict
from core.history import load_and_validate_history


def _write_cfg(tmp_path: Path, cfg: dict) -> Path:
    path = tmp_path / "case.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def test_driver_emits_revision_one_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(simulate, "DEFAULT_OUTPUT_DIR", tmp_path)
    cfg = v1_dict()
    cfg_path = _write_cfg(tmp_path, cfg)
    out_json = tmp_path / "results.json"
    out_txt = tmp_path / "report.txt"
    code = simulate.main([
        str(cfg_path), "--output", str(out_json), "--text", str(out_txt),
    ])
    assert code in (0, 3)
    site_id = cfg["site_id"]
    hist_path = tmp_path / f"{site_id}_history.json"
    assert hist_path.is_file()
    history = load_and_validate_history(hist_path, expected_site_id=site_id)
    assert len(history.revisions) == 1
    assert len(history.executions) == 1
    result = json.loads(out_json.read_text(encoding="utf-8"))
    assert "history" in result
    assert result["history"]["revision_count"] == 1
    assert result["history"]["execution_count"] == 1
    assert result["history"]["history_artifact"].endswith(f"{site_id}_history.json")


def test_driver_appends_with_prior_history(tmp_path, monkeypatch):
    monkeypatch.setattr(simulate, "DEFAULT_OUTPUT_DIR", tmp_path)
    cfg = v1_dict()
    cfg_path = _write_cfg(tmp_path, cfg)
    out_json = tmp_path / "results.json"
    out_txt = tmp_path / "report.txt"
    code1 = simulate.main([
        str(cfg_path), "--output", str(out_json), "--text", str(out_txt),
    ])
    assert code1 in (0, 3)
    site_id = cfg["site_id"]
    hist1 = tmp_path / f"{site_id}_history.json"
    # Copy prior so overwrite of output history is separate from input.
    prior = tmp_path / "prior_history.json"
    prior.write_text(hist1.read_text(encoding="utf-8"), encoding="utf-8")
    code2 = simulate.main([
        str(cfg_path), "--output", str(out_json), "--text", str(out_txt),
        "--prior-history", str(prior),
    ])
    assert code2 in (0, 3)
    history = load_and_validate_history(hist1, expected_site_id=site_id)
    assert len(history.revisions) == 2
    assert history.revisions[1].parent_revision_id == history.revisions[0].revision_id
    result = json.loads(out_json.read_text(encoding="utf-8"))
    assert result["history"]["revision_count"] == 2


def test_driver_not_ready_emits_history_without_execution(tmp_path, monkeypatch):
    from core.contracts import EvidenceValidationResult, compute_evidence_digest

    monkeypatch.setattr(simulate, "DEFAULT_OUTPUT_DIR", tmp_path)
    cfg = v1_dict()
    for e in cfg["evidence"]:
        if e["evidence_id"] == "ev_site_assumed":
            e["review_status"] = "pending_review"
    for b in cfg["field_bindings"]:
        if b["field_path"] == "groundwater.hydraulic_gradient":
            b["review_status"] = "pending_review"

    def fake_validate(case):
        return EvidenceValidationResult(
            disposition="proceed",
            evidence_digest=compute_evidence_digest(case),
            warnings=(),
            review_summary={
                "accepted": 0, "pending_review": 1, "rejected": 0, "superseded": 0,
                "evidence_records": len(case.evidence),
                "field_bindings": len(case.field_bindings),
            },
            bound_fields=tuple(sorted({b.field_path for b in case.field_bindings})),
        )

    monkeypatch.setattr(simulate, "validate_evidence_layer", fake_validate)
    code = simulate.main([str(_write_cfg(tmp_path, cfg))])
    assert code == 1
    site_id = cfg["site_id"]
    hist_path = tmp_path / f"{site_id}_history.json"
    assert hist_path.is_file()
    history = load_and_validate_history(hist_path, expected_site_id=site_id)
    assert len(history.revisions) == 1
    assert len(history.executions) == 0
    # No ExecutionRecord ⇒ no generated_artifacts anywhere in the chain.
    assert all(len(exe.generated_artifacts) == 0 for exe in history.executions)
    assert history.decisions[0].event_type.value == "readiness_not_ready"
    fail_json = tmp_path / f"{site_id}_readiness_failure.json"
    artifact = json.loads(fail_json.read_text(encoding="utf-8"))
    assert artifact["history"]["execution_count"] == 0


def test_driver_authorization_denied_emits_history_without_execution_bindings(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(simulate, "DEFAULT_OUTPUT_DIR", tmp_path)
    fixture = Path(__file__).resolve().parent / "fixtures" / "site_case_v1_refuse.json"
    cfg = json.loads(fixture.read_text(encoding="utf-8"))
    cfg_path = _write_cfg(tmp_path, cfg)
    out_json = tmp_path / "custom" / "results.json"
    out_txt = tmp_path / "custom" / "report.txt"
    out_json.parent.mkdir()
    code = simulate.main([
        str(cfg_path), "--output", str(out_json), "--text", str(out_txt),
    ])
    assert code == 2
    site_id = cfg["site_id"]
    # History stays under DEFAULT_OUTPUT_DIR, not beside custom --output.
    hist_path = tmp_path / f"{site_id}_history.json"
    assert hist_path.is_file()
    assert not (out_json.parent / f"{site_id}_history.json").exists()
    history = load_and_validate_history(hist_path, expected_site_id=site_id)
    assert len(history.executions) == 0
    assert all(len(exe.generated_artifacts) == 0 for exe in history.executions)
    assert history.decisions[0].event_type.value == "authorization_denied"
    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["history"]["execution_count"] == 0
    # Embedded pointer names the default history location (basename under
    # monkeypatched DEFAULT_OUTPUT_DIR when outside the repo root).
    assert artifact["history"]["history_artifact"].endswith(
        f"{site_id}_history.json"
    )


def test_history_stays_in_default_dir_when_output_is_custom(tmp_path, monkeypatch):
    """Documented GW-005 split: custom --output does not relocate history."""
    monkeypatch.setattr(simulate, "DEFAULT_OUTPUT_DIR", tmp_path / "hist_home")
    (tmp_path / "hist_home").mkdir()
    cfg = v1_dict()
    cfg_path = _write_cfg(tmp_path, cfg)
    custom = tmp_path / "elsewhere"
    custom.mkdir()
    out_json = custom / "results.json"
    out_txt = custom / "report.txt"
    code = simulate.main([
        str(cfg_path), "--output", str(out_json), "--text", str(out_txt),
    ])
    assert code in (0, 3)
    site_id = cfg["site_id"]
    hist_path = tmp_path / "hist_home" / f"{site_id}_history.json"
    assert hist_path.is_file()
    assert not (custom / f"{site_id}_history.json").exists()
    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["history"]["history_artifact"].endswith(
        f"{site_id}_history.json"
    )
    # Integrity: still no result_json byte binding.
    history = load_and_validate_history(hist_path, expected_site_id=site_id)
    recorded = [a for exe in history.executions for a in exe.generated_artifacts]
    assert recorded
    assert all(a.artifact_type != "result_json" for a in recorded)


def test_driver_evidence_failure_does_not_emit_history(tmp_path, monkeypatch):
    monkeypatch.setattr(simulate, "DEFAULT_OUTPUT_DIR", tmp_path)
    cfg = v1_dict()
    # Conflicting provenance on critical field → evidence contradiction.
    cfg["field_bindings"].append({
        "field_path": "groundwater.hydraulic_gradient",
        "provenance_class": "measured",
        "review_status": "accepted",
        "evidence_id": None,
        "database_id": None,
        "regulatory_authority": "TCEQ",
        "assumption_id": None,
        "notes": None,
    })
    # Ensure existing binding remains so we get duplicate/conflict.
    cfg_path = _write_cfg(tmp_path, cfg)
    code = simulate.main([str(cfg_path)])
    assert code == 1
    site_id = cfg["site_id"]
    hist_path = tmp_path / f"{site_id}_history.json"
    assert not hist_path.exists()


def test_recorded_artifact_digests_match_on_disk(tmp_path, monkeypatch):
    # Integrity invariant (OSSF-GW-005): every artifact digest recorded in
    # history must match the bytes actually left on disk. Before the fix the
    # authorized path bound result_json with a digest taken *before*
    # embed_history_block rewrote the file, so the recorded sha256 was stale
    # and an auditor re-hashing the file would see a false tamper mismatch.
    # This asserts the invariant directly: it fails on the pre-fix code and
    # passes once the stale result_json binding is removed.
    from core.governance import sha256_of_file

    monkeypatch.setattr(simulate, "DEFAULT_OUTPUT_DIR", tmp_path)
    cfg = v1_dict()
    cfg_path = _write_cfg(tmp_path, cfg)
    out_json = tmp_path / "results.json"
    out_txt = tmp_path / "report.txt"
    code = simulate.main([
        str(cfg_path), "--output", str(out_json), "--text", str(out_txt),
    ])
    assert code in (0, 3)
    site_id = cfg["site_id"]
    hist_path = tmp_path / f"{site_id}_history.json"
    history = load_and_validate_history(hist_path, expected_site_id=site_id)

    recorded = [a for exe in history.executions for a in exe.generated_artifacts]
    assert recorded, "expected at least one recorded artifact binding"
    # result_json bytes must NOT be bound — they change when history is embedded.
    assert all(a.artifact_type != "result_json" for a in recorded)
    for a in recorded:
        on_disk = tmp_path / a.relative_path
        assert on_disk.is_file(), f"missing artifact file {a.relative_path!r}"
        assert sha256_of_file(on_disk) == a.sha256, (
            f"recorded digest for {a.artifact_type!r} does not match on-disk bytes"
        )


def test_driver_rejects_malformed_prior_history(tmp_path, monkeypatch):
    monkeypatch.setattr(simulate, "DEFAULT_OUTPUT_DIR", tmp_path)
    cfg = v1_dict()
    cfg_path = _write_cfg(tmp_path, cfg)
    prior = tmp_path / "bad_prior.json"
    prior.write_text("{not-json", encoding="utf-8")
    out_json = tmp_path / "results.json"
    code = simulate.main([
        str(cfg_path), "--output", str(out_json),
        "--prior-history", str(prior),
    ])
    assert code == 1
    assert not out_json.exists()
    assert prior.read_text(encoding="utf-8") == "{not-json"
