"""core/physics_registry.py — Abstract physics engine interface and registry.

Design: screening-2.0.0 — enforcement by construction (ADR-0005).

The central guarantee provided by this module is:

    **No physics calculation can execute without passing through the
    authorization gate, by construction, regardless of how an engine is
    implemented.**

This is achieved through an abstract base class (:class:`AbstractPhysicsEngine`)
whose :meth:`~AbstractPhysicsEngine.run` method is *final* — it always calls
:func:`~core.governance.ensure_execution_permitted` before dispatching to the
subclass's :meth:`~AbstractPhysicsEngine._evaluate_impl`.  Subclasses cannot
circumvent the gate by overriding ``run``; an ``__init_subclass__`` guard raises
:exc:`TypeError` at class-definition time if they try.

Public API
----------
- :class:`EngineMetadata` — frozen, view-only dataclass returned by
  :func:`get_engine`.  Contains no callable fields.
- :class:`AbstractPhysicsEngine` — ABC that all engines must subclass.
- :func:`register_engine` — add an engine to the registry.
- :func:`get_engine` — return :class:`EngineMetadata` (no callable fields).
- :func:`run_authorized_engine` — the only sanctioned execution path for
  external callers.

See also
--------
docs/adr/ADR-0005-abstract-physics-engine-interface.md
core/governance.py
"""

from __future__ import annotations

import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.governance import ensure_execution_permitted


# ---------------------------------------------------------------------------
# EngineMetadata — view-only dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineMetadata:
    """View-only metadata for a registered physics engine.

    Returned by :func:`get_engine`.  This dataclass intentionally contains
    **no callable fields** — it is impossible to invoke physics through this
    object.  External callers that need to run a calculation must use
    :func:`run_authorized_engine`.

    Fields
    ------
    name:
        Unique registry key (lower-snake-case), e.g. ``"ogata_banks_1d"``.
    version:
        SemVer-style engine version string, e.g. ``"1.0.0"``.
    scope_notes:
        Human-readable notes on applicability and limitations.
    description:
        One-line description of the physics method.
    """

    name: str
    version: str
    scope_notes: str
    description: str


# ---------------------------------------------------------------------------
# AbstractPhysicsEngine — ABC with final run()
# ---------------------------------------------------------------------------


