# ADR-0005: Versioned Site Case Input Contract

## Status

Accepted — ossf-site-case-1.0.0

Establishes the governed *input boundary* that sits immediately upstream of
the preflight. Complements ADR-0001 (refusal doctrine) and ADR-0003
(authorization contract); it does not change either.

(ADR-0004 is reserved for the forthcoming output/result-envelope contract,
which is explicitly out of scope here — see Non-Goals.)

## Context

Before this change the tool accepted a raw, unversioned JSON dictionary and
threaded it through preflight, authorization, physics, and attestation as a
loosely-typed `dict`. Operational decisions were made by reading nested keys
and, in the case of treatment classification, by matching a **free-form
narrative string** (`source.treatment_class`). This was workable for a single
example but unsafe as the tool grows toward saved cases, a practitioner UI,
scenario analysis, and future APIs:

- missing fields surfaced as low-level `KeyError`/`TypeError` deep in the
  pipeline rather than as actionable input errors;
- units were implicit (a bare `distance_m` with no enforced meaning);
- treatment status was inferred from prose;
- the config was hashed **before** any normalization, so key ordering or
  incidental formatting could in principle change identity;
- there was no explicit, testable migration path for older configs;
- every downstream consumer depended on an undocumented dictionary shape.

The preflight, authorization, and physics layers were already well-governed.
The gap was that nothing owned the **shape and validity of the input** before
those layers ran.

## Decision

Introduce a canonical, versioned, immutable, unit-explicit input contract —
`SiteCaseV1` — as the sole governed input to the pipeline, living in a new
`core/contracts/` package.

**Schema version.** Every governed case declares
`schema_version = "ossf-site-case-1.0.0"`. A missing, blank, malformed, or
unsupported version is rejected before preflight
(`UnsupportedSchemaVersionError`). A result-schema identifier supplied as an
input schema is likewise rejected.

**Typed, immutable records.** `SiteCaseV1` and its nested records
(`ProjectMetadata`, `RegulatoryLocation`, `TreatmentConfiguration`,
`SourceConfiguration`, `SubsurfaceConfiguration`, `GroundwaterConfiguration`,
`ReceptorDefinition`, `ConstituentSelection`, `PhysicsSelection`,
`ReportingMetadata`, `DeclaredAssumption`) are frozen dataclasses that
validate themselves fail-fast in `__post_init__`. They use only the standard
library — no runtime validation framework was added (dependency policy). The
sole new dependency is `jsonschema`, and only as a **dev/test** dependency for
schema-fixture equivalence tests.

**Canonical units in field names.** Dimensional fields carry their unit
explicitly: `distance_m`, `depth_to_groundwater_m`, `hydraulic_gradient`
(dimensionless), `soil_thickness_m`, `design_flow_gpd`, etc. There is **no
automatic unit guessing or conversion** in V1.

**Typed operational values.** Free-form operational strings are replaced by
closed enums: `TreatmentLevel`, `DisinfectionStatus`, `DisinfectionMethod`,
`ReceptorType`, `DispersivityMethod`, `ConstituentRole`, `EvidenceBasis`,
`AssumptionStatus`. **No operational branch may depend on a substring search.**
Free-form notes remain allowed but carry no operational meaning. In
particular, SAD-007 now keys off `treatment_level` / `disinfection_status`
instead of parsing `treatment_class`.

**Validation ownership and order.** Validation runs in a fixed order: raw JSON
shape → schema-version selection → primitive field parsing → nested-record
construction → structural validation → cross-field validation → database
resolution → engine-option compatibility → canonical normalization. Structural
and cross-field problems accumulate into a single `ContractValidationError`
carrying field-pathed `FieldValidationError` records; reference problems raise
specific typed errors (`UnknownSoilError`, `UnknownConstituentError`,
`UnknownEngineError`, `UnsupportedPhysicsOptionError`). No hash or preflight
determination is produced before this sequence succeeds.

**Contract boundary.** The contract layer owns data shape, types, canonical
units, enum values, structural validity, internal consistency,
database-reference validity, and normalized serialization. It does **not** own
regulatory suitability (preflight), execution permission (authorization),
contaminant compliance, model interpretation, professional judgment, or
physics. Preflight remains the sole authority for site appropriateness.

**One governed hashing route.** `site_case_hash` is computed from the
normalized, serialized `SiteCaseV1` (via `governance.sha256_of_json_stable` —
still one hash algorithm). Raw dictionaries are never hashed for governed
execution, and there is no second active hashing authority. Authorization now
binds to this normalized V1 hash, and the attestation stamps
`input_schema_version` plus the normalized `site_config_hash`.

**Explicit, bounded legacy migration.** `convert_legacy_site_config_to_v1`
is the single approved converter from the pre-V1 shape. It maps known
narrative values through an explicit table, generates deterministic receptor
IDs (reported as warnings), and **refuses** materially ambiguous input rather
than guessing. The driver auto-routes an unversioned config through it; a
versioned config goes straight to the parser.

## Consequences

**Positive.** Invalid, ambiguous, contradictory, or physically implausible
input is rejected before preflight, authorization, or physics, with actionable
field paths. Operational behavior no longer depends on prose. Units are
explicit. Only normalized, validated cases are hashed, so identity is
stable and key-order-invariant. A checked-in JSON Schema documents and
validates the contract, and CI validates every canonical fixture against it.

**Negative / breaking.** The raw-dictionary Python API is intentionally
broken: preflight, authorization, and physics now require a `SiteCaseV1`.
Existing unversioned configs work only through the explicit converter. The
CLI form (`python simulate.py config/site_example.json`) is unchanged.

**Hash migration.** EX-001's canonical config hash changes because the
serialized input contract changed. This is expected: the former hash is
documented as the legacy-input hash and the V1 hash is the new canonical
identity. We do **not** claim byte-for-byte input identity across schema
versions. EX-001's *scientific* results (preflight findings, authorization
behavior, engine selection, numerical outputs) are preserved within existing
regression tolerances; the low-dispersion characterization gate remains green.

**Neutral.** Exit-code taxonomy is unchanged (`0` proceed/warn, `2` refused);
an invalid or unsupported contract exits `1` like other input errors.

## Non-Goals

No new physics, SAD rules, thresholds, regulatory interpretations, soils, or
constituents. No `ScreeningResultV1` output-envelope redesign (reserved for
ADR-0004). No unit-conversion engine, no automatic repair of invalid cases, no
silent inference from narrative fields, and no persistence/API/UI work.

## References

- OSSF-GW-002 — Versioned Site Case Contract (the engineering order).
- `core/contracts/` — the contract package (`site_case_v1`, `enums`, `errors`,
  `validation`, `serialization`, `legacy`).
- `schemas/ossf-site-case-1.0.0.schema.json` — the authoritative schema.
- `docs/SITE_CASE_V1.md` — field-by-field reference.
- ADR-0001 (refusal doctrine), ADR-0003 (authorization contract).
- `tests/test_site_case_v1.py`, `tests/test_site_case_validation.py`,
  `tests/test_site_case_serialization.py`, `tests/test_site_case_legacy.py`.
