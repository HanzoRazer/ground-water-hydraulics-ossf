# ADR-0003: Artifact Schema Fields

**Status:** Accepted — screening-3.0.0

## Context

Output artifacts lacked explicit `schema_version` and `status` fields, making
it impossible to distinguish a completed run from an aborted or partial one
without inspecting the full result structure.

## Decision

Add `schema_version` (maps to `OUTPUT_CONTRACT_VERSION`) and `status`
(`"complete"` | `"partial"` | `"error"`) to the top-level `meta` block of
every output artifact.

## Consequences

Consumers can quickly triage artifacts by status field without deserialising
the full results tree.

## References

- `docs/OUTPUT_CONTRACT.md`
- `core/governance.py`
