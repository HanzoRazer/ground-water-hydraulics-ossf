"""
run_session.py
==============

RunSession-scoped authorization for the OSSF groundwater screening tool.

Design (ADR-0006)
-----------------
Authorization validation is expensive: it re-hashes the full site config and
recomputes finding digests to detect tampering. In the receptor × constituent
inner loop that drives a full screening run, calling ``validate_authorization``
on every engine invocation is O(receptors × constituents) full validations.

This module introduces a **session scope** that validates exactly once:

  1. ``RunSession.__enter__`` calls ``validate_authorization`` (the full,
     expensive check) exactly once.
  2. On success, a fresh ``_session_token`` (``secrets.token_bytes(32)``) is
     generated and added to the module-private ``_LIVE_SESSIONS`` set.
  3. A ``SessionScopedExecutor`` — carrying the token and the pre-validated
     authorization — is yielded to the caller.
  4. ``RunSession.__exit__`` removes the token from ``_LIVE_SESSIONS``
     unconditionally (even if the body raised), invalidating the executor.

Per-call guard (``SessionScopedExecutor.authorize_call``)
----------------------------------------------------------
``authorize_call()`` is the O(1) check called by every engine invocation.
It tests only ``_token in _LIVE_SESSIONS`` — a Python set membership check.
No re-hashing. No config comparison.

Direct-call bypass remains closed
----------------------------------
Callers with a valid ``ScreeningAuthorization`` but no live ``RunSession``
cannot execute an engine. The engine's ``run()`` method accepts only a
``SessionScopedExecutor``, not a raw ``ScreeningAuthorization``. Producing a
valid executor requires going through ``RunSession.__enter__``, which means
going through ``validate_authorization``.

A ``SessionScopedExecutor`` constructed directly (outside a live session)
cannot produce a token that passes ``authorize_call()``: any token not in
``_LIVE_SESSIONS`` raises ``SessionExpiredError``.

Constraints
-----------
- Not re-entrant: entering a ``RunSession`` that is already active raises.
- Not reusable: exiting and re-entering the same ``RunSession`` raises.
- Single-process: ``_LIVE_SESSIONS`` is a module-level in-process set; it
  is NOT safe to share ``SessionScopedExecutor`` instances across processes
  (document this as a known limitation in ADR-0006).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from .authorization import ScreeningAuthorization, validate_authorization


# ---------------------------------------------------------------------------
# Module-private live-session registry
# ---------------------------------------------------------------------------

_LIVE_SESSIONS: set[bytes] = set()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SessionExpiredError(RuntimeError):
    """Raised by ``SessionScopedExecutor.authorize_call()`` when the token is
    not in ``_LIVE_SESSIONS`` — either the ``RunSession`` has exited or the
    executor was constructed outside a live session."""


class SessionAlreadyActiveError(RuntimeError):
    """Raised when attempting to ``__enter__`` a ``RunSession`` that is
    already active (re-entrancy guard)."""


class SessionNotReusableError(RuntimeError):
    """Raised when attempting to ``__enter__`` a ``RunSession`` that has
    already been exited (reuse guard)."""


# ---------------------------------------------------------------------------
# SessionScopedExecutor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionScopedExecutor:
    """Opaque execution ticket produced by a live ``RunSession``.

    Carries a private session token and the pre-validated authorization.
    The only public action is ``authorize_call()``, which performs an O(1)
    set membership check to verify the session is still active.

    Consumers receive this object from ``RunSession.__enter__`` and pass it
    to ``run_authorized_engine`` or ``AbstractPhysicsEngine.run()``. They
    cannot construct a valid instance themselves because any token they
    fabricate will not be in ``_LIVE_SESSIONS``.

    The ``_authorization`` field is private by convention (underscore prefix).
    Do not use it to bypass the session boundary.
    """
    _token: bytes
    _authorization: ScreeningAuthorization

    def authorize_call(self) -> None:
        """O(1) guard: assert this executor belongs to a live session.

        Raises
        ------
        SessionExpiredError
            if the ``RunSession`` has exited or the token was forged.
        """
        if self._token not in _LIVE_SESSIONS:
            raise SessionExpiredError(
                "SessionScopedExecutor.authorize_call() failed: the session "
                "token is not in the live-session registry. Either the "
                "RunSession has exited or the executor was constructed "
                "outside a live session."
            )

    @property
    def authorization_id(self) -> str:
        """Read-only view of the authorization id for logging/attestation."""
        return self._authorization.authorization_id

    @property
    def disposition(self) -> str:
        """Read-only view of the preflight disposition."""
        return self._authorization.disposition

    @property
    def site_config_hash(self) -> str:
        """Read-only view of the bound site config hash."""
        return self._authorization.site_config_hash


# ---------------------------------------------------------------------------
# RunSession
# ---------------------------------------------------------------------------

class RunSession:
    """Context manager that validates authorization exactly once per run.

    Usage
    -----
    ::

        with RunSession(authorization, site_config, soils_db, constituents_db) as executor:
            for receptor in receptors:
                for constituent in constituents:
                    result = run_authorized_engine(
                        engine_name, executor, **kwargs
                    )

    ``__enter__`` calls ``validate_authorization`` once, generates a fresh
    session token, and yields a ``SessionScopedExecutor``. Every engine call
    inside the block calls ``executor.authorize_call()`` — an O(1) set check.
    ``__exit__`` removes the token unconditionally, expiring all executors.

    Parameters
    ----------
    authorization : ScreeningAuthorization
        The token minted by ``authorize_screening``.
    site_config : dict
        The exact site configuration dict used for config-binding validation.
    soils_db : dict
        Soils database (passed for context; future validators may use it).
    constituents_db : dict
        Constituents database (same note).
    """

    def __init__(
        self,
        authorization: ScreeningAuthorization,
        site_config: dict,
        soils_db: dict,
        constituents_db: dict,
    ) -> None:
        self._authorization = authorization
        self._site_config = site_config
        self._soils_db = soils_db
        self._constituents_db = constituents_db
        self._token: bytes | None = None
        self._entered: bool = False
        self._exited: bool = False

    def __enter__(self) -> SessionScopedExecutor:
        if self._exited:
            raise SessionNotReusableError(
                "RunSession cannot be reused: it has already been exited. "
                "Create a new RunSession for the next run."
            )
        if self._entered:
            raise SessionAlreadyActiveError(
                "RunSession is not re-entrant: __enter__ was called while "
                "the session is already active."
            )

        # Full authorization validation — exactly once per session.
        validate_authorization(self._authorization, self._site_config)

        # Generate a fresh per-session token and register it.
        token = secrets.token_bytes(32)
        _LIVE_SESSIONS.add(token)
        self._token = token
        self._entered = True

        return SessionScopedExecutor(
            _token=token,
            _authorization=self._authorization,
        )

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        # Unconditional cleanup: remove the token even if the body raised.
        if self._token is not None:
            _LIVE_SESSIONS.discard(self._token)
        self._exited = True
        # Do not suppress exceptions.
        return None
