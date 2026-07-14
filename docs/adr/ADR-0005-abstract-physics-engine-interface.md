# ADR-0005 — Abstract Physics Engine Interface

**Status:** Accepted — screening-2.0.0
**Date:** 2025

---

## Context

In the screening-1.x design, `get_engine(name)` returned an `EngineRecord`
dataclass that included a callable `evaluate` field.  This design created a
**footgun**: any caller who received an `EngineRecord` from `get_engine()`
could call `.evaluate(**kwargs)` directly, bypassing the authorization gate
entirely.  Authorization was enforced by convention — callers were expected
to call `ensure_execution_permitted(authorization)` first — but convention
is not enforcement.

Two redesign paths were considered:

### Path A — View-only record

Keep `get_engine()` returning a dataclass but strip the `evaluate` field.
The caller would separately look up and call the engine.  This removes the
footgun from the record but does not prevent a determined caller from
reaching the engine instance through other means (e.g. `ENGINES[name]`).

### Path B — Abstract interface (chosen)

Replace `EngineRecord` with an abstract base class (`AbstractPhysicsEngine`)
whose execution method (`run`) is **final** and always calls
`ensure_execution_permitted` before dispatching to the subclass's physics
hook (`_evaluate_impl`).  `get_engine()` returns `EngineMetadata` — a
frozen, view-only dataclass with no callable fields.  Execution goes
exclusively through `run_authorized_engine(name, authorization, **kwargs)`.

## Decision

**Path B (abstract interface)** was chosen because it provides
**enforcement by construction, not by convention**:

1. A subclass that tries to override `run` triggers a `TypeError` at
   class-definition time via `__init_subclass__`.  No subclass can ever
   bypass the authorization gate.
2. `get_engine()` returns `EngineMetadata` — there is no `evaluate` field,
   no `_evaluate_impl` field, and the object is not callable.  It is
   *structurally impossible* to execute physics through the metadata object.
3. `run_authorized_engine` is the only sanctioned execution entry point.
   External code never sees the engine instance.

This pattern is consistent with the `@safety_critical` gate used elsewhere
in the repo family and with the C2 process-exclusive authority pattern —
safety-critical operations must be routed through a single, audited gate,
not through ad-hoc call paths.

### `@methodology_attested` placement

The decorator is **not applied to `_evaluate_impl`**.  It is folded into
`AbstractPhysicsEngine.run()` — which unconditionally calls
`ensure_execution_permitted` before dispatch.  This means:

- Subclass authors do not need to remember to decorate `_evaluate_impl`.
- The attestation is always present; forgetting a decorator cannot weaken it.
- The `@methodology_attested` decorator is retained as a documentation
  marker for functions that are explicitly methodology-reviewed, but it
  adds no runtime authorization checks.

## Consequences

### Positive

- New engines inherit the authorization guard automatically by subclassing
  `AbstractPhysicsEngine`.  There is no additional code to write.
- `get_engine()` is safe to expose to any caller; it cannot return anything
  that can execute physics.
- Duplicate registration is caught at import time (`register_engine` raises
  `ValueError`).
- Non-ABC registration attempts are caught at registration time (raises
  `TypeError`).

### Negative

- Adding an engine now requires subclassing the ABC and implementing four
  abstract properties plus `_evaluate_impl`, rather than defining a
  standalone function.  This is a slightly higher barrier to entry.
- Existing code that called `engine.evaluate(**kwargs)` directly must
  migrate to `run_authorized_engine(name, authorization, **kwargs)`.

### Neutral

- `EngineRecord` is removed.  Any external consumer that imported
  `EngineRecord` must update.  The `EngineMetadata` replacement has the
  same informational content minus the callable `evaluate` field.
- `METHODOLOGY_VERSION` is bumped to `screening-2.0.0` (MAJOR) because
  `get_engine()` return type changed.  The `authorization` derivation
  scheme is unchanged.

## References

- `core/governance.py`
- `core/physics_registry.py`
- `core/physics_ogata_banks.py`
- `docs/adr/ADR-0002-physics-engine-tier-structure.md`
- `docs/adr/ADR-0004-authorization-id-binds-disposition.md`
- `tests/test_governed_execution.py`
- Ogata, A. & Banks, R.B. (1961). USGS Professional Paper 411-A.
