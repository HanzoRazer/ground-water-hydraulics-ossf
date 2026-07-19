# Site Case V1.1 — Evidence & Assumption Layer

**Schema identifier:** `ossf-site-case-1.1.0`  
**Authoritative schema:** [`schemas/ossf-site-case-1.1.0.schema.json`](../schemas/ossf-site-case-1.1.0.schema.json)  
**ADR:** [ADR-0006](adr/ADR-0006-evidence-assumption-layer.md)  
**Baseline:** [SITE_CASE_V1.md](SITE_CASE_V1.md) (`ossf-site-case-1.0.0`, protected)

## Migration from 1.0.0

Governed screening **rejects** `ossf-site-case-1.0.0`. Migrate explicitly:

1. Set `schema_version` to `ossf-site-case-1.1.0`.
2. Map constituent `source_basis` to `ProvenanceClass`
   (`estimated`→`assumed`, `literature`→`documented`; others unchanged).
3. Add `evidence[]` records and `field_bindings[]` for every load-bearing
   field (see registry below). Do **not** fabricate `measured` evidence.

Unversioned legacy configs continue through `convert_legacy_site_config_to_v1`,
which emits 1.1.0 with explicit assumed/database_derived/regulatory bindings.

## New top-level sections

| Field | Type | Required | Notes |
|---|---|---|---|
| `evidence` | array | no (default `[]`) | Evidence records; completeness enforced by evidence gate |
| `field_bindings` | array | no (default `[]`) | Path → evidence / citation bindings |

## `evidence[]`

| Field | Enum / type | Required |
|---|---|---|
| `evidence_id` | stable ID | yes |
| `provenance_class` | measured / documented / database_derived / assumed / regulatory_default | yes |
| `confidence` | low / medium / high / unknown | yes |
| `review_status` | pending_review / accepted / rejected / superseded | yes |
| `source_description` | non-empty string | yes |
| `captured_date` | string \| null | no |
| `notes` | string \| null | no |
| `database_id` | string \| null | no |
| `regulatory_authority` | string \| null | no |

## `field_bindings[]`

| Field | Notes |
|---|---|
| `field_path` | Canonical path (e.g. `groundwater.hydraulic_gradient`, `receptors[well].distance_m`) |
| `provenance_class` | Must match linked evidence when `evidence_id` is set |
| `review_status` | Practitioner review for this binding (overridden by linked evidence status when `evidence_id` is set) |
| `evidence_id` | Resolution route A — link into `evidence[]` |
| `database_id` | Resolution route B — standalone database_derived citation (no `evidence_id`) |
| `regulatory_authority` | Resolution route C — standalone regulatory_default citation (no `evidence_id`) |
| `assumption_id` | Optional link into `assumptions[]` |
| `notes` | Free-form; non-operational |

**Exactly one resolution route** must be present: `evidence_id` **xor**
`database_id` **xor** `regulatory_authority`. When an `evidence_id` is set,
put `database_id` / `regulatory_authority` on the evidence record, not on
the binding. Load-bearing fields require exactly one binding (duplicates
are contradictions, even with matching provenance).

## Load-bearing registry (Critical unless noted)

| Tier | Field path |
|---|---|
| Critical | `groundwater.hydraulic_gradient` |
| Critical | `groundwater.depth_to_groundwater_m` |
| Critical | `subsurface.soil_id` |
| Critical | `receptors[{id}].distance_m` (active only) |
| Critical | `constituents[{id}].source_concentration` **or** `.use_governed_default` (non-`reference_only`) |
| Critical | `constituents[{id}].source_basis` (non-`reference_only`) |
| Important | `treatment.treatment_level` |
| Important | `treatment.disinfection_status` |
| Important | `physics.dispersivity_method` |

**Critical** missing/rejected → `EvidenceValidationError`, exit 1, evidence-failure artifact.  
**Important** pending_review or rejected → warn; may proceed to preflight.
