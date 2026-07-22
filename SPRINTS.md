# Remediation Backlog — Sprints

Deferred items surfaced during GW-003 / GW-004 / GW-005 code review.

These are **adjudication-required backlog**, not implementation-ready work.
They are **not** open implementation defects (those are fixed in their
originating PRs).

This backlog distinguishes three classes of work that must not be conflated:

1. **Defects** — safe to fix immediately in a focused PR.
2. **Architectural / policy questions** — require explicit adjudication before
   implementation (this file).
3. **Project / process work** — repository hygiene, branch reconciliation,
   documentation ownership (also tracked here when deferred from review).

**Discipline:** adjudicate first; record the decision; implement only after
that decision is written down. Keep **defect correction**, **policy
adjudication**, and **branch reconciliation** in distinct changes.

## Status legend

| Status | Meaning |
|--------|---------|
| `ADJUDICATE` | Decision required before any implementation |
| `DECIDED` | Decision recorded; ready to scope/build |
| `SCOPED` | Acceptance criteria written; ready to implement |
| `DONE` | Implemented and verified |
| `BLOCKED` | Waiting on another item's adjudication |

## Adjudication rule of thumb

| If the change affects… | Then… |
|------------------------|-------|
| schema / contracts | **Adjudicate** (model shape + versioning) |
| validation semantics | **Adjudicate** (what is valid vs invalid) |
| compatibility / migration | **Adjudicate** (warn vs hard error; backfill) |
| severity / tiering policy | **Adjudicate** (warn vs block) |
| canonical branch / ownership | **Adjudicate** (process, not a feature PR) |
| tests that lock an already-decided rule | **Implement** after the decision is recorded |

## Required fields on every `ADJUDICATE` item

Each open adjudication entry must state its expected governance deliverable:

| Field | Purpose |
|-------|---------|
| **Decision required** | The single architectural / policy ruling to make |
| **Authority** | Who may record the decision (owner or review body) |
| **Blocks** | Sprint items or work streams held until decided |
| **Exit criterion** | What moves status from `ADJUDICATE` → `DECIDED` |

Without those four fields, an item is not ready for adjudication triage.

---

## Decision matrix (GW-003)

| ID | Title | Kind | Status | Depends on | Implementation only after |
|----|-------|------|--------|------------|---------------------------|
| GW-003-R1 | Superseded-predecessor lineage | **schema** + **validation** + **migration** | `ADJUDICATE` | — | Schema fields, enforcement rule, and migration severity are decided |
| GW-003-R2 | Residual multi-binding coverage (lineage case) | **implementation follow-up** | `BLOCKED` | R1 | R1 decision recorded; then add tests for unlinked superseded rows |
| GW-003-P1 | Legacy converter review default | **policy** + **migration** | `ADJUDICATE` | — | Default `review_status` and already-converted-case handling decided |
| GW-003-P2 | Order-stable evidence digest | **policy** + **compatibility** | `ADJUDICATE` | — | Whether digests canonicalize array order decided |
| GW-003-P3 | Important-tier conflict tiering | **policy** (severity) | `ADJUDICATE` | — | Important-tier conflict severity (warn vs block) decided |
| GW-003-X1 | Canonical-line reconciliation | **process** | `ADJUDICATE` | — | Canonical branch line and retirement of divergent history decided |

R2 coverage that does **not** depend on R1 is already `DONE` (see below).

---

## OSSF-GW-003 — Evidence & assumption layer

### GW-003-R1 · Superseded-predecessor semantics — `ADJUDICATE`

**Kind:** schema · validation semantics · migration  
**Origin:** review of PR #27, risk item 3.

**Observation:** the accepted-replacement rule in
`_critical_multi_binding_issues` (`core/contracts/evidence_validation.py`)
permits *one accepted + zero-or-more superseded* bindings of the same effective
provenance for a critical field. It only verifies **coexistence** — it does not
verify that the `superseded` rows are historical **predecessors** of the
accepted row. Semantically unrelated superseded rows for the same
field/provenance therefore pass.

**Why adjudication (not a defect fix):** the data model has no supersession
link. `EvidenceRecord` and `FieldEvidenceBinding` carry no `supersedes` /
`superseded_by` pointer, so lineage cannot be enforced without a
schema/contract change — a governed-shape decision.

