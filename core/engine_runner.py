"""
engine_runner.py — Authorized physics engine execution.

Public surface (Tier 1 via core.__init__):
    run_authorized_engine
"""
from __future__ import annotations

from typing import Any

from core.authorization import Authorization
from core.physics_registry import get_engine
from core.run_session import RunSession, SessionScopedExecutor


def run_authorized_engine(
    authorization: Authorization,
    engine_name: str,
    config: dict[str, Any],
    *,
    session: RunSession | None = None,
) -> dict[str, Any]:
    """Run a named physics engine under an authorization record.

    Tier 1 — Consumer API.

    Ties together an :class:`~core.authorization.Authorization` record, a
    registered engine (looked up by name), and an optional
    :class:`~core.run_session.RunSession`.  The returned results dict is
    augmented with ``_authorization_id`` and ``_methodology_version`` keys so
    the run can be traced back to its authorization.

    Parameters
    ----------
    authorization:
        An active :class:`~core.authorization.Authorization` (from
        :func:`~core.authorization.build_authorization`).
    engine_name:
        Name of the engine to run, as registered via
        :func:`~core.physics_registry.register_engine`.
    config:
        Site configuration dictionary passed verbatim to the engine.
    session:
        Optional :class:`~core.run_session.RunSession`.  When provided, the
        engine call is bound to the session — :exc:`SessionExpiredError` is
        raised if the session has already expired.

    Returns
    -------
    dict
        Engine results dictionary, augmented with:

        - ``_authorization_id`` — the authorization ID derived by
          :func:`~core.authorization.build_authorization`.
        - ``_methodology_version`` — the methodology version from the
          authorization record.

    Raises
    ------
    KeyError
        If *engine_name* is not registered.
    SessionExpiredError
        If *session* is provided and has expired.
    """
    engine = get_engine(engine_name)

    if session is not None:
        executor = SessionScopedExecutor(session, engine.run)
        results: dict[str, Any] = executor(config)
    else:
        results = engine.run(config)

    results = dict(results)
    results["_authorization_id"] = authorization.authorization_id
    results["_methodology_version"] = authorization.methodology_version
    return results
