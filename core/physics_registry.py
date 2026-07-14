"""
physics_registry.py
===================

Canonical authority for physics engines in the OSSF groundwater screening
toolkit.

Every engine registered here MUST:
  * inherit ``AbstractPhysicsEngine``
  * declare ``ENGINE_NAME`` and ``ENGINE_VERSION``
  * have tests that pin its numerical correctness

Selection at run time is by engine name string. If the caller omits the
name, the default is ``ogata_banks_1d``.

Adding a new engine:
  1. Implement the module (subclass ``AbstractPhysicsEngine``).
  2. Add an ``EngineMetadata`` entry to ``ENGINES`` below.
  3. Add a singleton instance to ``_ENGINE_INSTANCES``.
  4. Write sanity-limit tests.
  5. Open an ADR under docs/adr documenting scope-of-applicability.

Public API (screening-3.0.0)
----------------------------
``get_engine(name)`` → ``EngineMetadata`` (metadata only, no callable).
``run_authorized_engine(name, executor, **kwargs)`` → ``AuthorizedEngineRun``.

``run_authorized_engine`` requires a ``SessionScopedExecutor`` obtained from
a live ``RunSession``. Passing a raw ``ScreeningAuthorization`` is a
``TypeError`` at the isinstance guard.
"""

from __future__ import annotations

from typing import Any, Dict, NamedTuple

from . import physics_ogata_banks
from .physics_engine_base import AbstractPhysicsEngine, EngineMetadata
from .run_session import SessionScopedExecutor


# ---------------------------------------------------------------------------
# Result wrapper
# ---------------------------------------------------------------------------

class AuthorizedEngineRun(NamedTuple):
    """Result of a governed engine invocation: engine result + metadata."""
    result: Any
    engine: EngineMetadata


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ENGINES: Dict[str, EngineMetadata] = {
    "ogata_banks_1d": EngineMetadata(
        name=physics_ogata_banks.ENGINE_NAME,
        version=physics_ogata_banks.ENGINE_VERSION,
        description=physics_ogata_banks.ENGINE_DESCRIPTION,
        scope_notes=physics_ogata_banks.ENGINE_SCOPE_NOTES,
    ),
}

# Separate dict of engine instances (not exposed in metadata).
_ENGINE_INSTANCES: Dict[str, AbstractPhysicsEngine] = {
    "ogata_banks_1d": physics_ogata_banks.get_engine_instance(),
}

DEFAULT_ENGINE = "ogata_banks_1d"


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_engine(name: str | None = None) -> EngineMetadata:
    """Look up an engine's metadata for INSPECTION ONLY.

    Returns ``EngineMetadata`` — plain data, no callable. Production
    execution must go through ``run_authorized_engine``.
    """
    if name is None:
        name = DEFAULT_ENGINE
    if name not in ENGINES:
        available = ", ".join(sorted(ENGINES))
        raise KeyError(
            f"Unknown physics engine '{name}'. Available: {available}."
        )
    return ENGINES[name]


def list_engines() -> list[str]:
    """Return sorted list of registered engine names."""
    return sorted(ENGINES)


def run_authorized_engine(
    engine_name: str | None,
    executor: SessionScopedExecutor,
    **engine_inputs: Any,
) -> AuthorizedEngineRun:
    """The single governed choke point for running a physics engine.

    Parameters
    ----------
    engine_name : engine key (``None`` → default).
    executor : ``SessionScopedExecutor`` from a live ``RunSession``.
    **engine_inputs : keyword arguments forwarded to the engine's
        ``_evaluate_impl``.

    Returns
    -------
    AuthorizedEngineRun
        The engine result plus its metadata.

    Raises
    ------
    TypeError
        if ``executor`` is not a ``SessionScopedExecutor``.
    SessionExpiredError
        if the session has exited.
    KeyError
        if ``engine_name`` is not registered.

    Design note
    -----------
    Full authorization validation (config-hash recompute, findings-digest
    check, id recompute) is NOT performed here. It was performed exactly
    once by ``RunSession.__enter__``. The ``executor.authorize_call()``
    inside ``AbstractPhysicsEngine.run()`` is the O(1) session-provenance
    check that replaces per-call re-validation.
    """
    if not isinstance(executor, SessionScopedExecutor):
        raise TypeError(
            "run_authorized_engine() requires a SessionScopedExecutor "
            f"(obtained from RunSession.__enter__), not "
            f"{type(executor).__name__!r}. "
            "Wrap engine calls in a RunSession block."
        )
    meta = get_engine(engine_name)
    instance = _ENGINE_INSTANCES[meta.name]
    result = instance.run(executor, **engine_inputs)
    return AuthorizedEngineRun(result=result, engine=meta)
