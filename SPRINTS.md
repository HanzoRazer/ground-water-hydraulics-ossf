# Remediation Backlog — Sprints

Deferred items surfaced during code review. These are **not** implementation
defects (those are fixed in their originating PRs); they are governed-behavior
or design decisions that require separate adjudication before implementation,
per the standing discipline of keeping **defect correction**, **policy
decisions**, and **branch reconciliation** in distinct changes.

Status legend: `OPEN` (needs adjudication) · `SCOPED` (decision made, ready to
build) · `DONE`.

---

## OSSF-GW-003 — Evidence & assumption layer

### GW-003-R1 · Superseded-predecessor semantics — `OPEN` (policy + model change)

**Origin:** review of PR #27 (`fix(evidence): allow superseded critical
bindings with accepted replacement`), risk item 3.

**Observation:** the accepted-replacement rule in
`_critical_multi_binding_issues` (`core/contracts/evidence_validation.py`)
permits *one accepted + zero-or-more superseded* bindings of the same effective
provenance for a critical field. It only verifies **coexistence** — it does not
verify that the `superseded` rows are the historical **predecessors** of the
accepted row. Semantically unrelated superseded rows for the same
field/provenance therefore pass.

**Why deferred:** the data model has no supersession link. `EvidenceRecord` and
`FieldEvidenceBinding` carry no `supersedes` / `superseded_by` pointer, so
lineage cannot be enforced without a schema/contract change — a governed-shape
decision, not a defect fix.

**Proposed remediation (for adjudication):**
- Add an explicit `supersedes: Optional[str]` (evidence_id) to `EvidenceRecord`
  (or `superseded_by` on the binding), versioned into the 1.1.x schema.
- Enforce in the accepted-replacement branch that each superseded row is
  reachable from the accepted row's supersession chain.
- Decide whether unlinked superseded rows become a hard `conflicting_bindings`
  error or a warning during a migration window.

**Acceptance:** a case with an accepted binding plus an *unrelated* superseded
binding (no supersession link) is rejected (or warned) deterministically, with
a field-pathed error; linked history still passes.

---

### GW-003-R2 · Residual multi-binding test coverage — `DONE` (partial) / `OPEN` (lineage)

**Origin:** review of PR #27 / #28 risk item 5.

**Closed by the provenance-authority consistency follow-up:**
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
are *not* lineage-linked to the accepted replacement should hard-fail.

---

## Carried-over governed-behavior decisions (from PR #24 review) — `OPEN`

Related policy items previously flagged and intentionally not implemented as
defect fixes. Grouped here so the evidence-layer policy backlog is in one place.

- **GW-003-P1 · Legacy converter review default.** `convert_legacy_site_config_to_v1`
  stamps generated evidence/bindings as `review_status: "accepted"`, which makes
  legacy-converted inputs appear practitioner-reviewed. Decide whether the
  default should be `pending_review` (forcing a human gate) and, if so, the
  migration handling for already-converted cases.
- **GW-003-P2 · Order-stable evidence digest.** `compute_evidence_digest` hashes
  `evidence[]` / `field_bindings[]` in document order, so reordering
  semantically-identical arrays changes the digest and invalidates
  authorizations/attestations. Decide whether to canonicalize (sort by
  `(field_path, evidence_id)` / `evidence_id`) before hashing; note this changes
  existing digest values and any stored fixtures.
- **GW-003-P3 · Important-tier conflict tiering.** Conflicting-provenance
  bindings on an *Important* field are promoted to a hard
  `EvidenceContradictionError`, which contradicts the "important → warn" tier
  model. Decide whether Important-tier conflicts should warn instead of block.

---

## Cross-cutting — `OPEN`

- **Canonical-line reconciliation.** The divergent local
  `feat/ossf-gw-003-evidence-layer` branch (no `evidence_validation.py`) vs. the
  merged `main` line needs a canonical-line decision. Tracked separately from
  any feature/fix PR.
