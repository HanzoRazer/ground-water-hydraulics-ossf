"""
test_end_to_end.py
==================

End-to-end tests that drive ``simulate.main`` against the canonical V1
fixtures in ``tests/fixtures/`` and assert the governed OSSF-GW-002 pipeline
behaves correctly all the way to the written artifacts:

  * PROCEED  -> exit 0, authorization stamped, physics ran (once per
                receptor x constituent), input schema version stamped.
  * WARN     -> exit 0, warning preserved through JSON + text outputs.
  * REFUSE   -> exit 2, authorization denied, and the physics engine is
                PROVABLY never invoked (call-counter on the engine).

Plus the OSSF-GW-002 negative driver tests: an unsupported schema, a
structurally invalid case, and a cross-field-invalid case all fail with a
clean nonzero exit and PROVABLY never reach preflight/authorization/physics.

Run: python -m pytest tests/test_end_to_end.py -v
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
from core import physics_ogata_banks
import core.physics_registry as registry

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _run(tmp_path: Path, cfg_path: Path):
    out_json = tmp_path / "results.json"
    out_txt = tmp_path / "report.txt"
    code = simulate.main(
        [str(cfg_path), "--output", str(out_json), "--text", str(out_txt)]
    )
    return code, out_json, out_txt


def _run_fixture(tmp_path: Path, fixture_name: str):
    return _run(tmp_path, FIXTURES / fixture_name)


def _write(tmp_path: Path, cfg: dict, name: str = "site.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def _expected_engine_calls(cfg: dict) -> int:
    """Driver invokes once per active receptor × constituent (see run_physics)."""
    active_receptors = [r for r in cfg["receptors"] if r.get("active", True)]
    return len(active_receptors) * len(cfg["constituents"])


@pytest.fixture
def engine_call_counter(monkeypatch):
    """Wrap the registered engine's ``evaluate`` with a call counter so a
    test can prove whether the physics engine ran. Patches both the module
    attribute and the registry record (which holds its own reference)."""
    calls = {"n": 0}
    real = physics_ogata_banks.evaluate

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(physics_ogata_banks, "evaluate", counting)
    record = registry.ENGINES["ogata_banks_1d"]
    monkeypatch.setitem(
        registry.ENGINES, "ogata_banks_1d", record._replace(evaluate=counting)
    )
    return calls


# ---------------------------------------------------------------------------
# PROCEED
# ---------------------------------------------------------------------------

def test_proceed_fixture_runs_and_stamps_authorization(tmp_path):
    code, out_json, out_txt = _run_fixture(tmp_path, "site_case_v1_proceed.json")
    assert code == 0

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "screening-result-2.0"
    assert artifact["status"] == "pass"
    att = artifact["attestation"]
    assert att["preflight_disposition"] == "proceed"
    assert att["warning_count"] == 0
    assert att["refusal_count"] == 0
    # OSSF-GW-002: the input schema version is stamped on the artifact.
    assert att["input_schema_version"] == "ossf-site-case-1.1.0"
    assert len(att["site_config_hash"]) == 16
    assert artifact["authorization"]["disposition"] == "proceed"
    assert artifact["authorization"]["authorization_id"] == att["authorization_id"]
    assert artifact["physics"]["receptors"], "expected receptor results"


def test_proceed_fixture_invokes_engine(tmp_path, engine_call_counter):
    code, _, _ = _run_fixture(tmp_path, "site_case_v1_proceed.json")
    assert code == 0
    cfg = json.loads((FIXTURES / "site_case_v1_proceed.json").read_text(encoding="utf-8"))
    assert engine_call_counter["n"] == _expected_engine_calls(cfg)


# ---------------------------------------------------------------------------
# WARN
# ---------------------------------------------------------------------------

def test_warn_fixture_preserves_warning_through_outputs(tmp_path):
    code, out_json, out_txt = _run_fixture(tmp_path, "site_case_v1_warn.json")
    assert code == 0

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "screening-result-2.0"
    # Warn disposition is orthogonal to criteria outcome; this fixture still
    # meets every gating limit, so ADR-0004 status remains pass (exit 0).
    assert artifact["status"] == "pass"
    att = artifact["attestation"]
    assert att["preflight_disposition"] == "warn"
    assert att["warning_count"] >= 1
    assert artifact["authorization"]["disposition"] == "warn"

    assert any(w["rule_id"] == "SAD-005" for w in artifact["preflight"]["warnings"])
    text = out_txt.read_text(encoding="utf-8")
    assert "PREFLIGHT WARNINGS" in text
    assert "SAD-005" in text


def test_warn_fixture_still_runs_engine(tmp_path, engine_call_counter):
    code, _, _ = _run_fixture(tmp_path, "site_case_v1_warn.json")
    assert code == 0
    cfg = json.loads((FIXTURES / "site_case_v1_warn.json").read_text(encoding="utf-8"))
    assert engine_call_counter["n"] == _expected_engine_calls(cfg)


# ---------------------------------------------------------------------------
# REFUSE
# ---------------------------------------------------------------------------

def test_refuse_fixture_exits_2_and_denies_authorization(tmp_path):
    code, out_json, out_txt = _run_fixture(tmp_path, "site_case_v1_refuse.json")
    assert code == 2

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "screening-result-2.0"
    assert artifact["status"] == "refused"
    assert artifact["disposition"] == "refuse"
    # The refusal fixture is karst terrain -> SAD-002.
    assert any(r["rule_id"] == "SAD-002" for r in artifact["refusal_reasons"])

    auth = artifact["authorization"]
    assert auth["authorized"] is False
    assert auth["authorization_id"] is None
    assert auth["schema_version"]
    assert auth["ruleset_version"]
    assert auth["preflight_disposition"] == "refuse"
    assert len(auth["site_config_hash"]) == 16
    assert len(auth["findings_digest"]) == 16
    assert auth["refusal_count"] >= 1
    assert artifact["findings_all"], "refusal artifact should list all findings"
    assert any(f["rule_id"] == "SAD-002" for f in artifact["findings_all"])
    assert "physics" not in artifact
    assert "attestation" not in artifact

    text = out_txt.read_text(encoding="utf-8")
    assert "SITE REFUSED" in text
    assert "AUTHORIZATION: DENIED" in text


def test_refuse_fixture_never_invokes_engine(tmp_path, engine_call_counter):
    code, _, _ = _run_fixture(tmp_path, "site_case_v1_refuse.json")
    assert code == 2
    assert engine_call_counter["n"] == 0, (
        "physics engine was invoked on a refused site — governance breach"
    )


def test_authorized_fail_exits_3_with_status_fail(tmp_path, monkeypatch):
    """ADR-0004: authorized run with a gating exceedance → status fail, exit 3.

    Monkeypatch avoids inventing a brittle physics fixture: the proceed case
    still authorizes and runs; only the criteria aggregation is forced false.
    """
    monkeypatch.setattr(simulate, "_all_gating_criteria_met", lambda _physics: False)
    code, out_json, _ = _run_fixture(tmp_path, "site_case_v1_proceed.json")
    assert code == 3
    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "screening-result-2.0"
    assert artifact["status"] == "fail"
    assert artifact["authorization"]["disposition"] == "proceed"
    assert "physics" in artifact
    assert "attestation" in artifact


# ---------------------------------------------------------------------------
# Negative driver tests (OSSF-GW-002 §8.16): invalid input never reaches
# preflight / authorization / physics.
# ---------------------------------------------------------------------------

def test_unsupported_schema_exits_1_and_never_runs_engine(tmp_path, engine_call_counter, capsys):
    cfg = v1_dict(schema_version="ossf-site-case-9.9.9")
    code, _, _ = _run(tmp_path, _write(tmp_path, cfg))
    assert code == 1
    assert engine_call_counter["n"] == 0
    assert "schema" in capsys.readouterr().err.lower()


def test_structurally_invalid_exits_1_and_never_runs_engine(tmp_path, engine_call_counter, capsys):
    cfg = v1_dict()
    del cfg["treatment"]                      # required section missing
    cfg["groundwater"]["hydraulic_gradient"] = -1.0   # + a bad value
    code, _, _ = _run(tmp_path, _write(tmp_path, cfg))
    assert code == 1
    assert engine_call_counter["n"] == 0
    err = capsys.readouterr().err
    assert "validation" in err.lower()
    assert "treatment" in err


def test_unknown_soil_exits_1_before_preflight(tmp_path, engine_call_counter, capsys):
    cfg = v1_dict()
    cfg["subsurface"]["soil_id"] = "unobtanium"
    code, _, _ = _run(tmp_path, _write(tmp_path, cfg))
    assert code == 1
    assert engine_call_counter["n"] == 0
    assert "unobtanium" in capsys.readouterr().err


def test_unknown_constituent_exits_1_cleanly(tmp_path, engine_call_counter, capsys):
    cfg = v1_dict()
    cfg["constituents"] = [
        {"constituent_id": "not_a_real_constituent", "role": "gating", "use_governed_default": True},
    ]
    code, _, _ = _run(tmp_path, _write(tmp_path, cfg))
    assert code == 1
    assert engine_call_counter["n"] == 0
    assert "not_a_real_constituent" in capsys.readouterr().err


def test_malformed_json_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json ", encoding="utf-8")
    code = simulate.main([str(bad)])
    assert code == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_legacy_config_still_runs_via_converter(tmp_path):
    """The retained legacy fixture (unversioned) is converted and runs
    end-to-end, proving the bounded migration path."""
    code, out_json, _ = _run(tmp_path, FIXTURES / "site_case_legacy.json")
    assert code in (0, 2)  # depends on the legacy fixture's disposition
    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    # Either way it went through the V1 contract: schema version is stamped.
    if code == 0:
        assert artifact["attestation"]["input_schema_version"] == "ossf-site-case-1.1.0"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
