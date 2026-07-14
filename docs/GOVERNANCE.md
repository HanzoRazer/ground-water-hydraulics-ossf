# Governance Policy — Groundwater Screening Toolkit

## Purpose

This document describes the governance controls that prevent unattested,
unauthorized, or otherwise improper physics calculations from being executed
through this toolkit.  It is the normative reference for project maintainers
and reviewers.

## Versioned surfaces

The codebase maintains five independently-versioned governance surfaces.
Each versions along its own axis of change; a change to one surface does
not automatically require a bump in the others.

| Surface | Current version | Namespace prefix | Bump rule |
|---|---|---|---|
| Methodology (engine interface) | `screening-2.0.0` | `screening-` | MAJOR: breaking API change; MINOR: new engine or non-breaking interface; PATCH: doc/comment only |
| SAD preflight ruleset | `sad-1.0.0` | `sad-` | MAJOR: rule removed or semantics changed; MINOR: new rule added; PATCH: wording |
| Authorization derivation | `authorization-2.0.0` | `authorization-` | MAJOR: id derivation algorithm changed; MINOR: new scope field; PATCH: doc |
| Screening result contract | `screening-result-1.0.0` | `screening-result-` | MAJOR: field removed or renamed; MINOR: new optional field; PATCH: doc |
| Engine — Ogata-Banks 1D | `1.0.0` | (internal) | MAJOR: numerical output changes; MINOR: new parameter with default; PATCH: doc |

See `docs/OUTPUT_CONTRACT.md` for the output schema and `docs/adr/` for the
architectural decision records that govern each surface.

## Authorization model (ADR-0004)

Every engine execution must be authorized before any physics runs.  The
authorization model binds an `authorization_id` to a `disposition`:

- `authorization_id`: derived deterministically from the engine name, a
  hash of the call parameters, and a caller-supplied nonce.  Changing any
  input invalidates the id.
- `disposition`: must be the literal string `"permitted"` for execution to
  proceed.  Any other value causes `ensure_execution_permitted` to raise
  `AuthorizationError`.

The derivation of `authorization_id` is the responsibility of the caller
(or a future issuance service); this codebase validates the id is non-empty
and checks the disposition.  It does not re-derive or verify the id's content.

## Engine interface (ADR-0005)

All physics engines must:

1. Subclass `AbstractPhysicsEngine` (in `core/physics_registry.py`).
2. Implement the four abstract properties (`name`, `version`, `scope_notes`,
   `description`) and the `_evaluate_impl(**kwargs)` method.
3. Register a singleton instance via `register_engine(instance)`.

The `run(authorization, **kwargs)` method is **final** and not overridable.
It calls `ensure_execution_permitted` before dispatching to `_evaluate_impl`,
so the authorization gate is inherited automatically — no engine can run
without it.

External call sites must use `run_authorized_engine(name, authorization,
**kwargs)` exclusively.  Direct instantiation of engine classes or calls to
`_evaluate_impl` are prohibited in application code.

## Adding a new engine

1. Create a new module `core/physics_<name>.py`.
2. Define a class that inherits `AbstractPhysicsEngine` and implements all
   abstract members.
3. Create a module-level singleton and call `register_engine(singleton)`.
4. Write characterization tests in `tests/test_physics_<name>.py`.
5. Bump `ENGINE_VERSION` if updating an existing engine's physics.
6. If the registry API changes, bump `METHODOLOGY_VERSION` in
   `core/governance.py` per the table above.

## References

- `docs/adr/ADR-0002-physics-engine-tier-structure.md`
- `docs/adr/ADR-0004-authorization-id-binds-disposition.md`
- `docs/adr/ADR-0005-abstract-physics-engine-interface.md`
- `docs/OUTPUT_CONTRACT.md`
- `core/governance.py`
- `core/physics_registry.py`
