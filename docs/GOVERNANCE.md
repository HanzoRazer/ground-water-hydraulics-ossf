# Governance

This document describes the governance principles for the Groundwater Screening
Toolkit codebase — how versions are managed, how ADRs are used, and what
commitments the project makes to consumers.

## Versioning

The project uses a `screening-<MAJOR>.<MINOR>.<PATCH>` version string stored
in `core.governance.METHODOLOGY_VERSION`.

| Bump | Trigger |
|------|---------|
| MAJOR | Any removal of a Tier 1 or Tier 2 symbol from `core.__init__`; any change to the methodology that alters screening outcomes |
| MINOR | Addition of new Tier 1/Tier 2 symbols; removal of Tier 3 symbols from `core.__init__`; API-compatible enhancements |
| PATCH | Bug fixes, documentation corrections, test additions with no API surface change |

## Architectural Decision Records

ADRs are stored in `docs/adr/`.  Each ADR is a Markdown file with the
conventional sections: Status, Context, Decision, Consequences, References.

Subsequent additions to `core/__init__.__all__` require a new ADR entry or an
amendment to ADR-0007.  Removal of any Tier 1 or Tier 2 symbol requires a
MAJOR bump and an ADR.

## Public API Contract

See `docs/OUTPUT_CONTRACT.md` for the output-schema versioning contract.
See `docs/adr/ADR-0007-public-api-surface.md` for the three-tier API model.

## Methodology Attestation

Functions that constitute a methodology boundary must be decorated with
`@methodology_attested` (from `core.governance`).  This allows automated
tooling to enumerate the attested entry points and verify that the
`__methodology_version__` attribute matches `METHODOLOGY_VERSION`.
