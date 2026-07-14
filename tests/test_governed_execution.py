"""tests/test_governed_execution.py — ABC enforcement and governance tests.

Covers:

1. ``test_get_engine_is_metadata_only_and_does_not_run`` — asserts that
   ``get_engine()`` returns an ``EngineMetadata`` instance with no callable
   attributes (no ``evaluate``, no ``_evaluate_impl``, not callable itself).

2. ``test_run_method_cannot_be_overridden`` — asserts that defining a
   subclass that overrides ``run`` raises ``TypeError`` at class-definition
   time (``__init_subclass__`` guard), and that ``@typing.final`` signals
   the override to static type checkers.

3. ``test_register_engine_rejects_non_abc`` — asserts that attempting to
   register a plain dict, function, arbitrary class, or other object not
   inheriting ``AbstractPhysicsEngine`` raises ``TypeError``.

4. ``test_new_engine_inherits_authorization_guard`` — defines a minimal
   ``TestEngine(AbstractPhysicsEngine)`` with a trivial ``_evaluate_impl``
   that returns a sentinel, registers it, and verifies:
   a. ``run_authorized_engine("test_engine", bad_auth)`` raises
      ``AuthorizationError`` with the same behavior as the Ogata-Banks engine.
   b. ``run_authorized_engine("test_engine", good_auth)`` returns the
      sentinel without any additional authorization code in the subclass.
   This is the "by construction" test: the new engine gets the guard for
   free by virtue of subclassing the ABC.

These tests are expected to FAIL on the ``main`` branch (where
``AbstractPhysicsEngine`` does not exist) and PASS on this branch.

Falsification evidence
----------------------
On main:
    ImportError: cannot import name 'AbstractPhysicsEngine' from 'core.physics_registry'

On this branch:
    All tests in this file pass.
"""

from __future__ import annotations

import pytest

import core.physics_ogata_banks  # noqa: F401  (triggers registration)
from core.governance import Authorization, AuthorizationError
from core.physics_registry import (
    AbstractPhysicsEngine,
    EngineMetadata,
    ENGINES,
    get_engine,
    register_engine,
    run_authorized_engine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PERMITTED = Authorization(authorization_id="test-permit-001", disposition="permitted")
_DENIED = Authorization(authorization_id="test-deny-001", disposition="denied")
_PENDING = Authorization(authorization_id="test-pending-001", disposition="pending")


# ---------------------------------------------------------------------------
# 1. get_engine returns metadata only — no callable fields
# ---------------------------------------------------------------------------


def test_get_engine_is_metadata_only_and_does_not_run():
    """get_engine() must return EngineMetadata with no callable attributes.

    Asserts:
    - Return value is an EngineMetadata instance.
    - hasattr(meta, "evaluate") is False — EngineRecord.evaluate gone.
    - hasattr(meta, "_evaluate_impl") is False.
    - meta is not callable.
    - The metadata fields are strings (not functions).
    """
    meta = get_engine("ogata_banks_1d")

    assert isinstance(meta, EngineMetadata), (
        f"Expected EngineMetadata; got {type(meta).__name__}"
    )

    # No legacy EngineRecord.evaluate field.
    assert not hasattr(meta, "evaluate"), (
        "EngineMetadata must not have an 'evaluate' attribute."
    )

    # No private impl hook exposed.
    assert not hasattr(meta, "_evaluate_impl"), (
        "EngineMetadata must not have a '_evaluate_impl' attribute."
    )

    # The metadata object itself must not be callable.
    assert not callable(meta), "EngineMetadata must not be callable."

    # All fields must be plain strings, not callables.
    for field_name in ("name", "version", "scope_notes", "description"):
        value = getattr(meta, field_name)
        assert isinstance(value, str), (
            f"EngineMetadata.{field_name} must be a str; got {type(value).__name__}"
        )
        assert not callable(value), (
            f"EngineMetadata.{field_name} must not be callable."
        )

    # Spot-check values.
    assert meta.name == "ogata_banks_1d"
    assert meta.version == "1.0.0"


# ---------------------------------------------------------------------------
# 2. run() cannot be overridden
# ---------------------------------------------------------------------------


def test_run_method_cannot_be_overridden():
    """Defining a subclass that overrides run must raise TypeError at definition.

    The __init_subclass__ guard in AbstractPhysicsEngine raises TypeError
    immediately when Python processes the class body — before any instance
    is created.
    """
    with pytest.raises(TypeError, match="must not override"):

        class BadEngine(AbstractPhysicsEngine):  # type: ignore[misc]
            @property
            def name(self) -> str:
                return "bad_engine"

            @property
            def version(self) -> str:
                return "0.0.0"

            @property
            def scope_notes(self) -> str:
                return "test"

            @property
            def description(self) -> str:
                return "test"

            def _evaluate_impl(self, **kwargs):
                return None

            # This override must be rejected at class-definition time.
            def run(self, authorization, **kwargs):  # type: ignore[override]
                return "bypassed authorization"


# ---------------------------------------------------------------------------
# 3. register_engine rejects non-ABC instances
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_engine, description",
    [
        ({"name": "fake", "evaluate": lambda: None}, "dict"),
        (lambda **kw: None, "function"),
        (42, "integer"),
        ("ogata_banks_1d", "string"),
        (object(), "bare object"),
    ],
)
def test_register_engine_rejects_non_abc(bad_engine, description):
    """register_engine() must raise TypeError for non-AbstractPhysicsEngine."""
    with pytest.raises(TypeError, match="AbstractPhysicsEngine"):
        register_engine(bad_engine)


