# ADR-0007: Public API Surface — Three-Tier Model

**Status:** Accepted — screening-3.1.0

---

## Context

`core/__init__.py` is the implicit public API contract of the `core` package.
Prior to this ADR, `core/__init__.py` contained only a module docstring with
no explicit exports.  As the prerequisite infrastructure ADRs (ADR-0002
through ADR-0006) added new symbols to the codebase, there was no governing
rule about which symbols belonged in `core/__init__.py`.

**The implicit-contract problem with an un-curated `__init__.py`**

Every symbol that is importable from `core` — whether intentionally re-exported
or simply accessible due to Python's import mechanics — becomes something a
consumer may legitimately depend on.  Without an explicit `__all__` and a
written policy, the maintenance envelope grows unbounded: removing *any*
accessible symbol is a potential breaking change, even if it was never
intended to be public.

**The current risk**

Without this ADR:

- Tier 3 internals (hash helpers, private ID derivation, individual rule
  functions, physics primitives) are reachable via `from core import X` even
  though they are implementation details that may be refactored.
- Consumers have no documented guidance on which import path is stable and
  which is subject to change.
- There is no machine-readable contract — no `__all__` — that makes the
  boundary testable.

---

## Decision

This ADR adopts a three-tier model for the `core` package public surface:

### Tier 1 — Consumer API

For downstream users running the tool as a library.  Symbols are included in
`core/__init__.__all__`.  Removal of any Tier 1 symbol requires a **MAJOR**
bump of `METHODOLOGY_VERSION`.

### Tier 2 — Extension API

For developers writing new physics engines or preflight rules.  Symbols are
included in `core/__init__.__all__`.  Removal of any Tier 2 symbol requires a
**MAJOR** bump of `METHODOLOGY_VERSION`.

### Tier 3 — Internal

Reachable via `from core.<module> import X` but **not** re-exported from
`core.__init__`.  Not part of the public contract; may be refactored in any
MINOR bump.

### Subsequent additions

Any symbol added to `core.__init__.__all__` after this ADR requires either:
- An update to this ADR's symbol table (for straightforward Consumer/Extension
  additions), or
- A new ADR (for additions that change the scope or nature of the public
  surface).

### Version bump policy

- **MINOR** bump: adding Tier 1/2 symbols, or removing Tier 3 symbols from
  `core.__init__`.
- **MAJOR** bump: removing or renaming any Tier 1 or Tier 2 symbol.

---

## Authoritative Symbol Table

The following table is exhaustive as of `screening-3.1.0`.

| Symbol | Module | Tier | Justification |
|--------|--------|------|---------------|
| `RunSession` | `core.run_session` | Tier 1 | Primary consumer entry point for scoped runs |
| `SessionScopedExecutor` | `core.run_session` | Tier 1 | Session-bound callable wrapper; part of the session API |
| `SessionExpiredError` | `core.run_session` | Tier 1 | Exception consumers must catch when sessions expire |
| `build_authorization` | `core.authorization` | Tier 1 | Constructor consumers use to create authorization records |
| `AuthorizationError` | `core.authorization` | Tier 1 | Exception consumers must catch on bad authorization inputs |
| `EngineMetadata` | `core.physics_registry` | Tier 1 | Return type of `list_engines`; consumers inspect it |
| `get_engine` | `core.physics_registry` | Tier 1 | Engine lookup by name for consumers running specific engines |
| `list_engines` | `core.physics_registry` | Tier 1 | Engine discovery for consumers |
| `run_authorized_engine` | `core.engine_runner` | Tier 1 | Canonical entry point for running an authorized engine |
| `evaluate_site` | `core.preflight` | Tier 1 | Preflight entry point for consumers |
| `ScreeningScopeError` | `core.preflight` | Tier 1 | Exception consumers must catch when sites are out-of-scope |
| `METHODOLOGY_VERSION` | `core.governance` | Tier 1 | Version constant consumers use to stamp outputs |
| `PREFLIGHT_RULESET_VERSION` | `core.governance` | Tier 1 | Version constant for the active preflight rule set |
| `AUTHORIZATION_SCHEMA_VERSION` | `core.governance` | Tier 1 | Version constant for the authorization schema |
| `OUTPUT_CONTRACT_VERSION` | `core.governance` | Tier 1 | Version constant for the output contract schema |
| `AbstractPhysicsEngine` | `core.physics_registry` | Tier 2 | Base class for engine authors |
| `register_engine` | `core.physics_registry` | Tier 2 | Registration function for engine authors |
| `methodology_attested` | `core.governance` | Tier 2 | Decorator for engine authors to attest methodology compliance |
| `screening_boundary` | `core.governance` | Tier 2 | Decorator for rule authors to mark boundary functions |
| `RuleFinding` | `core.preflight` | Tier 2 | Return type for preflight rule authors |
| `SiteAppropriatenessDetermination` | `core.preflight` | Tier 2 | Return type for rule authors composing determinations |
| `sha256_of_file` | `core.governance` | Tier 3 | Private hash helper — engine implementation detail |
| `sha256_of_json_stable` | `core.governance` | Tier 3 | Private hash helper — engine implementation detail |
| `_derive_authorization_id` | `core.authorization` | Tier 3 | Private ID derivation — authorization implementation detail |
| `_LIVE_SESSIONS` | `core.run_session` | Tier 3 | Private session registry — internal session state |
| `rule_soil_class_in_database` | `core.preflight` | Tier 3 | Individual rule function — subject to change with ruleset |
| `rule_hydraulic_gradient_positive` | `core.preflight` | Tier 3 | Individual rule function — subject to change with ruleset |
| `rule_at_least_one_receptor` | `core.preflight` | Tier 3 | Individual rule function — subject to change with ruleset |
| `_U` | `core.transport` | Tier 3 | Physics primitive — ADE helper, engine implementation detail |
| `concentration_at_time` | `core.transport` | Tier 3 | Physics primitive — engine implementation detail |
| `concentration_steady_state` | `core.transport` | Tier 3 | Physics primitive — engine implementation detail |

### `__all__` as of screening-3.1.0

```python
__all__ = [
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
```

---

## Consequences

### Positive

- A clear, tested public contract.  `test_public_api_surface.py` locks
  `__all__` and verifies that Tier 3 symbols are NOT importable from `core`.
- Consumers have documented guidance: import from `core` for stable symbols,
  import from `core.<module>` only when intentionally depending on an
  internal detail.
- The maintenance envelope is explicit: only 20 symbols are committed to
  backward-compatibility.

### Negative

- Import verbosity for internal test files that currently reach into Tier 3
  symbols.  Those files must import from `core.<module>` rather than `core`.

### Neutral

- If Tier 2 grows substantially (e.g., a rich plugin ecosystem emerges),
  a future ADR may warrant splitting `core.extensions` into its own
  subpackage.  That is explicitly deferred here.

---

## Version Bump Justification

This is a **MINOR** bump (`screening-3.0.0` → `screening-3.1.0`) because:

- No previously-documented Tier 1 or Tier 2 promise is broken.
- The pre-ADR `core/__init__.py` exported nothing (empty); adding `__all__`
  and Tier 1/2 symbols is additive.
- Tier 3 symbols were never part of a published contract.

---

## References

- `core/__init__.py`
- `core/governance.py`
- `core/authorization.py`
- `core/physics_registry.py`
- `core/run_session.py`
- `core/preflight.py`
- `core/engine_runner.py`
- `core/transport.py`
- `tests/test_public_api_surface.py`
- `docs/GOVERNANCE.md`
- `docs/OUTPUT_CONTRACT.md`
- ADR-0002 through ADR-0006 (prerequisite infrastructure)
