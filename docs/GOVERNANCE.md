# Governance

This document explains the governance model of the OSSF groundwater
screening tool. It exists so any future maintainer, reviewer, or
challenging expert can locate the doctrine, code, and evidence
supporting every decision the tool makes.

## Governance layers

The tool is governed at five layers, each with its own artifact type:

**1. Architecture Decision Records (ADRs).** Every non-trivial design
decision is captured as a numbered ADR under `docs/adr/`. An ADR is
never edited after acceptance; it is superseded by a later ADR.
Currently accepted:

- ADR-0001 — Screening Scope and Refusal Doctrine (sad-1.0.0)
- ADR-0002 — Physics Engine Tier Structure (screening-1.0.0)
- ADR-0003 — Authorization Contract and Execution Boundary
  (screening-authorization-1.0.0)
- ADR-0005 — Versioned Site Case Input Contract (ossf-site-case-1.0.0)

  ADR-0004 records the shared output `status` / exit-code contract
  (`core/result_contract.py`); the governed driver is the sole consumer.

**2. The versioned input contract (`SiteCaseV1`).** The input boundary
owns the *shape and validity of input* before any interpretation runs
(ADR-0005). Raw JSON is parsed into an immutable, unit-explicit,
schema-versioned `SiteCaseV1` and fully validated — structural, cross-field,
database-reference, and engine-compatibility — before preflight. Malformed,
ambiguous, contradictory, or physically implausible input is rejected here
with actionable, field-pathed errors and never reaches preflight,
authorization, or physics. Key properties (all in `core/contracts/`):

- **Schema version required.** Every case declares
  `schema_version = "ossf-site-case-1.0.0"`; a missing/blank/unsupported
  version is rejected (`UnsupportedSchemaVersionError`).
- **Canonical units.** Dimensional fields carry their unit in the name
  (`distance_m`, `depth_to_groundwater_m`, `design_flow_gpd`, …). No unit
  guessing or conversion.
- **Typed operational values.** Enums replace free-form strings; **no
  operational branch depends on a substring search** (SAD-007 keys off
  `treatment_level`/`disinfection_status`, not narrative text).
- **One governed hash.** `site_case_hash` is computed from the normalized,
  serialized contract; raw dictionaries are never hashed for governed
  execution. Authorization binds to this normalized V1 hash.
- **Explicit, bounded migration.** `convert_legacy_site_config_to_v1` maps a
  known pre-V1 config through an explicit table and refuses ambiguous input
  rather than guessing; unversioned configs are auto-routed through it.

The contract owns data shape, types, units, enums, structural/internal
consistency, and database-reference validity. It does **not** own regulatory
suitability, authorization, or physics.

**3. The authorization contract and execution boundary.** Scope refusal
is enforced by a single authority (ADR-0003), not by a decorator. The
pipeline is:

```
raw JSON -> parse SiteCaseV1 -> preflight (SAD) -> authorize_screening -> run_authorized_engine -> attestation
 detect      validate +           disposition       mints a token from     the single execution     stamps schema
 schema      normalize            proceed/warn/      a PERMITTING (proceed/  boundary: validates      version + hash;
 (layer 2)   (invalid =>          refuse             warn) determination;    the token against the    run authorized
             exit 1, no                              refuse => denied, no    validated case (schema,  (see layer 4)
             preflight)                              token, no physics       config-binding, tamper)
```

Key properties (all in `core/authorization.py` and
`core/physics_registry.py`):

- **No token for a refused site.** `authorize_screening` raises
  `AuthorizationDeniedError` for a `refuse` determination; there is no
  override.
- **Config-binding.** A `ScreeningAuthorization` carries the
  canonical-JSON hash of the config it was minted from. The boundary
  recomputes and compares it, so a token cannot be replayed against a
  different config.
- **Tamper-evidence.** The `findings_digest` and `authorization_id`
  recompute from the token's own fields; any edit is detected.
- **Single boundary, no bypass.** `run_authorized_engine` is the only
  production path to an engine. `get_engine` is metadata-only, and the
  engine's `evaluate` refuses to run without a permitting token, so even
  a direct call cannot bypass the contract.

The only remaining governance decorator is
`@methodology_attested(engine_name, engine_version)` in
`core/governance.py`, which marks an engine's output as P.E.-sealable and
carries the engine identity into the attestation.

**4. Attestation.** Every successful output artifact (JSON and text
report) carries a top-level `attestation` block with:

- `methodology_version` — the tool's overall methodology version
- `preflight_ruleset_version` — SAD ruleset version
- `preflight_disposition` — `proceed` or `warn`
- `physics_engine` and `physics_engine_version` — the engine used
- `soil_db_hash` and `pathogens_db_hash` — SHA-256 short digests of
  the data files at the time of the run