def test_register_engine_rejects_arbitrary_class_instance():
    """A class that does not inherit AbstractPhysicsEngine must be rejected."""

    class FakeEngine:
        name = "fake"
        version = "0.0.0"
        scope_notes = ""
        description = ""

        def evaluate(self, **kwargs):
            return None

    with pytest.raises(TypeError, match="AbstractPhysicsEngine"):
        register_engine(FakeEngine())


def test_register_engine_rejects_duplicate_name():
    """Registering a second engine with the same name must raise ValueError."""
    # ogata_banks_1d is already registered by module import.
    from core.physics_ogata_banks import OgataBanks1D

    duplicate = OgataBanks1D()
    with pytest.raises(ValueError, match="already registered"):
        register_engine(duplicate)


# ---------------------------------------------------------------------------
# 4. New engine inherits the authorization guard by construction
# ---------------------------------------------------------------------------

_SENTINEL = object()


class _TestEngine(AbstractPhysicsEngine):
    """Minimal engine used to verify by-construction authorization enforcement.

    This engine does not implement any authorization logic of its own; the
    guard is inherited from AbstractPhysicsEngine.run().
    """

    @property
    def name(self) -> str:
        return "_governed_test_engine"

    @property
    def version(self) -> str:
        return "0.0.1"

    @property
    def scope_notes(self) -> str:
        return "Test-only engine; not for production use."

    @property
    def description(self) -> str:
        return "Returns a sentinel object; no real physics."

    def _evaluate_impl(self, **kwargs):
        return _SENTINEL


@pytest.fixture
def registered_test_engine():
    """Register _TestEngine for the duration of a test, then remove it."""
    engine = _TestEngine()
    register_engine(engine)
    yield engine
    # Cleanup: remove from the global registry so tests are independent.
    ENGINES.pop("_governed_test_engine", None)


def test_new_engine_inherits_authorization_guard_denied(registered_test_engine):
    """A new engine with a denied authorization must raise AuthorizationError."""
    with pytest.raises(AuthorizationError):
        run_authorized_engine("_governed_test_engine", _DENIED)


def test_new_engine_inherits_authorization_guard_pending(registered_test_engine):
    """A new engine with a pending authorization must raise AuthorizationError."""
    with pytest.raises(AuthorizationError):
        run_authorized_engine("_governed_test_engine", _PENDING)


def test_new_engine_inherits_authorization_guard_bad_type(registered_test_engine):
    """A new engine passed a non-Authorization must raise AuthorizationError."""
    with pytest.raises(AuthorizationError):
        run_authorized_engine("_governed_test_engine", {"disposition": "permitted"})


def test_new_engine_inherits_authorization_guard_none(registered_test_engine):
    """A new engine passed None as authorization must raise AuthorizationError."""
    with pytest.raises(AuthorizationError):
        run_authorized_engine("_governed_test_engine", None)


def test_new_engine_runs_with_valid_authorization(registered_test_engine):
    """A new engine with a permitted authorization must return the sentinel."""
    result = run_authorized_engine("_governed_test_engine", _PERMITTED)
    assert result is _SENTINEL, (
        "Expected the sentinel object; authorization guard should pass through."
    )


def test_ogata_banks_authorization_rejected_denied():
    """Ogata-Banks engine must raise AuthorizationError for denied disposition."""
    with pytest.raises(AuthorizationError):
        run_authorized_engine(
            "ogata_banks_1d",
            _DENIED,
            x_m=10.0, t_days=100.0, v_m_per_day=0.1,
            D_m2_per_day=0.5, C0=1.0,
        )


def test_ogata_banks_authorization_rejected_bad_type():
    """Ogata-Banks engine must raise AuthorizationError for non-Authorization."""
    with pytest.raises(AuthorizationError):
        run_authorized_engine(
            "ogata_banks_1d",
            None,
            x_m=10.0, t_days=100.0, v_m_per_day=0.1,
            D_m2_per_day=0.5, C0=1.0,
        )


def test_ogata_banks_authorization_rejected_empty_id():
    """Ogata-Banks must raise AuthorizationError for an empty authorization_id."""
    bad_auth = Authorization(authorization_id="", disposition="permitted")
    with pytest.raises(AuthorizationError, match="non-empty"):
        run_authorized_engine(
            "ogata_banks_1d",
            bad_auth,
            x_m=10.0, t_days=100.0, v_m_per_day=0.1,
            D_m2_per_day=0.5, C0=1.0,
        )


# ---------------------------------------------------------------------------
# 5. EngineMetadata is frozen (immutable)
# ---------------------------------------------------------------------------


def test_engine_metadata_is_frozen():
    """EngineMetadata must not allow attribute mutation."""
    meta = get_engine("ogata_banks_1d")
    with pytest.raises((AttributeError, TypeError)):
        meta.name = "tampered"  # type: ignore[misc]
