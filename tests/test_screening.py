"""Integration tests for the end-to-end screening pipeline (simulate.py)."""

import json
import pathlib

import pytest

import simulate
from core import darcy, transport
from core.report import build_report
from core.validation import ConfigValidationError

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_EXAMPLE = _ROOT / "config" / "site_example.json"


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Wiring / golden checks against the shipped example config
# --------------------------------------------------------------------------- #

def test_example_config_runs_and_reports_all_pass():
    config = _load(_EXAMPLE)
    results = simulate.run_screening(config)

    # Every receptor/constituent should carry a boolean pass flag.
    flags = [
        c["passes"]
        for rec in results["receptor_results"]
        for c in rec["constituents"]
    ]
    assert flags, "expected at least one constituent result"
    assert all(isinstance(f, bool) for f in flags)
    # The clay-loam example is engineered to pass at every receptor.
    assert all(flags)


def test_example_travel_time_matches_hand_computation():
    config = _load(_EXAMPLE)
    soils = _load(_ROOT / "data" / "soils.json")
    results = simulate.run_screening(config)

    soil = soils[config["soil_class"]]
    q = darcy.darcy_flux(soil["K_m_per_day"], config["hydraulic_gradient"])
    vs = darcy.seepage_velocity(q, soil["n_e"])

    for rec_cfg, rec_res in zip(config["receptors"], results["receptor_results"]):
        expected = transport.advective_travel_time(rec_cfg["distance_m"], vs)
        assert rec_res["t_adv_days"] == pytest.approx(expected)


def test_provenance_hashes_present_and_correct():
    config = _load(_EXAMPLE)
    results = simulate.run_screening(config)
    prov = results["meta"]["provenance"]

    assert prov["soils_db_sha256"] == simulate._sha256_short(_ROOT / "data" / "soils.json")
    assert prov["constituents_db_sha256"] == simulate._sha256_short(
        _ROOT / "data" / "constituents.json"
    )
    assert results["meta"]["config_schema_version"] == config["_schema_version"]
    assert results["meta"]["nondetect_log_removal_target"] == transport.NONDETECT_LOG_REMOVAL_TARGET


def test_report_builds_and_includes_scope_and_provenance():
    config = _load(_EXAMPLE)
    results = simulate.run_screening(config)
    report = build_report(results)

    assert "MODEL SCOPE & LIMITATIONS" in report
    assert "DATA PROVENANCE" in report
    assert "metadata only" in report  # treatment_type framing
    # No exact-zero "effectively zero" claim should survive.
    assert "effectively zero" not in report


# --------------------------------------------------------------------------- #
# Non-detect policy exercised end-to-end
# --------------------------------------------------------------------------- #

def _nondetect_config(distance_m: float):
    return {
        "_schema_version": "1.0",
        "site_id": "nd_test",
        "soil_class": "Sand",
        "hydraulic_gradient": 0.01,
        "constituents": ["E. coli"],
        "receptors": [{"name": "well", "distance_m": distance_m}],
    }


def test_nondetect_fails_when_removal_insufficient():
    # Very short path through fast Sand -> < 4-log removal -> FAIL.
    results = simulate.run_screening(_nondetect_config(1.0))
    row = results["receptor_results"][0]["constituents"][0]
    assert row["limit_is_nondetect"] is True
    assert row["log_removal"] < row["nondetect_log_removal_target"]
    assert row["passes"] is False


def test_nondetect_passes_when_removal_sufficient():
    # Long path -> huge removal (underflow) -> PASS via log-removal policy.
    results = simulate.run_screening(_nondetect_config(500.0))
    row = results["receptor_results"][0]["constituents"][0]
    assert row["passes"] is True


# --------------------------------------------------------------------------- #
# Validation is enforced through the pipeline
# --------------------------------------------------------------------------- #

def test_run_screening_rejects_invalid_config():
    bad = _nondetect_config(1.0)
    bad["hydraulic_gradient"] = -1.0
    with pytest.raises(ConfigValidationError):
        simulate.run_screening(bad)


def test_run_screening_rejects_unit_mismatch():
    bad = _nondetect_config(1.0)
    bad["effluent_concentrations"] = {"E. coli": {"C0": 10.0, "unit": "mg/L"}}
    with pytest.raises(ConfigValidationError):
        simulate.run_screening(bad)


# --------------------------------------------------------------------------- #
# CLI-level malformed-input handling
# --------------------------------------------------------------------------- #

def test_cli_reports_malformed_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json ", encoding="utf-8")
    rc = simulate.main([str(bad)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not valid JSON" in err


def test_cli_reports_missing_file(capsys):
    rc = simulate.main(["does_not_exist_12345.json"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_cli_reports_validation_errors(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"_schema_version": "1.0"}), encoding="utf-8")
    rc = simulate.main([str(cfg)])
    assert rc == 1
    assert "Invalid site configuration" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Output artifact contract: schema_version + status fields + exit codes
# --------------------------------------------------------------------------- #

def test_result_schema_version_present():
    config = _load(_EXAMPLE)
    results = simulate.run_screening(config)
    assert results["schema_version"] == simulate.RESULT_SCHEMA_VERSION
    assert results["schema_version"] == "screening-result-1.0"


def test_authorized_status_when_all_pass():
    config = _load(_EXAMPLE)
    results = simulate.run_screening(config)
    assert results["status"] == "authorized"


def test_refused_status_when_any_fail():
    # Very short path through fast Sand -> pathogen removal insufficient -> FAIL
    config = {
        "_schema_version": "1.0",
        "site_id": "refuse_test",
        "soil_class": "Sand",
        "hydraulic_gradient": 0.01,
        "constituents": ["E. coli"],
        "receptors": [{"name": "well", "distance_m": 1.0}],
    }
    results = simulate.run_screening(config)
    assert results["status"] == "refused"
    assert results["schema_version"] == simulate.RESULT_SCHEMA_VERSION


def test_cli_exits_0_when_authorized(capsys):
    # Use the example config which is known to produce an authorized result.
    rc = simulate.main([str(_EXAMPLE)])
    capsys.readouterr()  # discard output
    assert rc == 0


def test_cli_exits_2_when_refused(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        json.dumps({
            "_schema_version": "1.0",
            "site_id": "refuse_cli_test",
            "soil_class": "Sand",
            "hydraulic_gradient": 0.01,
            "constituents": ["E. coli"],
            "receptors": [{"name": "well", "distance_m": 1.0}],
        }),
        encoding="utf-8",
    )
    rc = simulate.main([str(cfg)])
    capsys.readouterr()
    assert rc == 2


def test_report_includes_schema_version_and_status():
    config = _load(_EXAMPLE)
    results = simulate.run_screening(config)
    report = build_report(results)
    assert "screening-result-1.0" in report
    assert "authorized" in report
