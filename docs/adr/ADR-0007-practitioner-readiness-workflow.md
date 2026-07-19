# ADR-0007: Practitioner Readiness Workflow

## Status

Accepted — screening-readiness-1.0.0 / screening-authorization-1.2.0
(OSSF-GW-004)

## Context

ADR-0006 (OSSF-GW-003) bound load-bearing inputs to evidence records,
field bindings, and practitioner review status before preflight. Evidence
validation answers *whether consequential inputs are complete and
review-accepted*. It does not produce a separate, digest-bound readiness
decision that later case history (GW-005) can cite.

Authorization (ADR-0003, amended by ADR-0006) already binds
`evidence_digest`. GW-004 needs an explicit **practitioner readiness**
step between evidence validation and preflight/authorization so that:

1. Important-tier evidence warnings are carried forward as readiness
   warnings without inventing new SAD rules.
2. Critical binding acceptance and linked-assumption verification status
   are re-checked deterministically.
3. A stable `readiness_digest` exists for authorization, attestation, and
   future CaseHistory binding.

## Decision

1. **New package `core/readiness/`** owns assessment contracts, digest
   computation, and readiness errors. It does **not** own SiteCase,
   evidence validation, SAD thresholds, or physics.

2. **Schema identity.** `READINESS_SCHEMA_VERSION =
   "screening-readiness-1.0.0"`. No SiteCase schema bump — readiness is
   computed from SiteCase 1.1.0 + `EvidenceValidationResult`.

3. **Dispositions.** `ready`, `ready_with_warnings`, `not_ready`.
   `permits_authorization` is true only for the first two. Worst
   disposition wins: `not_ready` > `ready_with_warnings` > `ready`.

4. **Code-owned rules (deterministic):**
   - **RDY-001** — evidence result must permit preflight; else `not_ready`
   - **RDY-002** — recomputed `evidence_digest` must match; mismatch →
     `not_ready` (tamper)
   - **RDY-003** — Important-tier evidence warnings →
     `ready_with_warnings`
   - **RDY-004** — every critical load-bearing binding must be
     `accepted`; else `not_ready`. Uses the shared
     `iter_critical_binding_acceptance_issues` helper from the evidence
     layer so acceptance semantics cannot drift from GW-003.
   - **RDY-005** — linked assumptions with `pending_verification` on
     critical bindings → `ready_with_warnings` (do not block)

5. **`readiness_digest`** = 16-hex `sha256_of_json_stable` of schema
   version, `case_hash`, `evidence_digest`, disposition, and normalized
   findings (`finding_id`, `severity`, `code` only). Wall-clock
   `assessed_utc` is excluded from the digest.

6. **Pipeline insertion:** after `validate_evidence_layer`, before
   preflight. `not_ready` → readiness-failure artifact, exit 1, no
   preflight/physics.

7. **Authorization binds `readiness_digest`.** Schema
   `screening-authorization-1.2.0`; signature
   `authorize_screening(case, determination, evidence_result,
   readiness_result)`. Attestation stamps `readiness_digest` +
   readiness disposition.

## Consequences

- Success and auth-refusal artifacts embed a `readiness` summary block.
- Future GW-005 CaseHistory can bind `readiness_digest` without
  re-deriving assessment rules.
- Physics, SAD thresholds, and SiteCase 1.1.0 remain unchanged.

## Non-goals

UI, persistence, collaboration, history ledger (GW-005), new SAD
thresholds, new physics, SiteCase 1.2.0 bump, user accounts.
