# SiteCaseV1 — Governed Input Contract Reference

**Schema identifier:** `ossf-site-case-1.0.0`
**Authoritative schema:** [`schemas/ossf-site-case-1.0.0.schema.json`](../schemas/ossf-site-case-1.0.0.schema.json)
**Design decision:** [ADR-0005](adr/ADR-0005-versioned-site-case-input-contract.md)

`SiteCaseV1` is the canonical, versioned, immutable, unit-explicit input
contract for every governed OSSF groundwater screening. Raw JSON is parsed and
fully validated into a `SiteCaseV1` *before* preflight; malformed, ambiguous,
contradictory, or physically implausible input is rejected here with
actionable, field-pathed errors and never reaches preflight, authorization, or
physics.

The contract layer owns **data shape, types, canonical units, enum values,
structural validity, internal consistency, database-reference validity, and
normalized serialization**. It does **not** own regulatory suitability
(preflight), execution permission (authorization), or physics.

## Conventions

- **Canonical units are in the field name.** There is no unit object and no
  automatic conversion. A value in the wrong unit is a data error the tool
  cannot detect — the engineer of record is responsible for supplying values
  in the canonical unit.
- **Operational values are typed enums.** No behavior depends on free-form
  text; notes fields exist but are never branched on.
- **Stable IDs** match `^[A-Za-z0-9][A-Za-z0-9_.-]*$` and must be unique within
  their collection.
- **Numbers must be finite** (no `NaN`/`Infinity`); integers are normalized to
  floats on construction so serialization is deterministic.
- Objects marked *additionalProperties: false* reject unknown keys.

## Top-level object

| JSON path | Type | Required | Meaning |
|---|---|---|---|
| `schema_version` | const `"ossf-site-case-1.0.0"` | yes | Input contract version. A missing/blank/unsupported value is rejected. |
| `site_id` | stable ID | yes | Unique case identifier; used in output filenames. |
| `project` | object | yes | Non-interpretive project metadata. |
| `regulatory_location` | object | yes | Structured regulatory-zone facts. |
| `treatment` | object | yes | Structured treatment + disinfection. |
| `source` | object | yes | Effluent source term. |
| `subsurface` | object | yes | Soil reference + unsaturated-zone thickness. |
| `groundwater` | object | yes | Groundwater depth + hydraulic gradient. |
| `receptors` | array | yes (≥1) | Receptors evaluated by physics. |
| `constituents` | array | yes (≥1) | Constituents evaluated. |
| `physics` | object | yes | Engine + method selection. |
| `reporting` | object | no (default `{}`) | Reporting configuration. |
| `assumptions` | array | no (default `[]`) | Declared engineering assumptions. |

## `project` — ProjectMetadata

All free-form; **no operational branch depends on these values.**

| JSON path | Type | Required | Notes |
|---|---|---|---|
| `project.name` | non-empty string | yes | Project/site name. |
| `project.engineer` | non-empty string | yes | Engineer of record. |
| `project.county` | non-empty string | yes | County, state. |
| `project.regulatory_authority` | non-empty string | yes | e.g. `30 TAC Ch. 285`. |
| `project.description` | string / null | no | Free-form. |

## `regulatory_location` — RegulatoryLocation

Structured booleans (not narrative). SAD-001 / SAD-002 key off these.

| JSON path | Type | Required | Default | Downstream use |
|---|---|---|---|---|
| `regulatory_location.edwards_aquifer_recharge_zone` | bool | no | `false` | SAD-001 → refuse if true. |
| `regulatory_location.edwards_aquifer_transition_zone` | bool | no | `false` | Recorded. |
| `regulatory_location.edwards_aquifer_contributing_zone` | bool | no | `false` | Recorded. |
| `regulatory_location.karst_terrain` | bool | no | `false` | SAD-002 → refuse if true. |
| `regulatory_location.coastal_zone` | bool | no | `false` | Recorded. |
| `regulatory_location.notes` | string / null | no | — | Free-form. |

## `treatment` — TreatmentConfiguration

Replaces the pre-V1 free-form `source.treatment_class` string. SAD-007 keys off
`treatment_level` and `disinfection_status`.

| JSON path | Type | Required | Allowed values |
|---|---|---|---|
| `treatment.treatment_level` | enum | yes | `primary`, `secondary`, `advanced_secondary` |
| `treatment.disinfection_status` | enum | yes | `none`, `disinfected` |
| `treatment.disinfection_method` | enum | no (default `none`) | `none`, `chlorine`, `uv`, `ozone`, `other` |
| `treatment.notes` | string / null | no | Free-form |

**Consistency (cross-field):** `disinfection_method` must be `none` when
`disinfection_status` is `none`; a method is required when status is
`disinfected`.

## `source` — SourceConfiguration

| JSON path | Type | Unit | Required | Constraint |
|---|---|---|---|---|
| `source.design_flow_gpd` | number | gallons/day | yes | > 0, finite |
| `source.description` | string / null | — | no | Free-form |

## `subsurface` — SubsurfaceConfiguration

Soil physical properties (K_sat, porosity, bulk density) are resolved from the
soil database by `soil_id` — **never duplicated here.**

