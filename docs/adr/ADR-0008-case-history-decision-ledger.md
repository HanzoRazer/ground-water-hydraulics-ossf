# ADR-0008: Case History and Decision Ledger

## Status

Accepted — ossf-case-history-1.0.0 (OSSF-GW-005)

## Context

Authorization (ADR-0003), evidence (ADR-0006), and practitioner readiness
(ADR-0007) produce deterministic digests that bind a screening run. Those
digests answer *what was bound for this execution*. They do not record how a
case evolved across refusal, re-authorization, and later authorized runs as
an append-only engineering chronology.

GW-005 adds a governed **CaseHistory** artifact so every authorizable
screening path (authorization refusal and authorized pass/fail) can be traced
through immutable revisions, decision summaries, and execution records —
without persistence, collaboration, UI, or user accounts.

## Decision

1. **New package `core/history/`** owns revision chronology, decision
   ledger entries, execution records, split digests, and chain validation.
   It does **not** own SiteCase, evidence, readiness, authorization, SAD, or
   physics.

2. **Schema identity.** `HISTORY_SCHEMA_VERSION =
   "ossf-case-history-1.0.0"`. Artifact path:
   `output/<site_id>_history.json`.

3. **Three peer collections (locked 4A).** `CaseHistory` carries
   `revisions`, `decisions`, and `executions`. Executions are not nested
   solely inside revisions; each `ExecutionRecord` references a
   `revision_id` explicitly.

4. **Separate enums (locked 5).** `HistoryEventType` records *what
   happened*; `DecisionCategory` records *why a judgment was made*
   (`evidence`, `assumption`, `readiness`, `authorization`, `execution`,
   `reporting`).

5. **Emission policy (locked 3B).** Emit CaseHistory on authorization
   refusal (`execution_count: 0`) and authorized pass/fail. Do **not** emit
   on contract/schema, evidence, or readiness failures.

6. **CLI append (locked 2C).** Default is a one-revision history. Optional
   `--prior-history PATH` validates the prior artifact and appends; the
   driver never auto-discovers or overwrites a prior file in place.

7. **Split digests (locked 6C).**
   - `history_chain_digest` — content-only (revision bindings, decision
     ids/categories/summaries, execution ids/paths); **no timestamps**
   - `history_artifact_digest` — `sha256_of_json_stable` of the full
     serialized instance (includes timestamps)
   Revision and decision ids are content-derived (16-hex).

8. **Compact result reference (locked 7).** Result JSON embeds only a
   `history` summary (`schema_version`, `chain_digest`, `artifact_digest`,
   `revision_count`, `latest_revision_id`, `execution_count`,
   `history_artifact`). Full chronology stays in the history artifact.

## Consequences

- Authorized and auth-refusal runs write `output/<site_id>_history.json`
  and stamp a compact `history` block on the result artifact.
- Reviewers can answer whether every governed screening execution is
  traceable through a deterministic, append-only decision history without
  changing scientific or regulatory behavior.
- Physics, SAD thresholds, evidence semantics, and readiness rules remain
  unchanged; history only records their digests and outcomes.

## Non-goals

Database storage, project management, UI, collaboration, user accounts,
auto-discovery of prior history, and opening a PR without explicit owner
authorization (locked decision 8).
