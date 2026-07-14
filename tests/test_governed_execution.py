"""
test_governed_execution.py
==========================

Tests that the physics boundary cannot be crossed without a valid
authorization carried inside a live RunSession.

Coverage:
  * valid session runs and returns engine metadata
  * raw authorization without session is rejected (TypeError)
  * expired executor is rejected (SessionExpiredError)
  * invalid / mismatched authorization fails at RunSession.__enter__
  * unknown engine name is rejected
  * get_engine returns metadata only (no callable fields)

Run: python -m pytest tests/test_governed_execution.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.preflight import RuleFinding, SiteAppropriatenessDetermination
from core.authorization import (
    AuthorizationMismatchError,
    AuthorizationDeniedError,
    authorize_screening,
    ScreeningAuthorization,
)
from core.run_session import (
    RunSession,
    SessionScopedExecutor,
    SessionExpiredError,
)
from core.physics_registry import (
    AuthorizedEngineRun,
    EngineMetadata,
    get_engine,
    run_authorized_engine,
)
from core.physics_ogata_banks import OgataBanksEngine
from core.physics_engine_base import EngineMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> dict:
    base = {
        "project": {"site_id": "EX-001"},
        "soil_class": "Sand",
        "hydraulic_gradient": 0.01,
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


def _refuse_sad() -> SiteAppropriatenessDetermination:
    return SiteAppropriatenessDetermination(
        disposition="refuse",
        findings=[
            RuleFinding(
                "SAD-001", "refuse",
                "Site is in EARZ.", "30 TAC 285.40-42"
            ),
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

def test_authorized_session_run_returns_result_and_engine_metadata():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    with RunSession(auth, cfg, {}, {}) as executor:
        run = run_authorized_engine("ogata_banks_1d", executor, **_engine_inputs())
    assert isinstance(run, AuthorizedEngineRun)
    assert run.engine.name == "ogata_banks_1d"
    assert run.engine.version == "1.0.0"
    assert run.result.retardation_factor > 1.0


def test_authorized_session_default_engine_when_name_none():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    with RunSession(auth, cfg, {}, {}) as executor:
        run = run_authorized_engine(None, executor, **_engine_inputs())
    assert run.engine.name == "ogata_banks_1d"


# ---------------------------------------------------------------------------
# Direct call with raw Authorization is rejected at runtime
# ---------------------------------------------------------------------------

def test_base_class_run_rejects_raw_authorization():
    """AbstractPhysicsEngine.run() must reject a raw ScreeningAuthorization
    at runtime, not just at the type-checker level.

    This is the belt-and-suspenders check: the type annotation says
    SessionScopedExecutor, and the isinstance guard enforces it at runtime.
    """
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    engine = OgataBanksEngine()

    with pytest.raises(TypeError) as exc_info:
        engine.run(auth, **_engine_inputs())

    assert "SessionScopedExecutor" in str(exc_info.value)


def test_run_authorized_engine_rejects_raw_authorization():
    """run_authorized_engine() must also reject a raw Authorization."""
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())

    with pytest.raises(TypeError) as exc_info:
        run_authorized_engine("ogata_banks_1d", auth, **_engine_inputs())

    assert "SessionScopedExecutor" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Authorization boundary failures
# ---------------------------------------------------------------------------

def test_missing_authorization_fails_at_session_entry():
    """Passing None as authorization must fail when entering the session."""
    cfg = _cfg()
    with pytest.raises(Exception):
        with RunSession(None, cfg, {}, {}) as executor:  # type: ignore[arg-type]
            pass


def test_refused_site_cannot_be_authorized():
    """A refused SAD must never yield a ScreeningAuthorization."""
    cfg = _cfg()
    with pytest.raises(AuthorizationDeniedError) as exc_info:
        authorize_screening(cfg, _refuse_sad())
    assert "SAD-001" in str(exc_info.value)


def test_config_mismatch_fails_at_session_entry():
    """Authorization minted for one config must fail when used with another."""
    auth = authorize_screening(_cfg(), _proceed_sad())
    other_cfg = _cfg(soil_class="Loam", hydraulic_gradient=0.05)

    with pytest.raises(AuthorizationMismatchError):
        with RunSession(auth, other_cfg, {}, {}) as executor:
            pass


def test_unknown_engine_name_is_rejected():
    """run_authorized_engine() with an unknown engine name raises KeyError."""
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())

    with RunSession(auth, cfg, {}, {}) as executor:
        with pytest.raises(KeyError):
            run_authorized_engine("nonexistent_engine", executor, **_engine_inputs())


# ---------------------------------------------------------------------------
# get_engine returns metadata only
# ---------------------------------------------------------------------------

def test_get_engine_returns_metadata_only():
    """get_engine() returns EngineMetadata — a plain data record, no callable."""
    meta = get_engine("ogata_banks_1d")
    assert isinstance(meta, EngineMetadata)
    assert meta.name == "ogata_banks_1d"
    assert meta.version == "1.0.0"
    # No callable field on the metadata record.
    assert not callable(getattr(meta, "evaluate", None))
    assert not callable(getattr(meta, "run", None))


def test_get_engine_default_when_none():
    meta = get_engine(None)
    assert meta.name == "ogata_banks_1d"


def test_get_engine_unknown_raises():
    with pytest.raises(KeyError):
        get_engine("does_not_exist")


# ---------------------------------------------------------------------------
# Session expiration
# ---------------------------------------------------------------------------

def test_expired_executor_rejected_by_run_authorized_engine():
    """An executor from an exited session must not be usable."""
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())

    with RunSession(auth, cfg, {}, {}) as executor:
        pass  # Immediately exits.

    with pytest.raises(SessionExpiredError):
        run_authorized_engine("ogata_banks_1d", executor, **_engine_inputs())