| JSON path | Type | Unit | Required | Constraint |
|---|---|---|---|---|
| `subsurface.soil_id` | stable ID | — | yes | Must exist in `data/soil_database.json` |
| `subsurface.soil_thickness_m` | number | metres | yes | > 0, finite |

## `groundwater` — GroundwaterConfiguration

| JSON path | Type | Unit | Required | Constraint |
|---|---|---|---|---|
| `groundwater.depth_to_groundwater_m` | number | metres | yes | > 0, finite |
| `groundwater.hydraulic_gradient` | number | dimensionless | yes | ≥ 0, finite (a negative gradient is a sign-convention error and is rejected) |

## `receptors[]` — ReceptorDefinition

At least one receptor is required; `receptor_id` values must be unique.

| JSON path | Type | Unit | Required | Notes |
|---|---|---|---|---|
| `receptors[].receptor_id` | stable ID | — | yes | Unique within the array. |
| `receptors[].receptor_type` | enum | — | yes | `private_well`, `public_well`, `property_boundary`, `surface_water`. Type-specific setbacks (SAD-005) key off this. |
| `receptors[].distance_m` | number | metres | yes | > 0, finite. |
| `receptors[].display_name` | non-empty string | — | yes | For the report. |
| `receptors[].active` | bool | — | no (default `true`) | When `false`, the receptor is retained for documentation but **excluded** from preflight setback checks, physics runs, and nearest-receptor comparison scenarios. At least one active receptor is required. |
| `receptors[].notes` | string / null | — | no | Free-form. |

Coordinates, bearing, screened interval, and off-axis location are **out of
scope** for V1.

## `constituents[]` — ConstituentSelection

At least one is required; `constituent_id` values must be unique and must exist
in `data/pathogens.json`. The source concentration is **either** explicit
**or** a visibly selected governed default — never inferred from the
constituent name. Exactly one of the two must hold.

| JSON path | Type | Required | Notes |
|---|---|---|---|
| `constituents[].constituent_id` | stable ID | yes | Must exist in the constituent database. |
| `constituents[].role` | enum | yes | `gating` (drives pass/fail) or `reference_only` (reported, never gates). |
| `constituents[].source_concentration` | number / null | conditional | Explicit source concentration in the constituent's canonical unit; ≥ 0, finite. |
| `constituents[].use_governed_default` | bool | conditional | `true` selects the governed database default (`typical_C0_post_disinfection`). |
| `constituents[].source_basis` | enum | no (default `regulatory_default`) | `measured`, `estimated`, `literature`, `regulatory_default`, `assumed`. |
| `constituents[].notes` | string / null | no | Free-form. |

## `physics` — PhysicsSelection

Engine registration and method/engine compatibility are validated by the
contract (before physics runs), not at physics time.

| JSON path | Type | Required | Notes |
|---|---|---|---|
| `physics.engine` | non-empty string | yes | Must be a registered engine (currently `ogata_banks_1d`). |
| `physics.dispersivity_method` | enum | yes | `epa_ssg` or `xu_eckstein` (both supported by `ogata_banks_1d`). |

## `reporting` — ReportingMetadata

| JSON path | Type | Required | Notes |
|---|---|---|---|
| `reporting.comparison_soil_ids` | array of stable IDs | no (default `[]`) | Governed comparison-soil report section; each must exist in the soil DB. |
| `reporting.notes` | string / null | no | Free-form. |

## `assumptions[]` — DeclaredAssumption

Provenance for declared engineering assumptions. Rationale is free-form; no
operational branch depends on it.

| JSON path | Type | Required | Allowed values |
|---|---|---|---|
| `assumptions[].assumption_id` | stable ID | yes | Unique within the array. |
| `assumptions[].description` | non-empty string | yes | Free-form rationale. |
| `assumptions[].basis` | enum | yes | `measured`, `estimated`, `literature`, `regulatory_default`, `assumed`. |
| `assumptions[].status` | enum | yes | `assumed`, `verified`, `pending_verification`. |

## Validation order

1. raw JSON shape → 2. schema-version selection → 3. primitive field parsing →
4. nested-record construction → 5. structural validation → 6. cross-field
validation → 7. database-reference resolution → 8. engine-option compatibility
→ 9. canonical normalization.

No hash or preflight determination is produced before this sequence succeeds.
Validation never returns a Boolean: it returns a fully valid, immutable
`SiteCaseV1` or raises a typed exception (`ContractValidationError` and its
subclasses, `UnsupportedSchemaVersionError`, or `LegacyConfigError`) carrying
field-pathed `FieldValidationError` records.

## Hashing and identity

The canonical `site_config_hash` is computed from the **normalized, serialized
`SiteCaseV1`** (`site_case_hash`) — the single governed hashing route. Raw
dictionaries are never hashed for governed execution. Because serialization
sorts keys, the hash is key-order-invariant; changing any material field
changes the hash. The authorization binds to this hash and the attestation
stamps it alongside `input_schema_version`.

## Legacy migration

Unversioned pre-V1 configs are converted by the single explicit converter
`convert_legacy_site_config_to_v1`, which maps known narrative values through
an explicit table, generates deterministic receptor IDs, and **refuses**
materially ambiguous input (e.g. an unlisted `treatment_class`) rather than
guessing. See `tests/test_site_case_legacy.py`.
