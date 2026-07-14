"""
test_run_session.py
===================

Session-scope enforcement tests for the RunSession / SessionScopedExecutor
pattern (core/run_session.py).

Coverage:
  * test_session_validates_once        — full validation called exactly once
  * test_direct_call_with_authorization_fails  — engine.run(auth) raises TypeError
  * test_executor_expires_on_session_exit      — SessionExpiredError after exit
  * test_session_not_reentrant                 — double __enter__ raises
  * test_session_not_reusable                  — re-enter after exit raises
  * test_forged_executor_fails                 — fabricated token raises
  * test_concurrent_sessions_isolated          — two sessions, distinct tokens

Run: python -m pytest tests/test_run_session.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.preflight import RuleFinding, SiteAppropriatenessDetermination
from core.authorization import authorize_screening, ScreeningAuthorization
from core.run_session import (
    RunSession,
    SessionScopedExecutor,
    SessionExpiredError,
    SessionAlreadyActiveError,
    SessionNotReusableError,
    _LIVE_SESSIONS,
)
from core.physics_engine_base import AbstractPhysicsEngine
from core.physics_ogata_banks import OgataBanksEngine
from core.physics_registry import run_authorized_engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> dict:
    base = {"project": {"site_id": "TEST-001"}, "soil_class": "Sand"}
    base.update(overrides)
    return base


def _proceed_sad() -> SiteAppropriatenessDetermination:
    return SiteAppropriatenessDetermination(
        disposition="proceed",
        findings=[
            RuleFinding("SAD-001", "proceed", "Not in EARZ.", "30 TAC 285.40-42"),
        ],
    )


def _valid_auth(cfg=None) -> ScreeningAuthorization:
    if cfg is None:
        cfg = _cfg()
    return authorize_screening(cfg, _proceed_sad())


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
# Test: session validates exactly once
# ---------------------------------------------------------------------------

def test_session_validates_once():
    """Full validation (validate_authorization) must be called exactly once
    per session, regardless of how many engine calls occur inside the block.

    Falsification: before the RunSession fix, each engine call would invoke
    validate_authorization (which recomputes the config hash). After the fix,
    only RunSession.__enter__ calls it.
    """
    cfg = _cfg()
    auth = _valid_auth(cfg)

    call_count = 0

    import core.run_session as rs_mod
    original_validate = rs_mod.validate_authorization

    def counting_validate(authorization, site_config):
        nonlocal call_count
        call_count += 1
        return original_validate(authorization, site_config)

    with patch.object(rs_mod, "validate_authorization", side_effect=counting_validate):
        with RunSession(auth, cfg, {}, {}) as executor:
            # Simulate multiple engine calls (receptor × constituent).
            for _ in range(6):  # e.g. 2 receptors × 3 constituents
                run_authorized_engine("ogata_banks_1d", executor, **_engine_inputs())

    assert call_count == 1, (
        f"validate_authorization was called {call_count} time(s); "
        "expected exactly 1 (once per run, not per engine call)."
    )


# ---------------------------------------------------------------------------
# Test: direct call with Authorization raises
# ---------------------------------------------------------------------------

def test_direct_call_with_authorization_fails():
    """engine.run(authorization, **kwargs) outside a session must raise TypeError.

    Falsification: before the RunSession fix, engine.run() accepted a raw
    ScreeningAuthorization and the direct-call bypass was open. After the fix,
    run() only accepts a SessionScopedExecutor.
    """
    cfg = _cfg()
    auth = _valid_auth(cfg)
    engine = OgataBanksEngine()

    with pytest.raises(TypeError) as exc_info:
        engine.run(auth, **_engine_inputs())

    assert "SessionScopedExecutor" in str(exc_info.value)


def test_direct_call_with_none_fails():
    """engine.run(None, **kwargs) must also raise TypeError."""
    engine = OgataBanksEngine()
    with pytest.raises(TypeError):
        engine.run(None, **_engine_inputs())


def test_run_authorized_engine_with_authorization_fails():
    """run_authorized_engine() with a raw Authorization (not executor) raises."""
    cfg = _cfg()
    auth = _valid_auth(cfg)

    with pytest.raises(TypeError) as exc_info:
        run_authorized_engine("ogata_banks_1d", auth, **_engine_inputs())

    assert "SessionScopedExecutor" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test: executor expires on session exit
# ---------------------------------------------------------------------------

def test_executor_expires_on_session_exit():
    """An executor captured inside a ``with`` block must fail outside it."""
    cfg = _cfg()
    auth = _valid_auth(cfg)

    with RunSession(auth, cfg, {}, {}) as executor:
        executor.authorize_call()  # Must succeed inside.

    # Token removed from _LIVE_SESSIONS on __exit__.
    with pytest.raises(SessionExpiredError):
        executor.authorize_call()


def test_executor_expires_on_session_exit_via_engine():
    """run_authorized_engine() with an expired executor must raise."""
    cfg = _cfg()
    auth = _valid_auth(cfg)

    with RunSession(auth, cfg, {}, {}) as executor:
        pass  # Enter and immediately exit.

    with pytest.raises(SessionExpiredError):
        run_authorized_engine("ogata_banks_1d", executor, **_engine_inputs())


# ---------------------------------------------------------------------------
# Test: session not re-entrant
# ---------------------------------------------------------------------------

def test_session_not_reentrant():
    """Entering a live RunSession a second time must raise."""
    cfg = _cfg()
    auth = _valid_auth(cfg)
    session = RunSession(auth, cfg, {}, {})

    session.__enter__()
    try:
        with pytest.raises(SessionAlreadyActiveError):
            session.__enter__()
    finally:
        session.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Test: session not reusable
# ---------------------------------------------------------------------------

def test_session_not_reusable():
    """Re-entering a RunSession after it has exited must raise."""
    cfg = _cfg()
    auth = _valid_auth(cfg)

    with RunSession(auth, cfg, {}, {}) as executor:
        pass  # Normal entry and exit.

    session = RunSession(auth, cfg, {}, {})
    session._exited = True  # Simulate a session that was previously exited.
    with pytest.raises(SessionNotReusableError):
        session.__enter__()


def test_session_not_reusable_via_context_manager():
    """Using a RunSession as a context manager twice must raise on second use."""
    cfg = _cfg()
    auth = _valid_auth(cfg)
    session = RunSession(auth, cfg, {}, {})

    with session as executor:
        executor.authorize_call()

    with pytest.raises(SessionNotReusableError):
        with session:
            pass


# ---------------------------------------------------------------------------
# Test: forged executor fails
# ---------------------------------------------------------------------------

def test_forged_executor_fails():
    """A SessionScopedExecutor constructed with an arbitrary token (not in
    _LIVE_SESSIONS) must fail authorize_call().

    This verifies that consumers cannot synthesize a valid executor without
    going through a live RunSession.__enter__.
    """
    cfg = _cfg()
    auth = _valid_auth(cfg)

    # Fabricate a token that is NOT in _LIVE_SESSIONS.
    import secrets
    forged_token = secrets.token_bytes(32)
    # Ensure it's not accidentally in the set.
    _LIVE_SESSIONS.discard(forged_token)

    forged_executor = SessionScopedExecutor(_token=forged_token, _authorization=auth)

    with pytest.raises(SessionExpiredError):
        forged_executor.authorize_call()


def test_forged_executor_via_run_authorized_engine_fails():
    """run_authorized_engine() with a forged executor must raise."""
    cfg = _cfg()
    auth = _valid_auth(cfg)

    import secrets
    forged_token = secrets.token_bytes(32)
    _LIVE_SESSIONS.discard(forged_token)
    forged_executor = SessionScopedExecutor(_token=forged_token, _authorization=auth)

    with pytest.raises(SessionExpiredError):
        run_authorized_engine("ogata_banks_1d", forged_executor, **_engine_inputs())


# ---------------------------------------------------------------------------
# Test: concurrent sessions are isolated
# ---------------------------------------------------------------------------

def test_concurrent_sessions_isolated():
    """Two simultaneously live sessions must have distinct tokens, and each
    executor fails outside its own session.
    """
    cfg1 = _cfg(project={"site_id": "SITE-A"})
    cfg2 = _cfg(project={"site_id": "SITE-B"})
    auth1 = _valid_auth(cfg1)
    auth2 = _valid_auth(cfg2)

    session1 = RunSession(auth1, cfg1, {}, {})
    session2 = RunSession(auth2, cfg2, {}, {})

    exec1 = session1.__enter__()
    exec2 = session2.__enter__()

    try:
        assert exec1._token != exec2._token, "Tokens must be distinct across sessions."

        # Both executors work inside their sessions.
        exec1.authorize_call()
        exec2.authorize_call()
    finally:
        session1.__exit__(None, None, None)
        session2.__exit__(None, None, None)

    # Both fail after exit.
    with pytest.raises(SessionExpiredError):
        exec1.authorize_call()
    with pytest.raises(SessionExpiredError):
        exec2.authorize_call()


def test_session1_exit_does_not_expire_session2():
    """Exiting session 1 must not expire session 2's executor."""
    cfg1 = _cfg(project={"site_id": "SITE-A"})
    cfg2 = _cfg(project={"site_id": "SITE-B"})
    auth1 = _valid_auth(cfg1)
    auth2 = _valid_auth(cfg2)

    session1 = RunSession(auth1, cfg1, {}, {})
    session2 = RunSession(auth2, cfg2, {}, {})

    exec1 = session1.__enter__()
    exec2 = session2.__enter__()

    try:
        session1.__exit__(None, None, None)

        with pytest.raises(SessionExpiredError):
            exec1.authorize_call()

        # Session 2 still live.
        exec2.authorize_call()
    finally:
        session2.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Test: successful happy-path run
# ---------------------------------------------------------------------------

def test_happy_path_session_run():
    """End-to-end: RunSession + run_authorized_engine returns a result."""
    cfg = _cfg()
    auth = _valid_auth(cfg)

    with RunSession(auth, cfg, {}, {}) as executor:
        run = run_authorized_engine("ogata_banks_1d", executor, **_engine_inputs())

    assert run.engine.name == "ogata_banks_1d"
    assert run.engine.version == "1.0.0"
    assert run.result.retardation_factor > 1.0


def test_executor_metadata_properties():
    """SessionScopedExecutor exposes read-only metadata views."""
    cfg = _cfg()
    auth = _valid_auth(cfg)

    with RunSession(auth, cfg, {}, {}) as executor:
        assert executor.authorization_id == auth.authorization_id
        assert executor.disposition == auth.disposition
        assert executor.site_config_hash == auth.site_config_hash
