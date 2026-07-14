# Output Contract

This document describes the versioned output-schema contract for the
Groundwater Screening Toolkit.

Current output-contract version: **`output-1.0.0`** (see
`core.governance.OUTPUT_CONTRACT_VERSION`).

## Consumer guidance

Consumers of the toolkit should import from the public API surface:

- **Tier 1 / Tier 2 symbols** — import from `core` (e.g.,
  `from core import RunSession, evaluate_site`).  These symbols are committed
  to backward-compatibility across MINOR bumps.

- **Tier 3 symbols** — import from the specific submodule (e.g.,
  `from core.governance import sha256_of_file`).  These symbols are
  *reachable* but not part of the public contract; they may be refactored in
  any MINOR bump.

For the full three-tier model and the authoritative symbol list, see
`docs/adr/ADR-0007-public-api-surface.md`.

## Output schema fields

The top-level JSON results produced by `simulate.run_screening` include:

| Field | Type | Description |
|-------|------|-------------|
| `meta.toolkit` | string | Toolkit name and version |
| `meta.methodology` | string | Methodology description |
| `meta.generated_utc` | string | ISO-8601 UTC timestamp |
| `meta.config_schema_version` | string | Schema version from config |
| `meta.nondetect_log_removal_target` | number | Log-removal target for ND constituents |
| `meta.provenance.soils_db_sha256` | string | SHA-256 prefix of soils.json |
| `meta.provenance.constituents_db_sha256` | string | SHA-256 prefix of constituents.json |
| `site.*` | object | Site identification fields |
| `darcy_site.*` | object | Darcy flux and seepage velocity for site soil |
| `receptor_results[].constituents[].passes` | boolean | Screening pass/fail |
| `receptor_results[].constituents[].log_removal` | number | Achieved log-removal |

Any addition of new fields at any level is a MINOR bump.  Removal or rename of
an existing field at the top or second level is a MAJOR bump.
