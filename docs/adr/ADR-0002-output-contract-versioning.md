# ADR-0002: Output Contract Versioning

**Status:** Accepted — screening-3.0.0

## Context

The toolkit produces structured JSON output consumed by external reviewers and
downstream scripts.  Without explicit versioning of the output schema, any
field addition or rename creates silent incompatibility.

## Decision

Introduce `OUTPUT_CONTRACT_VERSION` in `core.governance` following
`output-<MAJOR>.<MINOR>.<PATCH>` semantics.  The version is stamped into
results via `meta.output_contract_version`.  Field removals or renames at the
top two levels are MAJOR bumps; additions are MINOR bumps.

## Consequences

Downstream consumers can check `OUTPUT_CONTRACT_VERSION` before parsing
results and fail fast on unexpected MAJOR bumps.

## References

- `docs/OUTPUT_CONTRACT.md`
- `core/governance.py`
