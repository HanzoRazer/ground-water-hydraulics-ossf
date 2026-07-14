"""
physics_registry.py
===================

Canonical authority for physics engines. Mirrors the ``process-exclusive
canonical authority`` pattern from the luthiers-toolbox C2 ruling: exactly
one place knows what physics engines exist, their versions, and their
scope-of-applicability.

Every engine registered here MUST:

  * be marked with ``@methodology_attested(engine_name, engine_version)``
  * expose an ``evaluate(**constituent_and_site_kwargs) -> result`` callable
  * have a documented sanity-limit test in tests/ that pins its correctness

Selection at run time is by string key from the site config
(``site.physics.engine``), or by explicit override in code. If the config
does not specify an engine, the default is ``ogata_banks_1d``.

Adding a new engine (e.g. ``domenico_3d``) is:

  1. Implement the module.
  2. Add an entry to ``ENGINES`` below.
  3. Write the sanity-limit test.
  4. Open an ADR under docs/adr documenting scope-of-applicability.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, NamedTuple

from . import physics_ogata_banks
from .authorization import ScreeningAuthorization, validate_authorization


class EngineRecord(NamedTuple):
    name: str
    version: str
    module: object
    evaluate: Callable
    description: str
    scope_notes: str


class AuthorizedEngineRun(NamedTuple):
    """Result of a governed engine invocation: the engine's own result plus
    the ``EngineRecord`` metadata (name/version/scope) for attestation."""
    result: Any
    engine: EngineRecord


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ENGINES: Dict[str, EngineRecord] = {
    "ogata_banks_1d": EngineRecord(
        name="ogata_banks_1d",
        version=physics_ogata_banks.ENGINE_VERSION,
        module=physics_ogata_banks,
        evaluate=physics_ogata_banks.evaluate,
        description=(
            "1D advection-dispersion transport with linear retardation "
            "and first-order decay. Continuous source, semi-infinite "
            "domain. Van Genuchten & Alves (1982) solution A1."
        ),
        scope_notes=(
            "Appropriate for on-axis receptors, homogeneous soils, "
            "steady flow. Not appropriate for off-axis receptors "
            "(no transverse dispersion), heterogeneous soils, or "
            "transient sources."
        ),
    ),
}

DEFAULT_ENGINE = "ogata_banks_1d"


def get_engine(name: str | None = None) -> EngineRecord:
    """Look up an engine record for METADATA INSPECTION ONLY.

    This returns the ``EngineRecord`` (name, version, scope notes, and the
    raw ``evaluate`` callable) so callers can report which engine would be
    used. It performs NO authorization check. Production execution must go
    through ``run_authorized_engine`` — do not call ``record.evaluate``
    directly to run a screening (ADR-0001)."""
    if name is None:
        name = DEFAULT_ENGINE
    if name not in ENGINES:
        available = ", ".join(sorted(ENGINES))
        raise KeyError(
            f"Unknown physics engine '{name}'. Available: {available}."
        )
    return ENGINES[name]


def list_engines() -> list[str]:
    return sorted(ENGINES)


def run_authorized_engine(
    engine_name: str | None,
    site_config: dict,
    authorization: ScreeningAuthorization,
    engine_inputs: dict,
) -> AuthorizedEngineRun:
    """The single governed choke point for running a physics engine.

    Every production engine invocation flows through here. In order:

      1. Resolve the engine (validates it is a registered engine).
      2. Validate the authorization against ``site_config``: schema version,
         config-binding (recomputed canonical-JSON hash), tamper detection
         (findings digest + id), and that the disposition permits execution.
         Any failure raises from ``core.authorization`` and the engine is
         never reached.
      3. Dispatch ``engine.evaluate(**engine_inputs, authorization=...)``.
      4. Return the result together with the engine metadata.

    There is no code path that runs the engine without a validated
    authorization; ``get_engine`` is metadata-only and ``evaluate`` itself
    refuses to run tokenless.
    """
    engine = get_engine(engine_name)
    # Boundary validation (defense in depth). The governed engine entry point
    # also validates config-binding with the same site_config, so a direct
    # call to the engine cannot bypass this check.
    validated = validate_authorization(authorization, site_config)
    result = engine.evaluate(
        **engine_inputs, authorization=validated, site_config=site_config
    )
    return AuthorizedEngineRun(result=result, engine=engine)
