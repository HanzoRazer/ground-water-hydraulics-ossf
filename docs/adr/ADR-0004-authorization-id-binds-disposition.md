# ADR-0004 — Authorization ID Binds Disposition

**Status:** Accepted — authorization-2.0.0
**Date:** 2025

---

## Context

Early versions of the toolkit called physics functions directly without
any authorization model.  The risk was that a caller could inadvertently
(or maliciously) run an engine with unapproved parameters — for example,
reusing a prior "permitted" result with different inputs, or calling an
engine that has not yet been vetted for a particular use case.

Two authorization schemes were considered:

- **Path A — Capability token:** A short-lived cryptographic token that
  the caller presents to prove they have the right to run a specific
  engine.  Enforces expiry and replay prevention.
- **Path B — Disposition record:** A simple dataclass (`Authorization`)
  that couples a deterministically-derived `authorization_id` to a
  `disposition` string (`"permitted"` / `"denied"`).  The id is derived
  from engine name + parameter hash + caller nonce, so changing any input
  invalidates the prior id.

## Decision

**Path B (disposition record)** was chosen because:

1. It is lightweight and does not require a token-issuance service.
2. The id-derivation binding (engine + params + nonce → id) provides
   replay protection equivalent to Path A for the current threat model.
3. The `disposition` field is a plain string, easy to audit in logs.

The `Authorization` dataclass (in `core/governance.py`) is frozen and
immutable.  `ensure_execution_permitted` is the single enforcement gate.

## Consequences

- **Positive:** Simple, auditable, no external dependencies.
- **Positive:** Replay protection through deterministic id derivation.
- **Negative:** Does not provide cryptographic non-repudiation; if
  stronger guarantees are needed, Path A (capability token) should be
  revisited.
- **Neutral:** The derivation of `authorization_id` is the caller's
  responsibility; this toolkit validates the id is non-empty and the
  disposition is `"permitted"` but does not re-derive or verify the id.

## References

- `core/governance.py`
- `docs/adr/ADR-0005-abstract-physics-engine-interface.md`
