# ADR-0004: Authorization Derivation

**Status:** Accepted — screening-3.0.0

## Context

Authorization records were ad-hoc dictionaries with no deterministic ID.  This
made it impossible to verify that two authorization objects referred to the
same run authorization without comparing every field.

## Decision

Introduce `_derive_authorization_id(site_id, methodology_version, issued_utc)`
in `core.authorization` which derives a 16-hex-character authorization ID as
a SHA-256 prefix of the canonical JSON of those three fields.  `build_authorization`
is the public constructor that validates inputs and calls the derivation.

The derivation function is Tier 3 (internal); `build_authorization` and
`AuthorizationError` are Tier 1.

## Consequences

Authorization IDs are deterministic and auditable.  Two calls with identical
inputs produce the same ID.  The derivation function is an internal
implementation detail and may be strengthened in a future MINOR bump.

## References

- `core/authorization.py`
