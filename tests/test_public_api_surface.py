"""
test_public_api_surface.py — Locks the core public API surface.

Two categories of tests:

1. **Positive coverage** — Every symbol listed in ``core.__all__`` is importable
   from ``core``, and ``core.__all__`` matches the expected locked-in list.
   This test locks the public surface; changing ``__all__`` requires updating
   this test AND writing an ADR entry (see ADR-0007).

2. **Negative coverage** — Every Tier 3 symbol identified in ADR-0007 is
   confirmed NOT importable from ``core`` (only from its specific module).
   This is what makes the trim mechanical rather than aesthetic.

To verify both categories:

    python -m pytest tests/test_public_api_surface.py -v
"""

from __future__ import annotations

import importlib

import pytest

import core


# ============================================================================
# Expected surface — update this list ONLY when writing a new ADR entry
# ============================================================================

_EXPECTED_ALL: list[str] = [
    # Tier 1 — Consumer API
    "RunSession",
    "SessionScopedExecutor",
    "SessionExpiredError",
    "build_authorization",
    "AuthorizationError",
    "EngineMetadata",
    "get_engine",
    "list_engines",
    "run_authorized_engine",
    "evaluate_site",
    "ScreeningScopeError",
    "METHODOLOGY_VERSION",
    "PREFLIGHT_RULESET_VERSION",
    "AUTHORIZATION_SCHEMA_VERSION",
    "OUTPUT_CONTRACT_VERSION",
    # Tier 2 — Extension API
    "AbstractPhysicsEngine",
    "register_engine",
    "methodology_attested",
    "screening_boundary",
    "RuleFinding",
    "SiteAppropriatenessDetermination",
]

# ============================================================================
# Tier 3 symbols — these must NOT be importable from core
# ============================================================================

_TIER3_SYMBOLS = [
    # core.governance — hash helpers
    "sha256_of_file",
    "sha256_of_json_stable",
    # core.authorization — private derivation
    "_derive_authorization_id",
    # core.run_session — private session registry
    "_LIVE_SESSIONS",
    # core.preflight — individual rule functions
    "rule_soil_class_in_database",
    "rule_hydraulic_gradient_positive",
    "rule_at_least_one_receptor",
    # core.transport — physics primitives
    "_U",
    "concentration_at_time",
    "concentration_steady_state",
]


# ============================================================================
# 1. Positive coverage
# ============================================================================

class TestPositiveCoverage:
    """Every Tier 1 and Tier 2 symbol is importable from core."""

    def test_all_exists(self):
        """core.__all__ must be defined."""
        assert hasattr(core, "__all__"), "core.__all__ is not defined"

    def test_all_matches_expected(self):
        """core.__all__ must exactly match the locked-in expected list.

        If this test fails, you have either added or removed a symbol from
        core.__all__ without updating this test — which means you need to
        write or update an ADR entry.
        """
        actual = sorted(core.__all__)
        expected = sorted(_EXPECTED_ALL)
        assert actual == expected, (
            f"core.__all__ does not match expected surface.\n"
            f"Extra symbols: {sorted(set(actual) - set(expected))}\n"
            f"Missing symbols: {sorted(set(expected) - set(actual))}"
        )

    @pytest.mark.parametrize("name", _EXPECTED_ALL)
    def test_symbol_importable_from_core(self, name: str):
        """Each symbol in __all__ must be accessible as an attribute of core."""
        assert hasattr(core, name), (
            f"{name!r} is listed in core.__all__ but is not accessible as "
            f"core.{name}"
        )

    def test_all_contents_accessible(self):
        """Every entry in __all__ resolves to a non-None attribute."""
        missing = [name for name in core.__all__ if not hasattr(core, name)]
        assert not missing, (
            f"The following symbols are in __all__ but missing from core: "
            f"{missing}"
        )


# ============================================================================
# 2. Negative coverage
# ============================================================================

class TestNegativeCoverage:
    """Tier 3 symbols are NOT importable from core."""

    @pytest.mark.parametrize("name", _TIER3_SYMBOLS)
    def test_tier3_symbol_not_in_core_all(self, name: str):
        """Tier 3 symbols must not appear in core.__all__."""
        assert name not in core.__all__, (
            f"{name!r} is a Tier 3 symbol but appears in core.__all__. "
            f"See ADR-0007."
        )

    @pytest.mark.parametrize("name", _TIER3_SYMBOLS)
    def test_tier3_symbol_not_importable_from_core(self, name: str):
        """``from core import <tier3>`` must raise ImportError."""
        with pytest.raises((ImportError, AttributeError)):
            # We use getattr on the already-imported module object to avoid
            # Python's submodule fallback (which would try to import
            # core.<name> as a module before raising ImportError).
            val = getattr(core, name)
            # If getattr succeeds, the symbol is unexpectedly present — fail.
            raise AssertionError(
                f"{name!r} is unexpectedly accessible as core.{name} "
                f"(got {val!r}).  It is a Tier 3 symbol and must not be "
                f"re-exported from core.__init__."
            )

    @pytest.mark.parametrize("name,module", [
        ("sha256_of_file", "core.governance"),
        ("sha256_of_json_stable", "core.governance"),
        ("_derive_authorization_id", "core.authorization"),
        ("_LIVE_SESSIONS", "core.run_session"),
        ("rule_soil_class_in_database", "core.preflight"),
        ("rule_hydraulic_gradient_positive", "core.preflight"),
        ("rule_at_least_one_receptor", "core.preflight"),
        ("_U", "core.transport"),
        ("concentration_at_time", "core.transport"),
        ("concentration_steady_state", "core.transport"),
    ])
    def test_tier3_symbol_importable_from_specific_module(
        self, name: str, module: str
    ):
        """Tier 3 symbols must be importable from their specific module."""
        mod = importlib.import_module(module)
        assert hasattr(mod, name), (
            f"{name!r} is not accessible from {module}.  "
            f"Tier 3 symbols must be reachable from their specific module."
        )


