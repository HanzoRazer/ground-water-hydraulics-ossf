# Remediation Backlog — Sprints

Deferred items surfaced during GW-003 / GW-004 code review.

These are **adjudication-required backlog**, not implementation-ready work.
They are **not** open implementation defects (those are fixed in their
originating PRs). Each item changes one or more of:

- schema / contracts
- validation semantics
- compatibility / migration behavior
- severity / tiering policy
- canonical branch / reconciliation policy

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

---

## Decision matrix (GW-003)

| ID | Title | Kind | Status | Depends on | Implementation only after |
|----|-------|------|--------|------------|---------------------------|
| GW-003-R1 | Superseded-predecessor lineage | **schema** + **validation** + **migration** | `ADJUDICATE` | — | Schema fields (`supersedes` / `superseded_by`), enforcement rule, and migration severity (warn vs hard error) are decided |
| GW-003-R2 | Residual multi-binding coverage (lineage case) | **implementation follow-up** | `BLOCKED` | R1 | R1 decision recorded; then add tests for unlinked superseded rows |
| GW-003-P1 | Legacy converter review default | **policy** + **migration** | `ADJUDICATE` | — | Default `review_status` for converted evidence and handling of already-converted cases |
| GW-003-P2 | Order-stable evidence digest | **policy** + **compatibility** | `ADJUDICATE` | — | Whether digests canonicalize array order (breaks existing digest identity) |
| GW-003-P3 | Important-tier conflict tiering | **policy** (severity) | `ADJUDICATE` | — | Whether Important-tier provenance conflicts warn or block |
| GW-003-X1 | Canonical-line reconciliation | **process** | `ADJUDICATE` | — | Which branch line is canonical and how divergent local history is retired |

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

**Decisions required before coding:**
1. Add `supersedes: Optional[str]` (evidence_id) on `EvidenceRecord`, or
   `superseded_by` on the binding? (schema + versioning into 1.1.x)
2. How is lineage enforced in the accepted-replacement branch?
3. Are unlinked superseded rows a hard `conflicting_bindings` error, or a
   warning during a migration window?

**Draft acceptance (after decision):** a case with an accepted binding plus an
*unrelated* superseded binding (no supersession link) is rejected or warned
deterministically, with a field-pathed error; linked history still passes.

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

**Still open (depends on GW-003-R1):** whether multiple superseded rows that
are *not* lineage-linked to the accepted replacement should hard-fail. Do not
implement that test expectation until R1 records the intended severity.

---

## Carried-over governed-behavior decisions — `ADJUDICATE`

Related policy items previously flagged and intentionally not implemented as
defect fixes. Grouped here so the evidence-layer policy backlog is in one place.

### GW-003-P1 · Legacy converter review default — `ADJUDICATE`

**Kind:** policy · migration

`convert_legacy_site_config_to_v1` stamps generated evidence/bindings as
`review_status: "accepted"`, which makes legacy-converted inputs appear
practitioner-reviewed.

**Decisions required:** should the default be `pending_review` (forcing a human
gate)? If so, what is the migration handling for already-converted cases?

### GW-003-P2 · Order-stable evidence digest — `ADJUDICATE`

**Kind:** policy · compatibility

`compute_evidence_digest` hashes `evidence[]` / `field_bindings[]` in document
order, so reordering semantically-identical arrays changes the digest and
invalidates authorizations/attestations.

**Decisions required:** canonicalize (sort by `(field_path, evidence_id)` /
`evidence_id`) before hashing? Note this changes existing digest values and any
stored fixtures.

### GW-003-P3 · Important-tier conflict tiering — `ADJUDICATE`

**Kind:** policy (severity / tiering)

Conflicting-provenance bindings on an *Important* field are promoted to a hard
`EvidenceContradictionError`, which contradicts the "important → warn" tier
model.

**Decisions required:** should Important-tier conflicts warn instead of block?

---

## Cross-cutting — `ADJUDICATE`

### GW-003-X1 · Canonical-line reconciliation — `ADJUDICATE`

**Kind:** process (branch / ownership), not a feature task

The divergent local `feat/ossf-gw-003-evidence-layer` branch (no
`evidence_validation.py`) vs. the merged `main` line needs a canonical-line
decision. Tracked separately from any feature/fix PR.
