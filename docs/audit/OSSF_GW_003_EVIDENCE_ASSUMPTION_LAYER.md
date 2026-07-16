# OSSF-GW-003: Evidence & Assumption Layer — Dev-Ready Handoff

**Program:** OSSF groundwater screening (`ground-water-hydraulics-ossf`)  
**Status:** **IMPLEMENTATION IN PROGRESS** — owner §12 sign-off received 2026-07-16  
**Prepared:** 2026-07-15 (forks ratified 2026-07-16)  
**Implementation baseline:** `feb5f7d6d7a4d58081ddc17de584f065c48b6291`  
  (`main` after PR #21 merge; verified 226 tests green)  
**Input contract baseline:** `ossf-site-case-1.0.0` (`SiteCaseV1`) → `ossf-site-case-1.1.0`

---

## 0. Mission (narrow)

Add a **governed evidence-and-assumption layer** that binds each consequential
`SiteCaseV1` input to its **source**, **confidence**, and **practitioner review
status** *before* preflight.

```text
SiteCaseV1 (parsed + structurally valid)
        ↓
Evidence records + assumption records + field bindings
        ↓
Evidence completeness / contradiction validation
        ↓
Practitioner review status gate
        ↓
Preflight (SAD — unchanged thresholds in GW-003)
        ↓
Authorization → Physics → Attestation
```

GW-003 strengthens **provenance and reviewability** of load-bearing inputs.
It does **not** expand physics, scenarios, or practitioner UI.

---

## 1. Authorization & sequencing

**Prerequisites (satisfied on integration branch @ `02915a9`):**

| Gate | Evidence |
|---|---|
| GW-001 tests green | 214 passed locally |
| GW-002 tests green | included in suite |
| Authorization boundary enforced | `tests/test_governed_execution.py` |
| SiteCaseV1 serialization stable | `tests/test_site_case_serialization.py` + schema fixture |

**Not authorized yet:** implementation, UI, document uploads, OCR, database
persistence, new preflight SAD thresholds, new physics, scenario analysis,
hazardous-waste abstractions, automatic report interpretation.

**Implementation may begin only after:** this handoff is reviewed, `main` carries
the GW-001/GW-002 stack (see §2), and owner signs §12.

---

## 2. Upstream integration note (`main` merge)

**Satisfied.** PR #21 merged the GW-001/GW-002 stack onto `main` at `feb5f7d`.
Post-merge verification: full pytest suite green (226 passed).

---

## 2.1 Ratified implementation forks (2026-07-16)

Owner ratified the following GW-003 forks. These are binding for implementation.

| # | Fork | Ruling | Implementation note |
|---|---|---|---|
| **1** | SiteCase 1.0.0 under GW-003 | **1B** | Reject for governed screening; explicit migration to `1.1.0` required. No silent evidence fabrication. |
| **2** | Provenance enum | **2A** | `ProvenanceClass` is canonical on 1.1.0. Map legacy `EvidenceBasis` values at parse/migration; do not leave two authorities. |
| **3** | Confidence | **3A** | Closed enum: `low` / `medium` / `high` / `unknown`. No free numeric score. |
| **4** | Rejected important evidence | **4B** | Evidence warning (material); may proceed if preflight permits. Distinct from critical refusal. |
| **5** | Critical evidence failure artifact | **5B** | Write evidence-failure JSON (and optional text) with errors/digest; exit `1`; no preflight/physics. |
| **6** | `authorize_screening` shape | **6A** | `authorize_screening(case, determination, evidence_result)` — evidence result passed explicitly. |
| **7** | Fatal evidence API style | **7A** | Raise typed `EvidenceContractError` subclasses (match contract layer). Driver maps to exit `1` + artifact. |
| **8** | Reporting | **8A** | Evidence sections in `simulate.py` + `core/result_contract.py` only. Do **not** revive `core/report.py`. |
| **9** | Constituent load-bearing scope | **9C** | `role == reference_only` skips source-concentration requirements; active receptors use `receptors[].active`. No new `constituents[].active` flag in GW-003. |
| **10** | DB/regulatory bindings | **10A** | Binding may omit `evidence_id` when it carries governed `database_id` or regulatory authority citation on the binding. |

**GW-004 decisions** (`1B 2C 3A 4A 5A 6A 7A 8A 9B 10B`) are recorded separately and
will be written into the GW-004 handoff after GW-003 merges. GW-004 code remains
unauthorized until then.

---

## 3. Problem statement (repository-grounded)

GW-002 introduced:

| Existing artifact | Location | GW-003 gap |
|---|---|---|
| `EvidenceBasis` enum | `core/contracts/enums.py` | Used on `ConstituentSelection.source_basis` and `DeclaredAssumption.basis` only — **no evidence records** |
| `AssumptionStatus` enum | `core/contracts/enums.py` | On `DeclaredAssumption.status` — **not bound to fields** |
| `DeclaredAssumption` | `core/contracts/site_case_v1.py` | Free-standing rationale rows; **no field bindings**, no review workflow |
| `assumptions[]` on case | schema + parser | Defaults to `[]`; **never validated for completeness** |
| `source_basis` per constituent | `ConstituentSelection` | Declares provenance class but **no supporting evidence record** |

Operational values already typed; **provenance is declared but not governed**.
A practitioner (or API) can mark `source_basis="measured"` with no linked
evidence, and the pipeline proceeds to preflight unchanged.

---

## 4. Ratified scope

### 4.1 In scope (define + later implement)

| Area | Requirement |
|---|---|
| **Typed evidence records** | Immutable records: stable `evidence_id`, source description, basis class, confidence, capture metadata (text/date only — no file blobs) |
| **Explicit assumption records** | Extend/replace shallow `DeclaredAssumption` usage so assumptions reference evidence or declared basis consistently |
| **Evidence-to-field bindings** | Map `evidence_id` → canonical field paths (e.g. `groundwater.hydraulic_gradient`, `constituents[e_coli].source_concentration`) |
| **Provenance classifications** | Closed enum covering **measured**, **documented**, **database_derived**, **assumed**, **regulatory_default** — align with or supersede ad-hoc `EvidenceBasis` where load-bearing |
| **Completeness validation** | Registry of load-bearing fields; each must have a binding + compatible basis |
| **Contradiction validation** | Reject (contract error) when basis class and binding evidence disagree (e.g. `measured` with no evidence; two conflicting bases for one field) |
| **Practitioner review status** | Per evidence record and per load-bearing binding: `pending_review`, `accepted`, `rejected`, `superseded` |
| **Review gate** | Load-bearing fields with `pending_review` or `rejected` evidence → **block authorization** (contract/evidence gate, not new SAD threshold) |
| **Serialization + schema** | Bump to `ossf-site-case-1.1.0` (preferred) or additive 1.0.x extension with explicit migration note |
| **Authorization propagation** | Stamp `evidence_digest` (canonical hash of evidence+bindings subset) alongside existing `site_config_hash` binding |
| **Result artifact propagation** | Embed evidence summary block in successful JSON output; embed evidence refusal/warning block when gate fails |
| **Missing load-bearing evidence** | **Refuse** (exit 1, contract/evidence error) when required binding absent; **warn** when non-critical evidence pending review (configurable field tier — see §6) |

### 4.2 Explicitly out of scope

- UI implementation, document uploads, OCR, external evidence stores
- Database persistence beyond existing JSON file workflow
- New SAD preflight thresholds or new physics engines
- Scenario analysis, hazardous-waste abstractions
- Automatic interpretation of third-party reports
- Implicit evidence inference from narrative text

---

## 5. Pipeline insertion point

GW-003 adds a validation stage **after** existing GW-002 contract validation
and **before** `evaluate_site()`:

```text
load_site_case_json / convert_legacy
    → parse_site_case_dict          (existing)
    → validate_site_case            (existing cross-field + DB + engine)
    → validate_evidence_layer       (NEW — GW-003)
    → evaluate_site                 (unchanged SAD rules)
    → authorize_screening           (binds case + evidence digest)
    → run_authorized_engine
    → build_attestation             (stamps evidence digest)
```

**Invariant:** evidence validation **never** calls the physics engine and
**never** auto-writes project state. It only reads the immutable case.

---

## 6. Load-bearing field registry (initial)

Define in code (not config files) for V1.1. Fields requiring bindings:

| Tier | Field path | Rationale |
|---|---|---|
| **Critical** | `groundwater.hydraulic_gradient` | Drives seepage velocity; SAD-006 envelope |
| **Critical** | `groundwater.depth_to_groundwater_m` | SAD-003 shallow water table |
| **Critical** | `subsurface.soil_id` | K_sat / retardation path |
| **Critical** | `receptors[].distance_m` (active only) | SAD-005 setbacks |
| **Critical** | `constituents[].source_concentration` or governed default | Source term |
| **Critical** | `constituents[].source_basis` | Must match binding class |
| **Important** | `treatment.treatment_level` | SAD-007 |
| **Important** | `treatment.disinfection_status` | SAD-007 |
| **Important** | `physics.dispersivity_method` | Engine compatibility |

**Critical** missing binding → contract/evidence **refusal** (exit 1).  
**Important** pending review → **warn** artifact flag; may still authorize if
owner policy allows (default: warn-only for Important, refuse for Critical).

Registry lives in `core/contracts/evidence_registry.py` (new — see §7.1).

---

## 7. Repository-grounded file plan

Conventions: `docs/audit/OSSF_GW_*`, colocated `tests/test_*.py`, ADR under
`docs/adr/`. No speculative modules pre-authorized.

### 7.1 Definite — must change or add

| File | Change |
|---|---|
| `core/contracts/enums.py` | Add `ProvenanceClass`, `EvidenceReviewStatus`, `FieldTier`; reconcile with existing `EvidenceBasis` |
| `core/contracts/site_case_v1.py` | Add `EvidenceRecord`, `FieldEvidenceBinding`; extend `SiteCaseV1` with `evidence[]` (and refine `assumptions[]` linkage) |
| `core/contracts/evidence_registry.py` | **New.** Load-bearing field registry + tier policy |
| `core/contracts/evidence_validation.py` | **New.** Completeness, contradiction, review-status gate |
| `core/contracts/validation.py` | Call evidence validation from `validate_site_case` or export separate gate invoked by driver |
| `core/contracts/serialization.py` | Parse/serialize 1.1.0 evidence sections; version gate |
| `core/contracts/__init__.py` | Export new types + `validate_evidence_layer` |
| `schemas/ossf-site-case-1.1.0.schema.json` | **New.** JSON Schema for extended contract |
| `schemas/ossf-site-case-1.0.0.schema.json` | **Protected** — unchanged |
| `core/authorization.py` | Include `evidence_digest` in authorization binding + id derivation (schema bump → `screening-authorization-1.1.0`) |
| `core/governance.py` | Stamp `evidence_digest` + review summary counts on `MethodologyAttestation` |
| `simulate.py` | Invoke evidence gate; embed evidence block in output; exit 1 on critical evidence refusal |
| `docs/SITE_CASE_V1.md` | Document 1.1.0 evidence sections or add `docs/SITE_CASE_V1_1.md` |
| `docs/adr/ADR-0006-evidence-assumption-layer.md` | **New.** Decision record |
| `docs/GOVERNANCE.md` | Cross-link evidence gate in pipeline diagram |
| `tests/test_site_case_evidence.py` | **New.** Completeness, contradiction, review gate |
| `tests/test_site_case_evidence_serialization.py` | **New.** Round-trip + schema equivalence |
| `tests/test_authorization.py` | Evidence digest binding breaks on tamper |
| `tests/test_governed_execution.py` | Attestation stamps evidence digest |
| `tests/test_end_to_end.py` | Fixture with evidence bindings; critical-missing → exit 1 |

### 7.2 Conditional — only if documented trigger

| File | Trigger |
|---|---|
| `core/contracts/legacy.py` | Legacy converter must emit minimal assumed bindings for converted fields |
| `core/preflight.py` | **Only if** evidence gate delegates warn disposition to preflight (default: **no** — keep out of SAD) |
| `config/site_example.json` | Update to 1.1.0 worked example after schema lands |
| `tests/fixtures/site_case_v1_*.json` | Remain 1.0.0 unless dual-version test matrix added |

### 7.3 Protected — must not change in GW-003

| File | Reason |
|---|---|
| `core/physics_ogata_banks.py` | No new physics |
| `core/preflight.py` SAD thresholds | No new preflight thresholds authorized |
| `core/physics_registry.py` | Engine registry unchanged |
| `data/soil_database.json`, `data/pathogens.json` | No DB persistence work |
| `EXECUTIVE_HANDOFF.md` | Out of scope unless owner directs |

### 7.4 Prohibited speculative additions

- Evidence upload service, blob storage, OCR pipeline
- Practitioner UI components
- Pinia/Vue or any frontend
- Generic “evidence resolver” frameworks
- Automatic basis inference from free text

---

## 8. Schema & identity

**Preferred:** `schema_version = "ossf-site-case-1.1.0"` with parallel schema file.

**Hashing:**

| Hash | Scope |
|---|---|
| `site_config_hash` | Full canonical case (existing) |
| `evidence_digest` | Canonical JSON of `evidence[]` + bindings + linked assumptions (new) |
| `authorization_id` | Rebind to include `evidence_digest` when auth schema bumps |

**Authorization identity semantics** (unchanged from GW-001): `authorization_id`
identifies the **decision**, not a single run; `generated_utc` / `granted_utc`
identify the **execution event**.

---

## 9. Refusal / warning behavior

| Condition | Behavior | Exit |
|---|---|---|
| Critical load-bearing field unbound | `EvidenceValidationError` | 1 |
| Basis class contradicts binding | `EvidenceValidationError` | 1 |
| Critical evidence `rejected` review | `EvidenceValidationError` | 1 |
| Important field `pending_review` | Evidence warning block in artifact; disposition `warn` at evidence layer | 0 if preflight still permits |
| Important evidence `rejected` review | Evidence warning block (fork **4B**); not a hard refusal | 0 if preflight still permits |
| Non-load-bearing evidence gaps | Ignored in V1.1 | — |
| Critical evidence failure (any) | Evidence-failure artifact written (fork **5B**); then exit 1 | 1 |

Evidence warnings are **distinct from SAD warnings** — stamp separately in
output (`evidence_warnings[]` vs `preflight.warnings[]`).

---

## 10. Verification plan (implementation PR)

```bash
python -m pytest tests/ -q
python -m pytest tests/test_site_case_evidence.py tests/test_site_case_evidence_serialization.py -v
python simulate.py config/site_example.json   # after example migrated to 1.1.0
```

**Manual smoke:**

1. Valid 1.1.0 case with complete bindings → exit 0; attestation includes `evidence_digest`.
2. Remove binding for `hydraulic_gradient` → exit 1 before preflight; engine call count 0.
3. Tamper `evidence_digest` after authorization → authorization mismatch at boundary.

---

## 11. Recommended commit stack (implementation)

Nine commits per the implementation authorization order:

```text
1. feat(contracts): add evidence provenance and review records
2. feat(evidence): define governed load-bearing field registry
3. feat(evidence): validate completeness contradictions and review status
4. feat(schema): add OSSF site case 1.1 evidence contract
5. feat(governance): bind authorization to evidence digest
6. feat(results): propagate evidence status through artifacts
7. feat(simulation): enforce evidence gate before preflight
8. feat(migration): add evidence-complete SiteCase 1.1 example
9. docs(governance): record evidence and assumption boundary (ADR-0006)
```

---

## 12. Implementation authorization statement

> **Owner:** Ross Echols, Jr.  
> **Date:** July 16, 2026  
> **Baseline commit:** `feb5f7d6d7a4d58081ddc17de584f065c48b6291`  
> **Verification:** 226 tests passing on `main` before implementation branch  
> **Authorized:** Implementation of OSSF-GW-003 per this handoff and ratified forks §2.1.

---

*End of OSSF-GW-003 Dev-Ready Handoff (review only).*