# ============================================================================
# 3. Smoke tests for key Tier 1 symbols
# ============================================================================

class TestTier1Smoke:
    """Light smoke tests confirming Tier 1 symbols behave as advertised."""

    def test_methodology_version_is_screening_3_minor(self):
        """METHODOLOGY_VERSION must be at screening-3.x.y."""
        assert core.METHODOLOGY_VERSION.startswith("screening-3."), (
            f"Expected METHODOLOGY_VERSION to start with 'screening-3.', "
            f"got {core.METHODOLOGY_VERSION!r}"
        )

    def test_build_authorization_returns_object_with_id(self):
        auth = core.build_authorization(
            site_id="TEST-001",
            methodology_version=core.METHODOLOGY_VERSION,
            issued_utc="2026-01-01T00:00:00+00:00",
        )
        assert auth.authorization_id, "authorization_id must be non-empty"
        assert auth.site_id == "TEST-001"

    def test_build_authorization_raises_on_empty_site_id(self):
        with pytest.raises(core.AuthorizationError):
            core.build_authorization(
                site_id="",
                methodology_version=core.METHODOLOGY_VERSION,
                issued_utc="2026-01-01T00:00:00+00:00",
            )

    def test_run_session_context_manager_expires(self):
        session = core.RunSession(
            site_id="S-001",
            methodology_version=core.METHODOLOGY_VERSION,
        )
        assert not session.is_expired
        with session:
            assert not session.is_expired
        assert session.is_expired

    def test_session_expired_error_raised_after_expiry(self):
        session = core.RunSession(
            site_id="S-002",
            methodology_version=core.METHODOLOGY_VERSION,
        )
        session.expire()
        executor = core.SessionScopedExecutor(session, lambda: None)
        with pytest.raises(core.SessionExpiredError):
            executor()

    def test_list_engines_returns_list(self):
        result = core.list_engines()
        assert isinstance(result, list)

    def test_evaluate_site_returns_determination(self):
        config = {
            "site_id": "TEST-SITE",
            "soil_class": "clay_loam",
            "hydraulic_gradient": 0.01,
            "receptors": [{"name": "R1", "distance_m": 30}],
        }
        soils_db = {"clay_loam": {"K_m_per_day": 0.01, "n_e": 0.45}}
        det = core.evaluate_site(config, soils_db)
        assert det.site_id == "TEST-SITE"
        assert det.is_appropriate is True

    def test_evaluate_site_raises_scope_error_on_fatal(self):
        config = {
            "site_id": "BAD-SITE",
            "soil_class": "nonexistent_soil",
            "hydraulic_gradient": 0.01,
            "receptors": [{"name": "R1", "distance_m": 30}],
        }
        soils_db = {}
        with pytest.raises(core.ScreeningScopeError):
            core.evaluate_site(config, soils_db)


# ============================================================================
# 4. Smoke tests for key Tier 2 symbols
# ============================================================================

class TestTier2Smoke:
    """Light smoke tests confirming Tier 2 symbols behave as advertised."""

    def test_abstract_physics_engine_is_abstract(self):
        """AbstractPhysicsEngine cannot be instantiated directly."""
        with pytest.raises(TypeError):
            core.AbstractPhysicsEngine()  # type: ignore[abstract]

    def test_methodology_attested_decorator(self):
        @core.methodology_attested
        def my_fn():
            return 42

        assert my_fn.__attested__ is True
        assert my_fn.__methodology_version__ == core.METHODOLOGY_VERSION
        assert my_fn() == 42

    def test_screening_boundary_decorator(self):
        @core.screening_boundary
        def my_boundary():
            return "ok"

        assert my_boundary.__screening_boundary__ is True
        assert my_boundary() == "ok"

    def test_rule_finding_dataclass(self):
        from core.preflight import FindingSeverity
        finding = core.RuleFinding(
            rule_id="TEST-001",
            severity=FindingSeverity.WARNING,
            message="Test warning",
        )
        assert finding.rule_id == "TEST-001"

    def test_register_and_get_engine(self):
        class _TestEngine(core.AbstractPhysicsEngine):
            def metadata(self):
                return core.EngineMetadata(
                    name="test-engine-adr7",
                    version="0.0.1",
                    description="Smoke test engine",
                )

            def run(self, config):
                return {"status": "ok"}

        engine = _TestEngine()
        core.register_engine(engine)
        retrieved = core.get_engine("test-engine-adr7")
        assert retrieved is engine

        metas = core.list_engines()
        names = [m.name for m in metas]
        assert "test-engine-adr7" in names