class AbstractPhysicsEngine(ABC):
    """Abstract base class for all governed physics engines.

    Every concrete engine **must** inherit this class.  The
    :meth:`register_engine` function rejects anything that does not.

    Subclass contract
    -----------------
    Subclasses must implement the four abstract properties (``name``,
    ``version``, ``scope_notes``, ``description``) and the abstract method
    ``_evaluate_impl``.  They **must not** override :meth:`run` — the
    ``__init_subclass__`` hook raises :exc:`TypeError` at class-definition
    time if they attempt to do so.

    Authorization enforcement
    -------------------------
    :meth:`run` calls :func:`~core.governance.ensure_execution_permitted`
    unconditionally before dispatching to ``_evaluate_impl``.  This
    centralises the gate in one place rather than relying on each subclass
    to remember to call it.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Prevent subclasses from overriding the final :meth:`run` method.

        Raises :exc:`TypeError` at class-*definition* time (i.e. at import,
        not at runtime of a call) if any subclass places ``run`` in its own
        ``__dict__``.  Combined with :func:`typing.final`, this provides
        both runtime and type-checker enforcement.
        """
        super().__init_subclass__(**kwargs)
        if "run" in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must not override "
                "AbstractPhysicsEngine.run(). "
                "Override _evaluate_impl() instead to implement physics."
            )

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement these
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique engine identifier (lower-snake-case).

        Used as the registry key; must be stable across releases because
        call sites reference engines by this string.
        """

    @property
    @abstractmethod
    def version(self) -> str:
        """SemVer-style version string for this engine, e.g. ``"1.0.0"``."""

    @property
    @abstractmethod
    def scope_notes(self) -> str:
        """Human-readable notes on applicability and limitations."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description of the physics method."""

    @abstractmethod
    def _evaluate_impl(self, **kwargs: Any) -> Any:
        """Perform the physics calculation.

        This method is called exclusively from :meth:`run` after
        authorization has been verified.  External code must **not** call
        it directly — use :func:`run_authorized_engine` instead.

        Parameters
        ----------
        **kwargs:
            Engine-specific keyword arguments defined by each subclass.

        Returns
        -------
        Any
            Engine-specific result value or structure.
        """

    # ------------------------------------------------------------------
    # Concrete final methods — not overridable
    # ------------------------------------------------------------------

    @typing.final
    def run(self, authorization: object, **kwargs: Any) -> Any:
        """Execute the engine after verifying *authorization*.

        This method is **final** — subclasses cannot override it.  The
        ``__init_subclass__`` hook enforces this at class-definition time;
        :func:`typing.final` enforces it for static type checkers.

        Parameters
        ----------
        authorization:
            An :class:`~core.governance.Authorization` instance whose
            ``disposition`` must be ``"permitted"``.
        **kwargs:
            Engine-specific keyword arguments forwarded verbatim to
            :meth:`_evaluate_impl`.

        Returns
        -------
        Any
            The result of :meth:`_evaluate_impl`.

        Raises
        ------
        core.governance.AuthorizationError
            If *authorization* is missing, malformed, or not permitted.
        """
        ensure_execution_permitted(authorization)
        return self._evaluate_impl(**kwargs)

    def metadata(self) -> EngineMetadata:
        """Return a view-only :class:`EngineMetadata` record for this engine."""
        return EngineMetadata(
            name=self.name,
            version=self.version,
            scope_notes=self.scope_notes,
            description=self.description,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ENGINES: dict[str, AbstractPhysicsEngine] = {}
"""Global engine registry mapping engine name → instance.

Do not access this dictionary directly from application code.  Use
:func:`register_engine`, :func:`get_engine`, and
:func:`run_authorized_engine` instead.
"""


def register_engine(engine: AbstractPhysicsEngine) -> None:
    """Register *engine* in the global engine registry.

    Parameters
    ----------
    engine:
        Must be an instance of :class:`AbstractPhysicsEngine`.  The
        :attr:`~AbstractPhysicsEngine.name` property is used as the
        registry key.

    Raises
    ------
    TypeError
        If *engine* is not an :class:`AbstractPhysicsEngine` instance.
    ValueError
        If an engine with the same name is already registered.
    """
    if not isinstance(engine, AbstractPhysicsEngine):
        raise TypeError(
            "register_engine() requires an AbstractPhysicsEngine instance; "
            f"got {type(engine).__name__!r}."
        )
    key = engine.name
    if key in ENGINES:
        raise ValueError(
            f"An engine named {key!r} is already registered. "
            "Duplicate registration is not permitted."
        )
    ENGINES[key] = engine


def get_engine(name: str) -> EngineMetadata:
    """Return **metadata only** for the registered engine named *name*.

    The returned :class:`EngineMetadata` is a frozen dataclass with no
    callable fields.  It is impossible to execute physics through this
    object.  To run a calculation, use :func:`run_authorized_engine`.

    Parameters
    ----------
    name:
        Engine name as registered via :func:`register_engine`.

    Returns
    -------
    EngineMetadata
        View-only frozen dataclass.

    Raises
    ------
    KeyError
        If no engine with the given *name* is registered.
    """
    try:
        engine = ENGINES[name]
    except KeyError:
        raise KeyError(
            f"No engine named {name!r} is registered. "
            f"Registered engines: {sorted(ENGINES.keys())!r}"
        ) from None
    return engine.metadata()


def run_authorized_engine(
    name: str, authorization: object, **kwargs: Any
) -> Any:
    """Run a registered engine after verifying *authorization*.

    This is the **only** sanctioned path for external callers to execute
    physics.  It looks up the engine instance internally and calls
    :meth:`~AbstractPhysicsEngine.run`, which enforces authorization before
    dispatching to the physics.  External callers never see the raw engine
    instance.

    Parameters
    ----------
    name:
        Engine name as registered via :func:`register_engine`.
    authorization:
        An :class:`~core.governance.Authorization` instance whose
        ``disposition`` must be ``"permitted"``.
    **kwargs:
        Engine-specific keyword arguments forwarded to the engine's
        :meth:`~AbstractPhysicsEngine.run`.

    Returns
    -------
    Any
        The result returned by the engine's
        :meth:`~AbstractPhysicsEngine._evaluate_impl`.

    Raises
    ------
    KeyError
        If no engine with *name* is registered.
    core.governance.AuthorizationError
        If the authorization check fails.
    """
    try:
        engine = ENGINES[name]
    except KeyError:
        raise KeyError(
            f"No engine named {name!r} is registered. "
            f"Registered engines: {sorted(ENGINES.keys())!r}"
        ) from None
    return engine.run(authorization, **kwargs)
