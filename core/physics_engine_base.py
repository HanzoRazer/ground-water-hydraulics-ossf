"""
physics_engine_base.py
======================

Abstract base class for all physics engines in the OSSF groundwater
screening toolkit.

Design (ADR-0005, ADR-0006)
---------------------------
Every concrete engine inherits ``AbstractPhysicsEngine`` and implements
``_evaluate_impl(**kwargs)``. The public ``run()`` method:

  1. Asserts the caller passed a ``SessionScopedExecutor`` (type guard).
  2. Calls ``executor.authorize_call()`` — the O(1) session-provenance check.
  3. Dispatches to ``_evaluate_impl(**kwargs)``.

The signature of ``run()`` accepts **only** a ``SessionScopedExecutor``,
not a raw ``ScreeningAuthorization``. This is a deliberate narrowing:
callers must go through a ``RunSession`` to obtain an executor; there is no
path to call ``run()`` without a live session.

Direct-call bypass
------------------
A caller with a valid ``ScreeningAuthorization`` but no ``RunSession``
cannot invoke ``run()`` — they will get a ``TypeError`` from the
``isinstance`` guard and cannot produce a ``SessionScopedExecutor`` whose
token passes ``authorize_call()``.

Engine metadata
---------------
``EngineMetadata`` is a frozen dataclass of plain data fields (no
callables). ``get_engine()`` in the registry returns ``EngineMetadata``;
the callable ``evaluate`` is never exposed as metadata, preventing
metadata-inspection callers from accidentally running the engine.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from .run_session import SessionScopedExecutor


@dataclass(frozen=True)
class EngineMetadata:
    """Static metadata about a registered engine.

    Contains only plain data fields — no callables. This prevents a
    ``get_engine()`` caller from accidentally invoking the engine by
    reaching through the metadata record.
    """
    name: str
    version: str
    description: str
    scope_notes: str


class AbstractPhysicsEngine(abc.ABC):
    """Base class for all OSSF physics engines.

    Subclasses implement ``_evaluate_impl(**kwargs)`` and declare
    ``ENGINE_NAME`` and ``ENGINE_VERSION`` class attributes.

    The ``run()`` method is intentionally final in its guard logic: it
    always checks session provenance before dispatching. Subclasses must
    not override ``run()``.
    """

    ENGINE_NAME: str
    ENGINE_VERSION: str

    def run(self, executor: SessionScopedExecutor, **kwargs: Any) -> Any:
        """Execute the engine under a live session.

        Parameters
        ----------
        executor : SessionScopedExecutor
            Obtained from ``RunSession.__enter__``. Must belong to a live
            session; ``authorize_call()`` raises ``SessionExpiredError``
            otherwise.

        Returns
        -------
        Any
            The engine-specific result object.

        Raises
        ------
        TypeError
            if ``executor`` is not a ``SessionScopedExecutor`` (direct call
            with a raw ``ScreeningAuthorization`` or any other object).
        SessionExpiredError
            if the session has exited or the token was forged.
        """
        if not isinstance(executor, SessionScopedExecutor):
            raise TypeError(
                f"{type(self).__name__}.run() requires a SessionScopedExecutor "
                f"(obtained from RunSession.__enter__), not "
                f"{type(executor).__name__!r}. "
                "Direct calls with a raw ScreeningAuthorization are rejected. "
                "Wrap engine calls in a RunSession block."
            )
        executor.authorize_call()
        return self._evaluate_impl(**kwargs)

    @abc.abstractmethod
    def _evaluate_impl(self, **kwargs: Any) -> Any:
        """Engine-specific computation. Called only after authorization."""

    @classmethod
    def metadata(cls) -> EngineMetadata:
        """Return static metadata about this engine."""
        return EngineMetadata(
            name=cls.ENGINE_NAME,
            version=cls.ENGINE_VERSION,
            description=getattr(cls, "ENGINE_DESCRIPTION", ""),
            scope_notes=getattr(cls, "ENGINE_SCOPE_NOTES", ""),
        )