- `input_schema_version` — the input contract version consumed
  (`ossf-site-case-1.0.0`)
- `site_config_hash` — SHA-256 of the **normalized, serialized
  `SiteCaseV1`** (the single governed hashing route; not a raw dict)
- `authorization_schema_version` and `authorization_id` — the
  authorization the run executed under
- `findings_digest` — digest of the preflight findings
- `warning_count` and `refusal_count` — preflight finding tallies
- `generated_utc` — UTC timestamp

The artifact also carries a top-level `authorization` block (the full
token). `build_attestation` refuses to stamp a successful run that is not
carrying permitting authorization metadata bound to the same config. A
refusal artifact instead carries `authorization: {authorized: false, ...}`
with the denial reason.

A submittal sealed today can be exactly reproduced from source in
five years by checking out the commit whose files match these hashes
and re-running with the same config.

**5. Characterization tests.** Every physics engine has non-negotiable
sanity-limit tests in `tests/`. They pin correctness against known
analytical or numerical results. If they fail, the engine must not
be used to produce sealed output. See
`tests/test_physics_ogata_banks.py` for the pattern.

## Adding a new physics engine

The process for adding a new engine (e.g., `domenico_3d`,
`hydrus_1d_wrapper`) is:

1. Implement the module with an `evaluate(**kwargs)` callable marked
   `@methodology_attested`.
2. Register the engine in `core/physics_registry.py` with a
   descriptive `scope_notes` string.
3. Write sanity-limit tests in `tests/` — at minimum, a limit that
   reduces to a known engine result (e.g., a Domenico engine in the
   low-transverse-dispersion limit should reduce to Ogata-Banks).
4. Open an ADR documenting the engine's scope-of-applicability and the
   physical/regulatory reason it was added.
5. Update this document with the new ADR reference.

## Modifying the preflight ruleset

The process for adding, removing, or modifying a rule in the SAD:

1. Increment `PREFLIGHT_RULESET_VERSION` in `core/governance.py`.
2. Add the rule function to `core/preflight.py`, cite its regulatory
   authority in the `RuleFinding.authority` field.
3. Register the rule in the `RULES` list at the bottom of
   `core/preflight.py`.
4. Open (or update) ADR-0001 to reflect the new rule.
5. Add or update characterization tests that exercise the rule.

## Modifying the input contract

The process for changing the `SiteCaseV1` contract (adding a field, an enum
value, or a validation rule):

1. Update the records/enums/validators in `core/contracts/` and keep the
   checked-in schema (`schemas/ossf-site-case-1.0.0.schema.json`) in lockstep.
2. A **backward-incompatible** change (removing/renaming a field, changing a
   unit, tightening a required field) requires a new schema version
   (`ossf-site-case-1.1.0` / `-2.0.0`) and a new ADR; do **not** silently
   redefine `ossf-site-case-1.0.0`.
3. Extend the explicit legacy mapping table only with known, unambiguous
   values — no heuristic text interpretation.
4. Add positive and negative tests, including a fixture-vs-schema equivalence
   test, and ensure canonical fixtures still validate.
5. Never add a silent material default: any permitted default must be
   non-interpretive, documented, deterministic, serialized, and tested.

## What is NOT governed by this document

The following are outside the scope of the tool and this governance
model. They are the responsibility of the engineer of record:

- Whether a specific site actually falls within the tool's scope. The
  preflight rules encode heuristics; the engineer's professional
  judgment is authoritative.
- Whether the values in `data/soil_database.json` are appropriate for
  the specific soil at the site. The database uses USDA texture-class
  averages (Carsel & Parrish 1988). Site-specific values should
  override via the site config.
- Whether the hydraulic gradient in the site config was correctly
  determined from piezometer or topographic data.
- Whether the declared `treatment_level` / `disinfection_status` match the
  manufacturer specification.
- Whether the receptors enumerated in the site config include every
  regulated feature.
- The final decision on whether the tool's output is fit for
  attachment to a permit application. That decision belongs to the
  P.E. of record.

## Reference: methodology and ruleset versions in force

| Component | Version | ADR |
|---|---|---|
| Overall methodology | `screening-1.0.0` | — |
| Input contract | `ossf-site-case-1.0.0` | ADR-0005 |
| Preflight ruleset | `sad-1.0.0` | ADR-0001 |
| Default physics engine | `ogata_banks_1d` v1.0.0 | ADR-0002 |
| Authorization contract | `screening-authorization-1.0.0` | ADR-0003 |
