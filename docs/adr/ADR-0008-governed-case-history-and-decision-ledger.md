# ADR-0008: Governed Case History and Decision Ledger

## Status

Accepted — screening-case-history-1.0.0 (OSSF-GW-005)

## Context

GW-003 binds load-bearing inputs to evidence digests. GW-004 produces a
practitioner readiness digest that authorization and attestation bind.
Neither stage preserves an append-only chronology of how a screening case
evolved across invocations: revisions, governed decisions, execution
outcomes, and artifact lineage.

Engineering review and audit need a deterministic, file-based Case History
that records those outcomes without introducing persistence, mutable state,
or a second authorization path.

## Decision

1. **New package `core/history/`** owns immutable CaseHistory contracts,
   digests, serialization, validation, and builders. It is observational
   only: it records governed actions and never authorizes, validates, or
   interprets engineering data.

2. **Schema identity.** `HISTORY_SCHEMA_VERSION =
   "screening-case-history-1.0.0"`. JSON Schema lives at
   `schemas/case_history.schema.json` using the repository's existing
   GitHub `$id` convention.

3. **Append-only file model.** History is emitted as
   `output/<site_id>_history.json`. Existing revisions never change.
   Optional `--prior-history` appends exactly one new revision per
   emitting invocation.

4. **Revision-per-invocation.** Every history-emitting run appends one
   `CaseRevision`. Multiple `DecisionRecord`s per revision are allowed.
   At most one `ExecutionRecord` per revision in v1.

5. **Emission gates.**
   - Readiness `not_ready` → revision + readiness decision; no execution.
   - Authorization denied → revision + authorization decision; no execution.
   - Authorized `proceed` / `warn` → revision + authorization + execution
     (+ reporting decision if a text report was written).
   - Evidence-validation / parse failures do **not** emit history
     (GW-003 evidence-failure artifact remains authoritative).

6. **Digest distinction.**
   - `history_chain_digest` hashes governed semantic content only
     (excludes timestamps, absolute paths, and the artifact digest).
   - `history_artifact_digest` hashes the serialized file payload
     excluding only itself (includes timestamps and relative paths).
   - History determinism is conditional on the determinism of upstream
     digests. GW-005 does not redefine GW-003 digest semantics
     (GW-003-P2 remains separately adjudicated).

7. **Result contract reference.** Success, refusal, and readiness-failure
   artifacts embed a compact `history` summary (digests, counts, relative
   path). They never embed the full chronology.

8. **Identity.** `history_id`, `revision_id`, `decision_id`, and
   `execution_id` are lowercase 16-hex digests via
   `sha256_of_json_stable`, with fixed-shape payloads using explicit JSON
   `null` for nullable fields.

9. **Immutable artifact-byte bindings.** `ExecutionRecord.generated_artifacts`
   records SHA-256 digests only for final on-disk bytes that are not rewritten
   after binding. The result JSON is intentionally excluded because it embeds
   the history summary (digest cycle); result identity uses semantic
   `result_digest` instead. History always emits to
   `output/<site_id>_history.json` under the driver default directory, even
   when `--output` / `--text` redirect other artifacts.

## Consequences

- `simulate.py` gains `--prior-history` and always writes the history
  artifact for emitting gates.
- Prior-history identity/chain failures exit `1` with no new artifacts.
- Future case-evolution features can append revisions without a database.
- Custom `--output` / `--text` may place result/report beside a different
  directory than the history file; `history.history_artifact` names the
  default history path.

## Non-goals

Databases, mutable storage, cloud sync, collaboration, VCS integration,
workflow editing, UI, history visualization, evidence-failure events,
cross-version history migration, rollback policy, cross-file atomic
multi-artifact commits, co-locating history with custom `--output` paths
(no history-output CLI in v1).
