# ADR-0003: Authorization Contract and Execution Boundary

## Status

Accepted — screening-authorization-1.0.0

Amends the *enforcement mechanism* of ADR-0001 (the refusal doctrine).
The doctrine itself is unchanged; only how it is enforced in code changes.

## Context

ADR-0001 established that a site the preflight refuses must never reach
the physics engine, and that this is a hard boundary with no override. The
original enforcement mechanism was the `@screening_boundary` decorator in
`core/governance.py`, which raised `ScreeningScopeError` unless the
preflight disposition was exactly `proceed`.

Two problems emerged as the tool matured:

1. **It contradicted the permitted `warn` disposition.** ADR-0001 permits
   screening to run on a `warn` site (with a caveat in the report). The
   decorator only allowed `proceed`, so a literal application of it would
   have wrongly blocked every `warn` site.

2. **It was a second, competing authority.** Scope was decided by the
   preflight (`preflight.py`) but *enforced* by an unrelated decorator that
   re-derived the decision from a duck-typed argument. Two places encoding
   the same rule is exactly the drift risk the governance model exists to
   prevent.

We also wanted the enforcement to be *positive* (a capability that must be
presented) rather than *negative* (a guard that must not be tripped), and
to bind execution to the exact site config that was screened — so a token
minted for one config cannot be replayed against another.

## Decision

Introduce an explicit **authorization contract** in
`core/authorization.py` and make the physics registry the **single
execution boundary**.

**The token.** `authorize_screening(site_config, determination)` turns a
*permitting* preflight determination into a frozen `ScreeningAuthorization`.
Permitting dispositions are `proceed` and `warn`. A `refuse` determination
is **not authorizable**: `authorize_screening` raises
`AuthorizationDeniedError` and no token exists. There is no override flag,
no `force` kwarg (ADR-0001 preserved).

The token binds the run to its inputs:

- `site_config_hash` — canonical-JSON SHA-256 of the config it was minted
  from (reuses `governance.sha256_of_json_stable`; one hash algorithm).
- `findings_digest` — SHA-256 of the canonical JSON of the ordered,
  normalized preflight findings.
- `authorization_id` — a deterministic digest of
  `site_config_hash + ruleset_version + findings_digest + schema_version`.
  Reproducible for identical inputs; it binds the other identifiers
  together and is **not** a substitute for them.

**The boundary.** `physics_registry.run_authorized_engine(engine_name,
site_config, authorization, engine_inputs)` is the only production path to
an engine. It (1) resolves the engine, (2) calls
`validate_authorization(authorization, site_config)` — checking schema
version, config-binding (recomputed hash), tamper-evidence (digest + id
recompute), and that the disposition permits execution — then (3)
dispatches. Any failure raises before the engine is reached.

**Defense in depth.** `get_engine` is documented and used for *metadata
inspection only*; it does not execute. The engine's own governed entry
point, `physics_ogata_banks.evaluate`, requires a permitting
`ScreeningAuthorization` and refuses to run tokenless
(`ensure_execution_permitted`), so even a direct call cannot bypass the
contract. The pure-math functions (`concentration_steady_state`,
`concentration_at_time`, `longitudinal_dispersivity_m`, `_U`) remain
ungoverned and directly callable for characterization tests.

**Removal of the competing authority.** The `@screening_boundary`
decorator and `ScreeningScopeError` are removed from
`core/governance.py`. Scope enforcement now has exactly one home.

**Attestation.** The methodology attestation is extended to record that a
run was authorized: `preflight_disposition`, `authorization_schema_version`,
`authorization_id`, `findings_digest`, `warning_count`, and
`refusal_count`. `build_attestation` refuses to stamp a successful run that
is not carrying permitting authorization metadata bound to the same config.

## Consequences

**Positive.** One authority for scope. `warn` sites run as intended.
Execution is bound to the exact config screened, so a token cannot be
replayed against a different site. Tampering with a token is detectable.
The output artifact now proves not just what ran but that it ran
authorized, and refusal artifacts record the denial explicitly.

**Negative.** Every engine invocation revalidates the authorization
(re-hashing a small config dict per constituent×receptor). The cost is
negligible and buys a boundary that is enforced on every call.

**Neutral.** Exit-code taxonomy is unchanged: `0` = authorized run
completed, `2` = refused. No new exit codes were introduced.

## References

- ADR-0001 — Screening Scope and Refusal Doctrine (the doctrine this ADR
  enforces).
- `core/authorization.py` — the contract.
- `core/physics_registry.py` — the execution boundary.
- `tests/test_authorization.py`, `tests/test_governed_execution.py`,
  `tests/test_end_to_end.py` — enforcement tests, including the
  engine-non-invocation proof for refused sites.
