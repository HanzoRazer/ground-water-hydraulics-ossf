"""
physics_registry.py — Abstract physics engine interface and global registry.

Public surface (Tier 1 via core.__init__):
    EngineMetadata, get_engine, list_engines

Public surface (Tier 2 via core.__init__):
    AbstractPhysicsEngine, register_engine
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Registry (module-level singleton)
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, tuple[AbstractPhysicsEngine, EngineMetadata]] = {}


@dataclass(frozen=True)
class EngineMetadata:
    """Metadata record for a registered physics engine.

    Tier 1 — Consumer API.

    Attributes
    ----------
    name:
        Short, unique identifier for the engine (used as registry key).
    version:
        Semantic version string for the engine implementation.
    description:
        One-sentence human-readable description.
    """

    name: str
    version: str
    description: str


class AbstractPhysicsEngine(abc.ABC):
    """Abstract base class for physics engines.

    Tier 2 — Extension API (for engine authors).

    Subclass this to create a new screening engine, implement
    :meth:`metadata` and :meth:`run`, then pass an instance to
    :func:`register_engine`.
    """

    @abc.abstractmethod
    def metadata(self) -> EngineMetadata:
        """Return the :class:`EngineMetadata` for this engine."""

    @abc.abstractmethod
    def run(self, config: dict[str, Any]) -> dict[str, Any]:
        """Execute the engine for the given site configuration.

        Parameters
        ----------
        config:
            Parsed site configuration dictionary.

        Returns
        -------
        dict
            Structured results dictionary.
        """


def register_engine(engine: AbstractPhysicsEngine) -> AbstractPhysicsEngine:
    """Register a physics engine in the global registry.

    Tier 2 — Extension API.

    May be used as a plain call or as a decorator on an instance assignment::

        my_engine = register_engine(MyEngine())

    Parameters
    ----------
    engine:
        An instantiated :class:`AbstractPhysicsEngine`.  The engine's
        ``metadata().name`` is used as the registry key; registering a
        second engine with the same name overwrites the first.

    Returns
    -------
    AbstractPhysicsEngine
        The same engine instance, for chained or decorator use.
    """
    meta = engine.metadata()
    _REGISTRY[meta.name] = (engine, meta)
    return engine


def get_engine(name: str) -> AbstractPhysicsEngine:
    """Look up a registered engine by name.

    Tier 1 — Consumer API.

    Parameters
    ----------
    name:
        Engine name as used in :func:`register_engine`.

    Returns
    -------
    AbstractPhysicsEngine

    Raises
    ------
    KeyError
        If no engine with that name is registered.
    """
    if name not in _REGISTRY:
        raise KeyError(f"No engine registered with name {name!r}.")
    return _REGISTRY[name][0]


def list_engines() -> list[EngineMetadata]:
    """Return metadata for all registered engines, sorted by name.

    Tier 1 — Consumer API.

    Returns
    -------
    list[EngineMetadata]
        Sorted by :attr:`EngineMetadata.name`.
    """
    return sorted(
        (meta for _, meta in _REGISTRY.values()),
        key=lambda m: m.name,
    )
