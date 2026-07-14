# ADR-0006: RunSession and SessionScopedExecutor

**Status:** Accepted — screening-3.0.0

## Context

Screening runs had no lifecycle concept — there was no way to distinguish
an in-progress run from a completed one, or to prevent reuse of stale
state from a closed run.

## Decision

Introduce `RunSession` as a context-manager-aware class that tracks a single
screening run and removes itself from a module-level live-session registry
(`_LIVE_SESSIONS`) on expiry.  `SessionScopedExecutor` wraps a callable and
raises `SessionExpiredError` if the bound session has expired before the call.

`RunSession`, `SessionScopedExecutor`, and `SessionExpiredError` are Tier 1.
`_LIVE_SESSIONS` is Tier 3 (internal registry).

## Consequences

Consumers use `with RunSession(...) as s:` to scope a run.  After the block,
the session is expired and any `SessionScopedExecutor` bound to it will raise
on subsequent calls.  The live-session registry enables future auditing of
concurrent runs without coupling the audit logic to each call site.

## References

- `core/run_session.py`
