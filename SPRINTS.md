# Remediation Backlog — Sprints

Deferred items surfaced during GW-003 / GW-004 code review.

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
