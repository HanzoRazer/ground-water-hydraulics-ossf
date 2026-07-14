"""
test_governed_execution.py
==========================

Tests that the physics boundary cannot be crossed without a valid
authorization. This is the enforcement half of the authorization contract:
``core/authorization.py`` defines the token; here we prove the registry
adapter and the engine refuse to run without one.

Boundary cases covered:

  * a valid authorization runs the engine and returns engine metadata;
  * a missing authorization is refused;
  * a config-mismatched authorization is refused (config-binding);
  * a smuggled non-permitting authorization is refused;
  * an unknown engine name is refused;
  * a DIRECT call to the engine's ``evaluate`` without a token is refused;
  * ``get_engine`` is metadata-only and does not run the engine.

Run: python -m pytest tests/test_governed_execution.py -v
"""

from __future__ import annotations

import copy
import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import simulate
from core import physics_ogata_banks
from core.governance import build_attestation
from core.physics_registry import (
    AuthorizedEngineRun,
    get_engine,
    run_authorized_engine,
)
from core.preflight import RuleFinding, SiteAppropriatenessDetermination
from core.authorization import (
    AUTHORIZATION_SCHEMA_VERSION,
    AuthorizationDeniedError,
    AuthorizationError,
    AuthorizationMismatchError,
    authorize_screening,
    validate_authorization,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> dict:
    base = {
        "project": {"site_id": "EX-001"},
        "subsurface": {"soil_type": "clay_loam", "hydraulic_gradient": 0.01},
        "physics": {"engine": "ogata_banks_1d"},
    }
    base.update(overrides)
    return base


def _proceed_sad() -> SiteAppropriatenessDetermination:
    return SiteAppropriatenessDetermination(
        disposition="proceed",
        findings=[
            RuleFinding("SAD-001", "proceed", "Not in EARZ.", "30 TAC 285.40-42"),
        ],
    )


def _engine_inputs() -> dict:
    return dict(
        C0=126.0,
        lam_per_day=0.5,
        Kd_L_per_kg=1.5,
        bulk_density_kg_m3=1390.0,
        effective_porosity=0.08,
        K_sat_m_per_s=7.22e-7,
        hydraulic_gradient=0.01,
        distance_m=30.5,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_authorized_run_returns_result_and_engine_metadata():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    run = run_authorized_engine("ogata_banks_1d", cfg, auth, _engine_inputs())
    assert isinstance(run, AuthorizedEngineRun)
    assert run.engine.name == "ogata_banks_1d"
    assert run.engine.version == "1.0.0"
    # Deep attenuation for clay loam at 30.5 m -> functionally zero.
    assert run.result.C_receptor_steady_state < 1e-10
    assert run.result.retardation_factor > 1.0


def test_authorized_run_default_engine_when_name_none():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    run = run_authorized_engine(None, cfg, auth, _engine_inputs())
    assert run.engine.name == "ogata_banks_1d"


# ---------------------------------------------------------------------------
# Boundary refusals
# ---------------------------------------------------------------------------

def test_missing_authorization_is_refused():
    cfg = _cfg()
    with pytest.raises(AuthorizationMismatchError):
        run_authorized_engine("ogata_banks_1d", cfg, None, _engine_inputs())  # type: ignore[arg-type]


def test_config_mismatched_authorization_is_refused():
    auth = authorize_screening(_cfg(), _proceed_sad())
    other_cfg = _cfg(subsurface={"soil_type": "sand", "hydraulic_gradient": 0.5})
    with pytest.raises(AuthorizationMismatchError):
        run_authorized_engine("ogata_banks_1d", other_cfg, auth, _engine_inputs())


def _mutate(cfg: dict, path: tuple, value) -> dict:
    """Return a deep copy of ``cfg`` with the value at ``path`` replaced."""
    out = copy.deepcopy(cfg)
    node = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


@pytest.mark.parametrize(
    "path, new_value",
    [
        (("receptors", 0, "distance_m"), 99.0),          # receptor distance
        (("subsurface", "soil_type"), "silt_loam"),       # soil selection
        (("subsurface", "hydraulic_gradient"), 0.02),     # hydraulic gradient
        (("source", "treatment_class"), "Class II ATU"),  # treatment class
        (("constituents_to_evaluate",), ["e_coli"]),      # constituent selection
        (("physics", "dispersivity_method"), "xu_eckstein"),  # physics method
    ],
    ids=["receptor_distance", "soil", "gradient", "treatment_class",
         "constituents", "physics_method"],
)
def test_authorization_reuse_breaks_on_any_config_change(path, new_value):
    """Config-binding: an authorization minted for one config must not
    validate against a config that differs in ANY governed field."""
    base = _full_cfg()
    auth = authorize_screening(base, _proceed_sad())
    changed = _mutate(base, path, new_value)
    assert changed != base, "test setup: mutation did not change the config"
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(auth, changed)
    # And the governed execution path refuses too.
    with pytest.raises(AuthorizationMismatchError):
        run_authorized_engine("ogata_banks_1d", changed, auth, _engine_inputs())


def test_smuggled_nonpermitting_authorization_is_refused():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    smuggled = dataclasses.replace(auth, disposition="refuse")
    with pytest.raises(AuthorizationDeniedError):
        run_authorized_engine("ogata_banks_1d", cfg, smuggled, _engine_inputs())


def test_unknown_engine_is_refused():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    with pytest.raises(KeyError):
        run_authorized_engine("no_such_engine", cfg, auth, _engine_inputs())


# ---------------------------------------------------------------------------
# Direct-call refusal (the engine itself will not run tokenless)
# ---------------------------------------------------------------------------

def test_direct_evaluate_without_authorization_is_refused():
    with pytest.raises(AuthorizationError):
        physics_ogata_banks.evaluate(**_engine_inputs())


def test_direct_evaluate_with_valid_authorization_and_matching_config_runs():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    result = physics_ogata_banks.evaluate(
        **_engine_inputs(), authorization=auth, site_config=cfg
    )
    assert result.C_receptor_steady_state < 1e-10


def test_direct_evaluate_with_token_but_no_config_is_refused():
    """Closing the bypass: a permitting token is not enough; the engine
    requires the site_config it was bound to so it can verify config-binding."""
    auth = authorize_screening(_cfg(), _proceed_sad())
    with pytest.raises(AuthorizationError):
        physics_ogata_banks.evaluate(**_engine_inputs(), authorization=auth)


def test_direct_evaluate_with_token_and_mismatched_config_is_refused():
    """A valid token for config A cannot run the engine against config B."""
    auth = authorize_screening(_cfg(), _proceed_sad())
    other_cfg = _cfg(subsurface={"soil_type": "sand", "hydraulic_gradient": 0.5})
    with pytest.raises(AuthorizationMismatchError):
        physics_ogata_banks.evaluate(
            **_engine_inputs(), authorization=auth, site_config=other_cfg
        )


def test_get_engine_is_metadata_only_and_does_not_run():
    """get_engine returns the record but does not execute; calling the raw
    evaluate callable off the record without a token still refuses."""
    record = get_engine("ogata_banks_1d")
    assert record.name == "ogata_banks_1d"
    with pytest.raises(AuthorizationError):
        record.evaluate(**_engine_inputs())


# ---------------------------------------------------------------------------
# Attestation guard
# ---------------------------------------------------------------------------

def test_build_attestation_refuses_without_authorization(tmp_path):
    soil_db = REPO_ROOT / "data" / "soil_database.json"
    path_db = REPO_ROOT / "data" / "pathogens.json"
    with pytest.raises(ValueError):
        build_attestation(
            physics_engine="ogata_banks_1d",
            physics_engine_version="1.0.0",
            soil_db_path=soil_db,
            pathogens_db_path=path_db,
            site_config=_cfg(),
            authorization=None,
            warning_count=0,
            refusal_count=0,
        )


def test_build_attestation_binds_authorization_metadata():
    soil_db = REPO_ROOT / "data" / "soil_database.json"
    path_db = REPO_ROOT / "data" / "pathogens.json"
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    att = build_attestation(
        physics_engine="ogata_banks_1d",
        physics_engine_version="1.0.0",
        soil_db_path=soil_db,
        pathogens_db_path=path_db,
        site_config=cfg,
        authorization=auth,
        warning_count=0,
        refusal_count=0,
    )
    d = att.as_dict()
    assert d["authorization_id"] == auth.authorization_id
    assert d["authorization_schema_version"] == AUTHORIZATION_SCHEMA_VERSION
    assert d["preflight_disposition"] == "proceed"
    assert d["findings_digest"] == auth.findings_digest
    assert d["warning_count"] == 0 and d["refusal_count"] == 0


# ---------------------------------------------------------------------------
# End-to-end driver: attestation + authorization propagate to artifacts
# ---------------------------------------------------------------------------

def _write_cfg(tmp_path: Path, cfg: dict) -> Path:
    p = tmp_path / "site.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def _full_cfg(**overrides) -> dict:
    cfg = {
        "project": {
            "name": "Test Site", "site_id": "T-1",
            "engineer": "EOR, P.E.", "tceq_authority": "30 TAC Ch. 285",
        },
        "regulatory_zones": {"edwards_aquifer_recharge_zone": False, "karst_terrain": False},
        "subsurface": {
            "soil_type": "clay_loam", "depth_to_water_table_m": 4.5,
            "hydraulic_gradient": 0.01,
        },
        "source": {
            "treatment_class": "Class I Aerobic + Disinfection",
            "C0_overrides": {},
        },
        "physics": {"engine": "ogata_banks_1d", "dispersivity_method": "epa_ssg"},
        "receptors": [
            {"name": "Private well", "type": "private_well", "distance_m": 30.5},
            {"name": "Property line", "type": "property_boundary", "distance_m": 20.0},
        ],
        "comparison_scenarios": {"soils": ["sandy_loam"]},
        "constituents_to_evaluate": ["e_coli", "nitrate_as_N"],
        "reporting": {"nitrate_reporting_mode": "advective_reference_only"},
    }
    cfg.update(overrides)
    return cfg


def test_end_to_end_proceed_stamps_authorization(tmp_path):
    cfg_path = _write_cfg(tmp_path, _full_cfg())
    out_json = tmp_path / "r.json"
    out_txt = tmp_path / "r.txt"
    code = simulate.main([str(cfg_path), "--output", str(out_json), "--text", str(out_txt)])
    assert code == 0

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    att = artifact["attestation"]
    assert att["preflight_disposition"] == "proceed"
    assert att["warning_count"] == 0
    assert att["refusal_count"] == 0
    assert len(att["authorization_id"]) == 16
    assert att["authorization_schema_version"] == AUTHORIZATION_SCHEMA_VERSION

    auth_block = artifact["authorization"]
    assert auth_block["authorization_id"] == att["authorization_id"]
    assert auth_block["disposition"] == "proceed"
    # The text report carries the AUTHORIZATION section.
    assert "AUTHORIZATION" in out_txt.read_text(encoding="utf-8")


def test_end_to_end_warn_preserved_through_outputs(tmp_path):
    # A property line at 3.0 m triggers the SAD-005 warn disposition.
    cfg = _full_cfg(receptors=[
        {"name": "Private well", "type": "private_well", "distance_m": 30.5},
        {"name": "Property line", "type": "property_boundary", "distance_m": 3.0},
    ])
    cfg_path = _write_cfg(tmp_path, cfg)
    out_json = tmp_path / "r.json"
    out_txt = tmp_path / "r.txt"
    code = simulate.main([str(cfg_path), "--output", str(out_json), "--text", str(out_txt)])
    assert code == 0

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    att = artifact["attestation"]
    assert att["preflight_disposition"] == "warn"
    assert att["warning_count"] >= 1
    assert artifact["authorization"]["disposition"] == "warn"
    # The warning survives into both the preflight block and the text report.
    assert any(w["rule_id"] == "SAD-005" for w in artifact["preflight"]["warnings"])
    assert "PREFLIGHT WARNINGS" in out_txt.read_text(encoding="utf-8")


def test_end_to_end_refuse_denies_authorization_and_exits_2(tmp_path):
    cfg = _full_cfg(regulatory_zones={"edwards_aquifer_recharge_zone": True})
    cfg_path = _write_cfg(tmp_path, cfg)
    out_json = tmp_path / "r.json"
    out_txt = tmp_path / "r.txt"
    code = simulate.main([str(cfg_path), "--output", str(out_json), "--text", str(out_txt)])
    assert code == 2

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["disposition"] == "refuse"
    assert artifact["authorization"]["authorized"] is False
    assert any(r["rule_id"] == "SAD-001" for r in artifact["refusal_reasons"])
    assert "SITE REFUSED" in out_txt.read_text(encoding="utf-8")


def test_end_to_end_unknown_constituent_exits_1_cleanly(tmp_path, capsys):
    """A typo in constituents_to_evaluate must produce a clean user-facing
    error and exit code 1 — not an unhandled KeyError traceback."""
    cfg = _full_cfg(constituents_to_evaluate=["e_coli", "not_a_real_constituent"])
    cfg_path = _write_cfg(tmp_path, cfg)
    out_json = tmp_path / "r.json"
    out_txt = tmp_path / "r.txt"
    code = simulate.main([str(cfg_path), "--output", str(out_json), "--text", str(out_txt)])
    assert code == 1
    err = capsys.readouterr().err
    assert "Unknown constituent" in err
    assert "not_a_real_constituent" in err


def test_end_to_end_malformed_json_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json ", encoding="utf-8")
    code = simulate.main([str(bad)])
    assert code == 1
    assert "not valid JSON" in capsys.readouterr().err


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
