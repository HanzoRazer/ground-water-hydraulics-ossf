# Output Contract — Groundwater Screening Toolkit

**Methodology version:** `screening-2.0.0`
**Effective from:** ADR-0005

---

## Purpose

This document defines the output schema and stability guarantees for
results produced by this toolkit.  Consumers that depend on the output
structure (report builders, downstream JSON parsers, audit tools) should
pin to a methodology version and update when breaking changes are made.

## Versioning policy

The output contract is versioned with the `screening-result-` namespace.
Current version: `screening-result-1.0.0`.

A MAJOR bump indicates a field was removed or renamed.
A MINOR bump indicates a new optional field was added.
A PATCH bump indicates documentation or comment changes only.

## `run_screening()` output schema

The `run_screening()` function returns a dictionary with the following
top-level keys:

### `meta`

| Field | Type | Description |
|---|---|---|
| `toolkit` | string | Human-readable toolkit name and version |
| `methodology` | string | Methodology description |
| `generated_utc` | ISO 8601 string | UTC timestamp of the run |
| `config_schema_version` | string or null | `_schema_version` from the config |
| `nondetect_log_removal_target` | float | Default log-removal target |
| `provenance.soils_db_sha256` | string | Short SHA-256 of `data/soils.json` |
| `provenance.constituents_db_sha256` | string | Short SHA-256 of `data/constituents.json` |

### `site`

| Field | Type | Description |
|---|---|---|
| `site_id` | string | From config |
| `description` | string | From config |
| `soil_class` | string | USDA texture class |
| `hydraulic_gradient` | float | dh/dL |
| `treatment_type` | string | From config (metadata only) |
| `comparison_soil` | string or null | Comparison soil class |

### `darcy_site` / `darcy_comparison`

| Field | Type | Description |
|---|---|---|
| `q_m_per_day` | float | Darcy flux [m/day] |
| `vs_m_per_day` | float | Seepage velocity [m/day] |

### `receptor_results` / `comparison_results`

Array of receptor objects, each containing:

| Field | Type | Description |
|---|---|---|
| `receptor_name` | string | Receptor label |
| `distance_m` | float | Receptor distance [m] |
| `t_adv_days` | float | Unretarded advective travel time [days] |
| `constituents` | array | Per-constituent results (see below) |

Per-constituent fields:

| Field | Type | Description |
|---|---|---|
| `constituent` | string | Constituent name |
| `C0` | float | Source concentration |
| `unit` | string | Concentration unit |
| `K_oc_mL_per_g` | float | Organic-carbon partition coefficient |
| `K_d_mL_per_g` | float | Distribution coefficient |
| `R` | float | Retardation factor |
| `t_r_days` | float | Retarded travel time [days] |
| `lambda_per_day` | float | First-order decay constant [1/day] |
| `attenuation_factor` | float | C/C0 = exp(−λ·t_r) |
| `C_receptor` | float | Predicted receptor concentration |
| `limit` | float | Regulatory screening limit |
| `limit_is_nondetect` | boolean | True when limit == 0 |
| `log_removal` | float | log10(C0/C_receptor); inf when C_receptor underflows |
| `nondetect_log_removal_target` | float | Log-removal target for non-detect |
| `passes` | boolean | Screening pass/fail |

## Physics engine outputs (screening-2.0.0)

As of `screening-2.0.0`, all physics engine calls go through
`run_authorized_engine(name, authorization, **kwargs)`.  The return
type is engine-specific and documented in each engine module.

### `ogata_banks_1d` (version 1.0.0)

Returns a single `float`: the predicted receptor concentration C(x, t).
Units are the same as the caller-supplied `C0`.

See `core/physics_ogata_banks.py` for the full parameter description.

## Stability guarantee

Fields in this contract at the current `screening-result-1.0.0` version
will not be removed or renamed without a MAJOR bump.  New optional fields
may be added with a MINOR bump.

The methodology version (`screening-2.0.0`) is stamped into the `meta`
section of every result for auditability.
