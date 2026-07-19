# ADR-0006: Evidence & Assumption Layer

## Status

Accepted — ossf-site-case-1.1.0 / screening-authorization-1.1.0
(OSSF-GW-003)

## Context

ADR-0005 introduced `SiteCaseV1` (`ossf-site-case-1.0.0`) with typed
operational values and a shallow `EvidenceBasis` / `DeclaredAssumption`
surface. Provenance could be *declared* (e.g. `source_basis="measured"`)
without any linked evidence record, review status, or field binding. The
pipeline proceeded to preflight unchanged.

OSSF-GW-003 requires that consequential inputs be bound to source,
confidence, and practitioner review status **before** preflight, without
changing physics, SAD thresholds, or the physics registry.

## Decision

1. **Schema bump to `ossf-site-case-1.1.0`.** Parallel schema file;
   `ossf-site-case-1.0.0` schema file remains protected/unchanged.
   Governed screening **rejects** 1.0.0 inputs with an explicit migration
   message — no silent evidence fabrication.

2. **`ProvenanceClass` is canonical:** `measured`, `documented`,
   `database_derived`, `assumed`, `regulatory_default`. Legacy
   `EvidenceBasis` strings are mapped at parse (`estimated`→`assumed`,
   `literature`→`documented`).

3. **Typed evidence records and field bindings** (`evidence[]`,
   `field_bindings[]`) with closed `EvidenceConfidence` and
   `EvidenceReviewStatus` enums. Each binding carries exactly one
   resolution route (`evidence_id` xor `database_id` xor
   `regulatory_authority`); load-bearing fields require exactly one
   binding.

4. **Load-bearing registry** in code (`evidence_registry.py`): Critical
   fields (gradient, depth, soil_id, active receptor distances, gating
   source terms + basis) refuse when unbound or rejected; Important
   fields (treatment, dispersivity) warn on pending/rejected.

5. **Pipeline insertion:** after `validate_site_case`, before preflight.
   Critical evidence failures raise `EvidenceValidationError` (exit 1,
   evidence-failure artifact) — distinct from preflight refusal (exit 2).

6. **Authorization binds `evidence_digest`.** Schema
   `screening-authorization-1.1.0`; signature
   `authorize_screening(case, determination, evidence_result)`.
   Attestation stamps digest + review summary.

## Consequences

- All governed fixtures and `config/site_example.json` migrate to 1.1.0
  with complete bindings.
- Legacy converter emits explicit assumed/database_derived/regulatory
  bindings (never measured).
- Physics, SAD thresholds, and `physics_registry` are unchanged.

## Non-goals

UI, document uploads, OCR, evidence persistence, new SAD rules, new
physics, automatic narrative inference.