| Governance field | Content |
|------------------|---------|
| **Decision required** | One architectural ruling covering: (1) schema home for lineage (`supersedes` on `EvidenceRecord` vs `superseded_by` on binding, including 1.1.x versioning); (2) how accepted-replacement enforcement walks the chain; (3) migration severity for unlinked superseded rows (hard `conflicting_bindings` vs temporary warning). |
| **Authority** | Architecture review (project maintainers); schema change requires contract owners. |
| **Blocks** | GW-003-R2 (lineage slice); any sprint that would harden superseded-coexistence into lineage checks. |
| **Exit criterion** | Written decision recorded in this file (or linked ADR) stating the chosen schema field(s), enforcement rule, and migration severity → status becomes `DECIDED`. |

**Draft acceptance (after `DECIDED` → `SCOPED`):** a case with an accepted
binding plus an *unrelated* superseded binding (no supersession link) is
rejected or warned deterministically, with a field-pathed error; linked history
still passes.

---

### GW-003-R2 · Residual multi-binding test coverage — `DONE` (non-lineage) / `BLOCKED` (lineage)

**Kind:** implementation follow-up (blocked on R1 for the open slice)  
**Origin:** review of PR #27 / #28 risk item 5.

**Closed without further adjudication** (locked by provenance-authority
consistency follow-up / PR #28):
- two-accepted → `duplicate_bindings`
- effective-provenance conflict (local match, linked differ) →
  `conflicting_bindings` (helper + readiness RDY-004)
- mixed citation + `evidence_id` same effective → `duplicate_bindings`
- mixed citation + `evidence_id` differing effective → `conflicting_bindings`
- unresolved `evidence_id` in multi-binding → `unknown_evidence`
- effective conflict precedes `pending_review` classification
- multiple superseded rows + one accepted (same effective provenance) →
  currently **proceeds** (documents pre-R1 coexistence policy)

**Lineage slice (blocked):**

| Governance field | Content |
|------------------|---------|
| **Decision required** | None independent of R1 — inherits R1's ruling on unlinked superseded rows. |
| **Authority** | Same as GW-003-R1. |
| **Blocks** | Lineage-dependent tests / implementation that would assert hard-fail (or warn) for unlinked superseded coexistence. |
| **Exit criterion** | GW-003-R1 reaches `DECIDED`; then this slice moves to `SCOPED` with tests matching the recorded severity. |

Do not implement lineage test expectations until R1 records the intended model.

---

## Carried-over governed-behavior decisions — `ADJUDICATE`

Related policy items previously flagged and intentionally not implemented as
defect fixes. Grouped here so the evidence-layer policy backlog is in one place.

### GW-003-P1 · Legacy converter review default — `ADJUDICATE`

**Kind:** policy · migration

`convert_legacy_site_config_to_v1` stamps generated evidence/bindings as
`review_status: "accepted"`, which makes legacy-converted inputs appear
practitioner-reviewed.

| Governance field | Content |
|------------------|---------|
| **Decision required** | One policy ruling: default `review_status` for converter-generated evidence/bindings (`accepted` vs `pending_review`), plus migration handling for already-converted cases if the default changes. |
| **Authority** | Architecture / product governance (evidence review-gate owners). |
| **Blocks** | Any change to `convert_legacy_site_config_to_v1` review defaults; readiness/evidence behavior for legacy imports that assumes the current stamp. |
| **Exit criterion** | Written decision stating the chosen default and migration rule → status becomes `DECIDED`. |

### GW-003-P2 · Order-stable evidence digest — `ADJUDICATE`

**Kind:** policy · compatibility

`compute_evidence_digest` hashes `evidence[]` / `field_bindings[]` in document
order, so reordering semantically-identical arrays changes the digest and
invalidates authorizations/attestations.

| Governance field | Content |
|------------------|---------|
| **Decision required** | One compatibility ruling: keep document-order digests, or canonicalize (e.g. sort by `(field_path, evidence_id)` / `evidence_id`) knowing that existing digest identity and stored fixtures will change. |
| **Authority** | Architecture review (authorization / attestation owners). |
| **Blocks** | Digest-canonicalization PRs; any fixture rewrite that assumes order-insensitive digests. |
| **Exit criterion** | Written decision stating order policy and whether a digest-breaking migration is authorized → status becomes `DECIDED`. |

### GW-003-P3 · Important-tier conflict tiering — `ADJUDICATE`

**Kind:** policy (severity / tiering)

Conflicting-provenance bindings on an *Important* field are promoted to a hard
`EvidenceContradictionError`, which contradicts the "important → warn" tier
model.

| Governance field | Content |
|------------------|---------|
| **Decision required** | One severity ruling: Important-tier provenance conflicts **warn** or **block**. |
| **Authority** | Architecture review (evidence-gate / tiering policy owners). |
| **Blocks** | Changes that soften or harden Important-tier conflict handling; tests that lock either severity as intended behavior. |
| **Exit criterion** | Written decision stating warn vs block for Important-tier conflicts → status becomes `DECIDED`. |

---

## Cross-cutting — `ADJUDICATE`

### GW-003-X1 · Canonical-line reconciliation — `ADJUDICATE`

**Kind:** process (branch / ownership), not a product or architectural requirement

The divergent local `feat/ossf-gw-003-evidence-layer` branch (no
`evidence_validation.py`) vs. the merged `main` line needs a canonical-line
decision. Tracked separately from any feature/fix PR.

| Governance field | Content |
|------------------|---------|
| **Decision required** | One process ruling: which line is canonical (`main` vs divergent feature branch), and how divergent local history is retired (archive, delete, or one-time reconcile with no further commits). |
| **Authority** | Repository maintainers / branch owners. |
| **Blocks** | Further commits on the divergent line; any “reconcile into main” PR that assumes ownership without a recorded decision. |
| **Exit criterion** | Written decision naming the canonical line and retirement action → status becomes `DECIDED` (then execute as process work, not a feature sprint). |

---

## Decision matrix (GW-005)

| ID | Title | Kind | Status | Depends on | Implementation only after |
|----|-------|------|--------|------------|---------------------------|
| GW-005-D1 | `_repo_relative` basename collapse | **implementation follow-up** | `DONE` | — | (defect) distinct output paths must not collapse to one recorded `relative_path` |
| GW-005-P1 | Recorded artifact-path traversal acceptance | **validation semantics** · compat | `ADJUDICATE` | — | Whether recorded artifact paths reject `..` traversal is decided |
| GW-005-P2 | History timestamp format / ordering | **validation semantics** · compat | `ADJUDICATE` | — | Whether history timestamps must be ISO-8601 + monotonic is decided |

All three are **non-blocking** for PR #30 / the GW-005 history feature: none
changes the pass/fail of a governed run, and none is reachable as a wrong-action
through any consumer shipped in the patch. They were surfaced by the PR #31
review (four-pass protocol, Pass 4) and deferred here rather than widening the
defect fix.

**Read these as review observations, not settled facts.** Each entry states
(a) **observed behavior** — a point-in-time code observation, verified against
`main` @ `b463fb7` on 2026-07-22; re-verify if the cited code moves — and
(b) an **adjudication-required decision** (or, for `SCOPED`, an acceptance
criterion). The `Observation` text is *not* a validated conclusion, and the
`Decision required` is *not* yet decided. **"Non-blocking" is conditional, not
permanent:** each entry carries a **Re-trigger** line naming the exact condition
under which it stops being non-blocking. If any of the cited code changes and
this file is not updated with it, the entry is stale — treat a mismatch between
these observations and current code as a bug in this backlog, not in the code.

---

## OSSF-GW-005 — Governed case history & decision ledger

### GW-005-D1 · `_repo_relative` basename collapse — `DONE`

**Kind:** implementation follow-up (provenance quality)  
**Origin:** review of PR #30 / #31 (Pass 4 non-blocking).

**Observation:** `simulate._repo_relative(path)` returns `path.name` when the
output path is outside the repository root (the `relative_to` `ValueError`
fallback). Two distinct output locations (e.g. `--output /a/results.json` and
`--output /b/results.json`) therefore collapse to the same recorded
`ArtifactBinding.relative_path` (`results.json`), reducing provenance
resolvability for custom output directories. Not a run-blocker: `execution_id`
still separates entries by artifact `sha256`, and in-repo default output is
unaffected.

**Acceptance:** distinct on-disk output locations never collapse to an identical
recorded `relative_path` — either a distinguishable path is recorded for
out-of-repo outputs, or out-of-repo provenance is explicitly documented as
unsupported. Add a driver test with two different `--output` directories
asserting distinct recorded paths.

**Re-trigger (stops being non-blocking when):** any workflow relies on
`relative_path` to uniquely locate an artifact across runs that use custom
`--output` directories, or provenance tooling begins keying on the recorded
path. Until then this is provenance-quality only.

**Note:** implementable without an architectural ruling. Promote to `ADJUDICATE`
only if maintainers treat the recorded-path *format* as a versioned contract
surface.

| Closure field | Content |
|---------------|---------|
| **Status** | `DONE` |
| **Decision/implementation** | Producer-side `recorded_artifact_path()`: in-repo → repository-relative; out-of-repo → `external/<normalized components>` (POSIX, Windows drive, UNC). `history.history_artifact` unchanged (separate repo-relative helper). |
| **PR** | stacked on integrity prerequisite PR #33; D1 branch `cursor/ossf-gw-005-d1-artifact-paths-32e0` |
| **Commit** | `e39b15a` (utility), `cb17e88` (driver), `8efd811` (docs), `d9645e0` (SHA correction); review follow-up: Windows host external labeling + conflict-marker docs repair |
| **Representation** | `output/...` in-repo; `external/...`, `external/C/...`, `external/UNC/server/share/...` outside |
| **Focused tests** | `tests/test_history_artifact_paths.py`; `test_distinct_custom_output_dirs_produce_distinct_binding_paths`; `test_default_in_repo_output_remains_repository_relative`; `test_recorded_artifact_digests_match_on_disk`; `test_windows_host_external_label_avoids_drive_backslash_leak` |
| **Full-suite result** | 355 passed |
| **Schema impact** | none (`screening-case-history-1.0.0`) |
| **CLI impact** | none |
| **Deferred items unchanged** | GW-005-P1, GW-005-P2 remain `ADJUDICATE` |

---

### GW-005-P1 · Recorded artifact-path traversal acceptance — `ADJUDICATE`

**Kind:** validation semantics · compatibility  
**Origin:** review of PR #30 / #31 (Pass 4 non-blocking).

**Observation:** `ArtifactBinding.__post_init__` (`core/history/models.py`)
rejects absolute POSIX paths, Windows drive (`:\`), and UNC (`\\`) prefixes, but
accepts relative traversal such as `../foo.json` (and forward-slash drive forms
like `C:/x`). Verified against `main` @ `b463fb7`: the guard is
`path.startswith("/") or ":\\" in path or path.startswith("\\\\")`, and the only
reader of `relative_path` is `builder.py` collecting it into a decision's
`related_ids` (a recorded string — it opens no file). So there is **no
wrong-action today**; this is defense-in-depth for any future consumer that
resolves the path against a base directory.

| Governance field | Content |
|------------------|---------|
| **Decision required** | One validation ruling: should recorded `relative_path` reject `..` traversal segments (and forward-slash drive forms), given no shipped consumer dereferences it and external producers may legitimately record unusual relative paths. |
| **Authority** | Architecture review (history-contract owners). |
| **Blocks** | Any future consumer that resolves `relative_path` against a base directory; path-hardening PRs and tests that would lock the stricter rule. |
| **Re-trigger (stops being non-blocking when):** | any consumer resolves `relative_path` against a base directory to open/read/write a file (today the sole reader, `builder.py:466`, only records the string). At that point this becomes a security item, not defense-in-depth. |
| **Exit criterion** | Written decision stating whether traversal is rejected (and the exact rule) → status becomes `DECIDED`. |

---

### GW-005-P2 · History timestamp format & ordering validation — `ADJUDICATE`

**Kind:** validation semantics · compatibility  
**Origin:** review of PR #30 / #31 (Pass 4 non-blocking).

**Observation:** `created_utc`, `started_utc`, and `completed_utc`
(`core/history/models.py`) are validated only as non-empty strings. A malformed
timestamp, or a `completed_utc` earlier than `started_utc`, passes both model
and JSON-schema validation. `history_chain_digest` deliberately **excludes**
timestamps (`core/history/digest.py`), so this has **no identity or determinism
impact** — it is a data-quality / interoperability gap. The driver always writes
well-formed UTC ISO-8601, so shipped output is unaffected; the gap is for
externally-authored or hand-edited histories.

| Governance field | Content |
|------------------|---------|
| **Decision required** | One validation ruling: enforce ISO-8601 format and `started_utc <= completed_utc` monotonicity on history timestamps, or keep them free-form (accepting that chain identity is timestamp-independent by design). |
| **Authority** | Architecture review (history-contract owners). |
| **Blocks** | Interop guarantees for external history producers/consumers; tests that would lock timestamp validity. |
| **Re-trigger (stops being non-blocking when):** | any consumer parses or orders these timestamps (e.g. sorts revisions by time, computes durations, or displays them as trustworthy), or `history_chain_digest` is changed to include timestamps — at which point malformed/non-monotonic values gain semantic weight they lack today. |
| **Exit criterion** | Written decision stating the timestamp validation rule (format + ordering, or none) → status becomes `DECIDED`. |
