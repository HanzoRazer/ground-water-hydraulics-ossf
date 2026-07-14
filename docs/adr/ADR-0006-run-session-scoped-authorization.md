# ADR-0006: RunSession-scoped authorization validation

**Status:** Accepted — screening-3.0.0

**Date:** 2026-07-14

**Issue:** [OSSF-GW-001 follow-up: validate authorization once per run, not per engine call](https://github.com/HanzoRazer/ground-water-hydraulics-ossf/issues/6)

---

## Context

### The performance problem

The OSSF groundwater screening tool evaluates a site by running a physics
engine for every (receptor, constituent) pair. With 4 receptors and 5
constituents, that is 20 engine calls per run.

Prior to this ADR, the physics boundary called `validate_authorization()`
on every engine invocation. `validate_authorization` is expensive: it
recomputes the canonical-JSON SHA-256 of the site configuration to verify
that the authorization token was minted for exactly this config.

For a 4 × 5 run, this means 20 config-hash recomputations where 1 is
correct. The authorization doesn't change between calls; the site config
doesn't change between calls. Recomputing on every call buys nothing.

### The tension: performance vs. bypass surface

The naive fix — cache the "already validated" result as a mutable flag on
the `ScreeningAuthorization` object — satisfies the performance goal but
violates a security invariant established by prior ADRs.

A mutable "I've been validated" flag is a **trust flag**. In a
governance-hardened codebase, a trust flag is a bypass: any caller who can
set the flag on an authorization object they control can claim to have been
validated without going through `validate_authorization`. The flag becomes
a forgeable "permission bit."

This is exactly the pattern the authorization contract was designed to
prevent. An option that reopens the bypass is not an option.

### Three approaches considered

**Option 1: Cache by object identity.** Store a `_validated_flag` on the
`ScreeningAuthorization` after first validation. The per-call guard checks
the flag. Fast. But it reintroduces the trust-flag anti-pattern the prior
ADRs eliminated. Rejected.

**Option 2: Split into AuthorizationCertificate + ExecutionTicket.** The
heavy artifact carries the full config hash and findings digest (validated
once). The light artifact is derived by HMAC from the certificate, so
producing a valid ticket requires having validated the certificate. A direct
caller who tries to synthesize a ticket without a certificate can't produce
one that verifies. Cryptographically sound. More machinery than needed for
a single-process Python tool. Deferred.

**Option 3: Session-scoped validator (chosen).** A `RunSession` context
manager validates the authorization on entry, generates a fresh opaque
token, registers the token in a module-private set, and yields a
`SessionScopedExecutor` carrying the token. The per-call guard is an O(1)
set membership check. `RunSession.__exit__` removes the token
unconditionally, expiring all executors. No flag; no cache; no trust.

### Why Option 3

- **Python-native.** Context managers are the idiomatic Python scope
  construct for "this block has been validated." No new concepts needed.
- **Composable.** The `RunSession` wraps the existing receptor × constituent
  loop in `simulate.py` with a single `with` statement.
- **Matches the C2 canonical-authority pattern.** "Exactly one place has
  authority; you get it by going through the door, not by claiming you did."
  The door is `RunSession.__enter__`.
- **Bypass surface unchanged.** A caller with a valid
  `ScreeningAuthorization` but no live `RunSession` cannot execute an
  engine. The engine's `run()` method accepts only a
  `SessionScopedExecutor`. Passing a raw authorization raises `TypeError`
  (type annotation) and a runtime `isinstance` guard. Fabricating a
  `SessionScopedExecutor` with a random token raises `SessionExpiredError`
  because the token is not in `_LIVE_SESSIONS`.
- **Single-validation property is testable.** A test can monkeypatch
  `validate_authorization`, run a full N × M loop, and assert the call
  count is exactly 1. This test fails on the pre-fix codebase and passes
  after.

---

## Decision

Introduce three new types in `core/run_session.py`:

### `RunSession` (context manager)

- Constructor takes `(authorization, site_config, soils_db, constituents_db)`.
- `__enter__` calls `validate_authorization(authorization, site_config)`
  exactly once. On success, generates `secrets.token_bytes(32)`, registers
  it in `_LIVE_SESSIONS: set[bytes]` (module-private), and yields a
  `SessionScopedExecutor`.
- `__exit__` calls `_LIVE_SESSIONS.discard(token)` unconditionally (even
  on exception).
- **Not re-entrant:** entering twice raises `SessionAlreadyActiveError`.
- **Not reusable:** re-entering after exit raises `SessionNotReusableError`.

### `SessionScopedExecutor` (frozen dataclass)

- Fields: `_token: bytes`, `_authorization: ScreeningAuthorization`
  (both private by convention).
- `authorize_call() -> None`: raises `SessionExpiredError` if
  `_token not in _LIVE_SESSIONS`. This is the O(1) per-call guard.
- Read-only properties: `authorization_id`, `disposition`,
  `site_config_hash` (for logging/attestation; no callable fields, no way
  to extract the token).

### `SessionExpiredError` / `SessionAlreadyActiveError` / `SessionNotReusableError`

Specific exceptions for session lifecycle violations.

### `AbstractPhysicsEngine.run()` signature narrowed

From: `run(authorization: ScreeningAuthorization, **kwargs)`
To:   `run(executor: SessionScopedExecutor, **kwargs)`

Body:
```python
def run(self, executor, **kwargs):
    if not isinstance(executor, SessionScopedExecutor):
        raise TypeError(...)
    executor.authorize_call()   # O(1), no rehash
    return self._evaluate_impl(**kwargs)
```

### `run_authorized_engine()` signature narrowed

From: `run_authorized_engine(name, site_config, authorization, engine_inputs)`
To:   `run_authorized_engine(name, executor, **engine_inputs)`

Passing a raw `ScreeningAuthorization` raises `TypeError`.

### `simulate.py` refactored

The receptor × constituent loop is wrapped in a `RunSession`:

```python
with RunSession(authorization, site_cfg, soils, constituents) as executor:
    for receptor in receptors:
        for constituent in constituents:
            run_authorized_engine(engine_name, executor, **kwargs)
```

---

## Consequences

### Positive

- **O(receptors × constituents) → O(1) full validations per run.**
  At 4 receptors × 5 constituents, from 20 to 1 (95% fewer config-hash
  recomputations).

- **Bypass surface unchanged.** `engine.run(authorization, ...)` outside a
  session raises `TypeError`. Fabricating an executor with a random token
  raises `SessionExpiredError`. There is no new trust flag.

- **Testable invariant.** `test_session_validates_once` (in
  `tests/test_run_session.py` and `tests/bench_authorization.py`) asserts
  the call count is exactly 1 for a full run. This test fails on the
  pre-fix codebase, providing falsification evidence.

### Negative

- **Engine consumers must wrap calls in a `with RunSession(...)` block.**
  This is slightly more verbose than the previous direct call style. The
  verbosity is the point: it makes the governance scope explicit.

- **`run()` and `run_authorized_engine()` signatures changed.** Any
  consumer that passed a raw `ScreeningAuthorization` must update. This is
  a breaking change (hence the MAJOR version bump to `screening-3.0.0`).

### Neutral

- **Single-process design.** `_LIVE_SESSIONS` is a module-level in-process
  set. This is correct for the single-process CLI use case. Multi-process
  session sharing (e.g., via `multiprocessing.Pool`) is not supported:
  each worker process has its own `_LIVE_SESSIONS`, so an executor from
  one process is always expired in another. Do not share `SessionScopedExecutor`
  instances across process boundaries.

- **Thread safety.** Multiple threads can each hold a live session
  simultaneously. `_LIVE_SESSIONS.add` and `_LIVE_SESSIONS.discard` are
  atomic for CPython's GIL. No additional locking is needed for the
  single-consumer-per-session use case.

---

## References

- [Issue #6 — validate authorization once per run](https://github.com/HanzoRazer/ground-water-hydraulics-ossf/issues/6)
- `core/run_session.py` — implementation
- `core/physics_engine_base.py` — `AbstractPhysicsEngine.run()` narrowed signature
- `core/physics_registry.py` — `run_authorized_engine()` narrowed signature
- `tests/test_run_session.py` — all session-scope enforcement tests
- `tests/bench_authorization.py` — one-validation-per-run assertion
