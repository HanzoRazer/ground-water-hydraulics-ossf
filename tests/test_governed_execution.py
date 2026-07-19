"""
test_governed_execution.py
==========================

Tests that the physics boundary cannot be crossed without a valid
authorization bound to a validated ``SiteCaseV1`` (OSSF-GW-002). This is the
enforcement half of the authorization contract: ``core/authorization.py``
defines the token; here we prove the registry adapter, the engine, and the
attestation refuse to run / seal without one.

Boundary cases covered:

  * a valid authorization runs the engine and returns engine metadata;
  * a missing authorization is refused;
  * a config-mismatched authorization is refused (config-binding);
  * changing ANY governed field of the validated case breaks reuse;
  * a smuggled non-permitting authorization is refused;
  * an unknown engine name is refused;
  * a DIRECT call to the engine's ``evaluate`` without a token / case is
    refused;
  * ``get_engine`` is metadata-only and does not run the engine;
  * ``build_attestation`` refuses to seal without a valid authorization and
    stamps the input schema version + normalized hash when it does.

Run: python -m pytest tests/test_governed_execution.py -v
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import (
    constituent,
    evidence_result_for,
    load_fixture_case,
    make_case,
    readiness_result_for,
    receptor,
    validated_evidence_result_for,
    validated_readiness_result_for,
)
from core import physics_ogata_banks
from core.contracts import DispersivityMethod, TreatmentLevel, site_case_hash
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

SOIL_DB = REPO_ROOT / "data" / "soil_database.json"
PATH_DB = REPO_ROOT / "data" / "pathogens.json"



def _auth(case, sad):
    ev = evidence_result_for(case)
    return authorize_screening(case, sad, ev, readiness_result_for(case, ev))

def _proceed_sad() -> SiteAppropriatenessDetermination:
    return SiteAppropriatenessDetermination(
        disposition="proceed",
        findings=[RuleFinding("SAD-001", "proceed", "Not in EARZ.", "30 TAC 285.40-42")],
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
    case = make_case()
    auth = _auth(case, _proceed_sad())
    run = run_authorized_engine("ogata_banks_1d", case, auth, _engine_inputs())
    assert isinstance(run, AuthorizedEngineRun)
    assert run.engine.name == "ogata_banks_1d"
    assert run.engine.version == "1.0.0"
    assert run.result.C_receptor_steady_state < 1e-10
    assert run.result.retardation_factor > 1.0


def test_authorized_run_default_engine_when_name_none():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    run = run_authorized_engine(None, case, auth, _engine_inputs())
    assert run.engine.name == "ogata_banks_1d"


# ---------------------------------------------------------------------------
# Boundary refusals
# ---------------------------------------------------------------------------

def test_missing_authorization_is_refused():
    case = make_case()
    with pytest.raises(AuthorizationMismatchError):
        run_authorized_engine("ogata_banks_1d", case, None, _engine_inputs())  # type: ignore[arg-type]


def test_config_mismatched_authorization_is_refused():
    auth = _auth(make_case(), _proceed_sad())
    other = make_case(soil_id="sand", gradient=0.05)
    with pytest.raises(AuthorizationMismatchError):
        run_authorized_engine("ogata_banks_1d", other, auth, _engine_inputs())


def _change(case, field):
    """Return a copy of ``case`` differing in exactly one governed field."""
    if field == "receptor_distance":
        return dataclasses.replace(case, receptors=(receptor("well", "private_well", 99.0, "Well"),))
    if field == "soil":
        return dataclasses.replace(
            case, subsurface=dataclasses.replace(case.subsurface, soil_id="silt_loam"))
    if field == "gradient":
        return dataclasses.replace(
            case, groundwater=dataclasses.replace(case.groundwater, hydraulic_gradient=0.02))
    if field == "treatment_level":
        return dataclasses.replace(
            case, treatment=dataclasses.replace(case.treatment, treatment_level=TreatmentLevel.ADVANCED_SECONDARY))
    if field == "constituents":
        return dataclasses.replace(case, constituents=(constituent("nitrate_as_N", "gating"),))
    if field == "dispersivity_method":
        return dataclasses.replace(
            case, physics=dataclasses.replace(case.physics, dispersivity_method=DispersivityMethod.XU_ECKSTEIN))
    raise AssertionError(field)


@pytest.mark.parametrize(
    "field",
    ["receptor_distance", "soil", "gradient", "treatment_level",
     "constituents", "dispersivity_method"],
)
def test_authorization_reuse_breaks_on_any_config_change(field):
    """Config-binding: an authorization minted for one validated case must
    not validate against a case that differs in ANY governed field."""
    base = make_case()
    auth = _auth(base, _proceed_sad())
    changed = _change(base, field)
    assert site_case_hash(changed) != site_case_hash(base)
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(auth, changed)
    with pytest.raises(AuthorizationMismatchError):
        run_authorized_engine("ogata_banks_1d", changed, auth, _engine_inputs())


def test_smuggled_nonpermitting_authorization_is_refused():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    smuggled = dataclasses.replace(auth, disposition="refuse")
    with pytest.raises(AuthorizationDeniedError):
        run_authorized_engine("ogata_banks_1d", case, smuggled, _engine_inputs())


def test_unknown_engine_is_refused():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    with pytest.raises(KeyError):
        run_authorized_engine("no_such_engine", case, auth, _engine_inputs())


# ---------------------------------------------------------------------------
# Direct-call refusal (the engine itself will not run tokenless)
# ---------------------------------------------------------------------------

def test_direct_evaluate_without_authorization_is_refused():
    with pytest.raises(AuthorizationError):
        physics_ogata_banks.evaluate(**_engine_inputs())


def test_direct_evaluate_with_valid_authorization_and_matching_case_runs():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    result = physics_ogata_banks.evaluate(
        **_engine_inputs(), authorization=auth, site_case=case
    )
    assert result.C_receptor_steady_state < 1e-10


def test_direct_evaluate_with_token_but_no_case_is_refused():
    """Closing the bypass: a permitting token is not enough; the engine
    requires the SiteCaseV1 it was bound to so it can verify config-binding."""
    auth = _auth(make_case(), _proceed_sad())
    with pytest.raises(AuthorizationError):
        physics_ogata_banks.evaluate(**_engine_inputs(), authorization=auth)


def test_direct_evaluate_with_token_and_mismatched_case_is_refused():
    auth = _auth(make_case(), _proceed_sad())
    other = make_case(soil_id="sand", gradient=0.05)
    with pytest.raises(AuthorizationMismatchError):
        physics_ogata_banks.evaluate(
            **_engine_inputs(), authorization=auth, site_case=other
        )


def test_get_engine_is_metadata_only_and_does_not_run():
    record = get_engine("ogata_banks_1d")
    assert record.name == "ogata_banks_1d"
    with pytest.raises(AuthorizationError):
        record.evaluate(**_engine_inputs())


# ---------------------------------------------------------------------------
# Attestation guard
# ---------------------------------------------------------------------------

def test_build_attestation_refuses_without_authorization():
    with pytest.raises(ValueError):
        build_attestation(
            physics_engine="ogata_banks_1d",
            physics_engine_version="1.0.0",
            soil_db_path=SOIL_DB,
            pathogens_db_path=PATH_DB,
            site_case=make_case(),
            authorization=None,
            warning_count=0,
            refusal_count=0,
        )


def test_build_attestation_binds_authorization_and_schema_metadata():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    att = build_attestation(
        physics_engine="ogata_banks_1d",
        physics_engine_version="1.0.0",
        soil_db_path=SOIL_DB,
        pathogens_db_path=PATH_DB,
        site_case=case,
        authorization=auth,
        warning_count=0,
        refusal_count=0,
    )
    d = att.as_dict()
    assert d["authorization_id"] == auth.authorization_id
    assert d["authorization_schema_version"] == AUTHORIZATION_SCHEMA_VERSION
    assert d["preflight_disposition"] == "proceed"
    assert d["findings_digest"] == auth.findings_digest
    # OSSF-GW-002: the stamp records the input schema version and normalized hash.
    assert d["input_schema_version"] == case.schema_version
    assert d["site_config_hash"] == site_case_hash(case)
    assert d["evidence_digest"] == auth.evidence_digest
    assert d["readiness_digest"] == auth.readiness_digest
    assert "evidence_review_summary" in d
    assert d["warning_count"] == 0 and d["refusal_count"] == 0


def test_build_attestation_refuses_config_mismatch():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    other = make_case(soil_id="sand", gradient=0.05)
    with pytest.raises(ValueError):
        build_attestation(
            physics_engine="ogata_banks_1d",
            physics_engine_version="1.0.0",
            soil_db_path=SOIL_DB,
            pathogens_db_path=PATH_DB,
            site_case=other,
            authorization=auth,
            warning_count=0,
            refusal_count=0,
        )


def test_authorized_run_with_real_evidence_gate_on_fixture():
    """End-to-end auth→engine path with real evidence + readiness gates."""
    case = load_fixture_case("proceed")
    evidence = validated_evidence_result_for(case)
    readiness = validated_readiness_result_for(case, evidence)
    auth = authorize_screening(case, _proceed_sad(), evidence, readiness)
    run = run_authorized_engine("ogata_banks_1d", case, auth, _engine_inputs())
    assert isinstance(run, AuthorizedEngineRun)
    assert run.engine.name == "ogata_banks_1d"
    att = build_attestation(
        physics_engine="ogata_banks_1d",
        physics_engine_version="1.0.0",
        soil_db_path=SOIL_DB,
        pathogens_db_path=PATH_DB,
        site_case=case,
        authorization=auth,
        warning_count=0,
        refusal_count=0,
        evidence_result=evidence,
        readiness_result=readiness,
    )
    assert att.evidence_digest == evidence.evidence_digest
    assert att.readiness_digest == readiness.readiness_digest


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
