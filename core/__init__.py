"""
core — Groundwater screening calculation modules.

Public API surface
------------------
This package exposes exactly the symbols listed in ``__all__``.  Every symbol
here is committed to backward-compatibility under the MINOR / MAJOR versioning
policy documented in ``docs/adr/ADR-0007-public-api-surface.md``.

Tier 1 — Consumer API
    Symbols for downstream users running the tool as a library.
    Stable across MINOR bumps; removal requires a MAJOR bump.

Tier 2 — Extension API
    Symbols for developers writing new engines or preflight rules.
    Stable across MINOR bumps; removal requires a MAJOR bump.

Tier 3 — Internal
    Symbols in individual ``core.<module>`` submodules, reachable via
    ``from core.<module> import X`` but NOT re-exported here.
    Refactorable in any MINOR bump.

For the full rationale and the authoritative symbol table see ADR-0007.
"""

# ============================================================================
# Tier 1: Consumer API
# ============================================================================
from core.run_session import RunSession, SessionScopedExecutor, SessionExpiredError
from core.authorization import build_authorization, AuthorizationError
from core.physics_registry import EngineMetadata, get_engine, list_engines
from core.engine_runner import run_authorized_engine
from core.preflight import evaluate_site, ScreeningScopeError
from core.governance import (
    METHODOLOGY_VERSION,
    PREFLIGHT_RULESET_VERSION,
    AUTHORIZATION_SCHEMA_VERSION,
    OUTPUT_CONTRACT_VERSION,
)

# ============================================================================
# Tier 2: Extension API
# ============================================================================
from core.physics_registry import AbstractPhysicsEngine, register_engine
from core.governance import methodology_attested, screening_boundary
from core.preflight import RuleFinding, SiteAppropriatenessDetermination

__all__ = [
    # ------------------------------------------------------------------
    # Tier 1 — Consumer API
    # ------------------------------------------------------------------
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
    # ------------------------------------------------------------------
    # Tier 2 — Extension API
    # ------------------------------------------------------------------
    "AbstractPhysicsEngine",
    "register_engine",
    "methodology_attested",
    "screening_boundary",
    "RuleFinding",
    "SiteAppropriatenessDetermination",
]
