"""
test_end_to_end.py
==================

End-to-end tests that drive ``simulate.main`` against the canonical
fixtures in ``tests/fixtures/`` and assert the governed pipeline behaves
correctly all the way to the written artifacts:

  * PROCEED  -> exit 0, authorization stamped, physics ran.
  * WARN     -> exit 0, warning preserved through JSON + text outputs.
  * REFUSE   -> exit 2, authorization denied, and the physics engine is
                PROVABLY never invoked (call-counter on the engine).

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
from core import physics_ogata_banks
import core.physics_registry as registry

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _run(tmp_path: Path, fixture_name: str):
    cfg = FIXTURES / fixture_name
    out_json = tmp_path / "results.json"
    out_txt = tmp_path / "report.txt"
    code = simulate.main(
        [str(cfg), "--output", str(out_json), "--text", str(out_txt)]
    )
    return code, out_json, out_txt


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
    code, out_json, out_txt = _run(tmp_path, "site_proceed.json")
    assert code == 0

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    att = artifact["attestation"]
    assert att["preflight_disposition"] == "proceed"
    assert att["warning_count"] == 0
    assert att["refusal_count"] == 0
    assert artifact["authorization"]["disposition"] == "proceed"
    assert artifact["authorization"]["authorization_id"] == att["authorization_id"]
    # Physics actually produced receptor results.
    assert artifact["physics"]["receptors"], "expected receptor results"


def test_proceed_fixture_invokes_engine(tmp_path, engine_call_counter):
    code, _, _ = _run(tmp_path, "site_proceed.json")
    assert code == 0
    # The engine is invoked once per (receptor x constituent) pair. Derive the
    # expected count from the fixture so the test does not break when the
    # fixture gains or loses a receptor or constituent.
    cfg = json.loads((FIXTURES / "site_proceed.json").read_text(encoding="utf-8"))
    expected_calls = len(cfg["receptors"]) * len(cfg["constituents_to_evaluate"])
    assert engine_call_counter["n"] == expected_calls


# ---------------------------------------------------------------------------
# WARN
# ---------------------------------------------------------------------------

def test_warn_fixture_preserves_warning_through_outputs(tmp_path):
    code, out_json, out_txt = _run(tmp_path, "site_warn.json")
    assert code == 0

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    att = artifact["attestation"]
    assert att["preflight_disposition"] == "warn"
    assert att["warning_count"] >= 1
    assert artifact["authorization"]["disposition"] == "warn"

    # The SAD-005 warning survives into the JSON preflight block ...
    assert any(w["rule_id"] == "SAD-005" for w in artifact["preflight"]["warnings"])
    # ... and into the text report.
    text = out_txt.read_text(encoding="utf-8")
    assert "PREFLIGHT WARNINGS" in text
    assert "SAD-005" in text


def test_warn_fixture_still_runs_engine(tmp_path, engine_call_counter):
    """A warn disposition permits execution: the engine must run."""
    code, _, _ = _run(tmp_path, "site_warn.json")
    assert code == 0
    assert engine_call_counter["n"] > 0


# ---------------------------------------------------------------------------
# REFUSE
# ---------------------------------------------------------------------------

def test_refuse_fixture_exits_2_and_denies_authorization(tmp_path):
    code, out_json, out_txt = _run(tmp_path, "site_refuse.json")
    assert code == 2

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["disposition"] == "refuse"
    assert any(r["rule_id"] == "SAD-001" for r in artifact["refusal_reasons"])

    # Refusal provenance: reproducible/auditable, but NOT an attested result.
    auth = artifact["authorization"]
    assert auth["authorized"] is False
    assert auth["authorization_id"] is None
    assert auth["schema_version"]
    assert auth["ruleset_version"]
    assert auth["preflight_disposition"] == "refuse"
    assert len(auth["site_config_hash"]) == 16
    assert len(auth["findings_digest"]) == 16
    assert auth["refusal_count"] >= 1
    # Complete findings are recorded.
    assert artifact["findings_all"], "refusal artifact should list all findings"
    assert any(f["rule_id"] == "SAD-001" for f in artifact["findings_all"])
    # No engine result and no successful methodology attestation.
    assert "physics" not in artifact
    assert "attestation" not in artifact

    text = out_txt.read_text(encoding="utf-8")
    assert "SITE REFUSED" in text
    assert "AUTHORIZATION: DENIED" in text


def test_refuse_fixture_never_invokes_engine(tmp_path, engine_call_counter):
    """The core non-invocation proof: on a refused site the physics engine
    is never called, not even once."""
    code, _, _ = _run(tmp_path, "site_refuse.json")
    assert code == 2
    assert engine_call_counter["n"] == 0, (
        "physics engine was invoked on a refused site — governance breach"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
