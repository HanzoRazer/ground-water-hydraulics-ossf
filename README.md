# ground-water-hydraulics-ossf

> A governed screening tool for evaluating subsurface flow and contaminant
> attenuation at on-site sewage facility (OSSF) sites under TCEQ Ch. 285.
> Every output is preflight-gated, authorization-bound, methodology-attested,
> and version-stamped.

## What this is

A Python + JSON toolkit that turns the "Darcy's Law / native soils provide
attenuation" language commonly used in OSSF setback waiver requests into a
reproducible, defensible calculation. It runs five phases in strict order:

**0. Input contract.** Raw JSON is parsed into an immutable, unit-explicit,
schema-versioned `SiteCaseV1` and fully validated — structural, cross-field,
database-reference, and engine-compatibility — *before* preflight. Every
governed case declares `schema_version = "ossf-site-case-1.0.0"`; every
dimensional field carries its canonical unit in the name (`distance_m`,
`design_flow_gpd`, …); operational values are typed enums, so no decision
depends on free-form text. Malformed, ambiguous, or physically implausible
input is rejected here with actionable, field-pathed errors and never reaches
preflight, authorization, or physics. See
[`docs/SITE_CASE_V1.md`](docs/SITE_CASE_V1.md) and `docs/adr/ADR-0005`.

**1. Preflight.** Every site is evaluated against a versioned ruleset (Site
Appropriateness Determination, `sad-1.0.0`). Each of the seven rules cites a
regulatory authority and returns `proceed`, `warn`, or `refuse`; the worst
disposition wins. Triggers such as the Edwards Aquifer Recharge Zone, karst,
a water table below the 2-ft regulatory minimum, a receptor already inside
the required setback, or primary-only treatment produce `refuse`.

**2. Authorization.** The preflight determination is turned into an explicit
`ScreeningAuthorization` by `authorize_screening`. Only the **permitting**
dispositions — `proceed` and `warn` — are authorizable; a `refuse`
determination is **not authorizable** and raises `AuthorizationDeniedError`,
so no token exists and the physics engine has nothing to accept. The token is
bound to the exact site config it was minted from (canonical-JSON hash) and
is tamper-evident (findings digest + derived id recompute). There is no
override flag and no `--force`.

**3. Physics.** For authorized sites, a registered physics engine evaluates
every effluent constituent at every **active** receptor — but only through the single
execution boundary, `physics_registry.run_authorized_engine`, which
revalidates the authorization against the config before each dispatch. The
default engine is `ogata_banks_1d` (Van Genuchten & Alves 1982 solution A1):
1D advection-dispersion with linear-equilibrium retardation and first-order
decay, semi-infinite domain, continuous source.

**4. Attestation.** Every successful artifact carries a provenance stamp:
methodology version, preflight ruleset version and disposition, physics
engine name and version, SHA-256 hashes of the soil and pathogen databases,
the input schema version, the hash of the **normalized** site case, the
authorization id and schema version, the findings digest, warning/refusal
counts, and a UTC timestamp. A submittal sealed today is exactly reproducible
from source in five years.

## Governance in one paragraph

Scope refusal is enforced by **one** authority (see `docs/adr/ADR-0003`): the
authorization contract (`core/authorization.py`) plus the execution boundary
(`core/physics_registry.run_authorized_engine`). `get_engine` is
metadata-only and the engine's `evaluate` refuses to run without a permitting
token, so a refused site can never reach the physics — proven by the
engine-non-invocation test in `tests/test_end_to_end.py`. The earlier
`@screening_boundary` decorator was removed because it only permitted
`proceed` (wrongly blocking `warn`) and was a competing authority; the
refusal doctrine itself (`docs/adr/ADR-0001`) is unchanged.

## Layout

```
ground-water-hydraulics-ossf/
├── LICENSE                          # MIT
├── README.md                        # This file
├── simulate.py                      # Governed driver: parse -> preflight -> authorize -> physics -> attest
├── core/
│   ├── contracts/                   # SiteCaseV1 input contract (ADR-0005)
│   │   ├── site_case_v1.py          # Immutable typed records + local validation
│   │   ├── enums.py                 # Canonical operational enums
│   │   ├── errors.py                # Typed error hierarchy + ErrorCollector
│   │   ├── validation.py            # Cross-field / DB / engine-compat validation
│   │   ├── serialization.py         # Canonical parse / serialize / hash / schema
│   │   └── legacy.py                # Explicit pre-V1 -> V1 converter
│   ├── governance.py                # Attestation, @methodology_attested, version anchors
│   ├── preflight.py                 # SAD rules with regulatory citations (consume SiteCaseV1)
│   ├── authorization.py             # Authorization contract (token, minting, validation)
│   ├── physics_registry.py          # Canonical engine registry + run_authorized_engine boundary
│   ├── physics_ogata_banks.py       # Default engine (Van Genuchten & Alves A1)
│   ├── darcy.py                     # Darcy flux + seepage velocity primitives
│   ├── transport.py                 # Legacy pure-advection (regression reference)
│   └── attenuation.py               # Permeability classification helpers
├── schemas/
│   └── ossf-site-case-1.0.0.schema.json  # Authoritative SiteCaseV1 JSON Schema
├── data/
│   ├── soil_database.json           # USDA soil hydraulic properties
│   └── pathogens.json               # Decay constants + regulatory limits
├── config/
│   └── site_example.json            # Canonical EX-001 example (SiteCaseV1)
├── docs/
│   ├── GOVERNANCE.md                # Governance model overview
│   ├── SITE_CASE_V1.md              # Field-by-field input contract reference
│   └── adr/
│       ├── ADR-0001-screening-scope-and-refusal-doctrine.md
│       ├── ADR-0002-physics-engine-tier-structure.md
│       ├── ADR-0003-authorization-contract-and-execution-boundary.md
│       └── ADR-0005-versioned-site-case-input-contract.md
├── tests/
│   ├── test_site_case_v1.py         # Contract construction + local validation
│   ├── test_site_case_validation.py # Structural / cross-field / DB / compat validation
│   ├── test_site_case_serialization.py # Canonical serialization / hash / schema
│   ├── test_site_case_legacy.py     # Explicit legacy conversion + ambiguity refusal
│   ├── test_physics_ogata_banks.py  # Sanity-limit characterization tests
│   ├── test_authorization.py        # Authorization contract tests
│   ├── test_governed_execution.py   # Boundary + attestation regression
│   ├── test_end_to_end.py           # Driver V1 fixtures + engine non-invocation proof
│   ├── test_darcy.py / test_transport.py / test_attenuation.py
│   └── fixtures/                     # site_case_v1_{proceed,warn,refuse}.json + site_case_legacy.json
└── output/                          # Generated artifacts (gitignored)
```

(ADR-0004 is reserved for the future output/result-envelope contract.)

## Narrative-to-calculation map

Every clause of the standard waiver narrative points to a specific
calculation:

| Narrative clause | Where it lives |
|---|---|
| *"evaluated using Darcy's Law"* | `core/darcy.py` |
| *"low to moderate K_sat"* | `data/soil_database.json` + `classify_permeability` |
| *"reduces the rate at which effluent can migrate"* | seepage velocity in `core/darcy.py` |
| *"increasing contact time for natural attenuation"* | Ogata-Banks steady-state + retardation |
| *"in contrast, highly permeable soils would allow..."* | `reporting.comparison_soil_ids` in site config |
| *"not anticipated to result in adverse impacts"* | `passes_screening` per constituent per receptor |

## Run

```bash
python simulate.py config/site_example.json
```

The CLI form is unchanged. An unversioned config is auto-routed through the
explicit legacy converter (`core/contracts/legacy.py`), which refuses
ambiguous input rather than guessing.

### Python API migration (OSSF-GW-002)

PR #19 introduces a **breaking input boundary**: governed screening APIs now
require a validated `SiteCaseV1` instead of raw config dicts.

| Before | After |
|---|---|
| `evaluate_site(site_cfg, soils)` | `evaluate_site(case: SiteCaseV1)` |
| `authorize_screening(site_config, determination)` | `authorize_screening(case, determination)` |
| `validate_authorization(authorization, site_config)` | `validate_authorization(authorization, case)` |
| `run_authorized_engine(..., site_config, ...)` | `run_authorized_engine(..., case, ...)` |
| `physics_ogata_banks.evaluate(..., site_config=...)` | `... site_case=...` |

Load or construct cases via `core.contracts.load_site_case_json` (V1 JSON) or
`convert_legacy_site_config_to_v1` (unversioned legacy JSON). Contract
validation errors (`ContractValidationError`, `CrossFieldValidationError`,
`LegacyConfigError`, …) exit **before** preflight and are not SAD refusals.

Authorization and attestation hashes are bound to the **canonical serialized
SiteCaseV1**, not the raw input dict — previously known config hashes will
change even when scientific outputs are unchanged.

See [`docs/SITE_CASE_V1.md`](docs/SITE_CASE_V1.md) and
[`docs/adr/ADR-0005-versioned-site-case-input-contract.md`](docs/adr/ADR-0005-versioned-site-case-input-contract.md).

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Site authorized (proceed/warn); screening report produced |
| 1 | Input error: file not found / not JSON / invalid or unsupported `SiteCaseV1` contract |
| 2 | Site refused by preflight; authorization denied; refusal artifact produced |

Outputs are written to `output/<site_id>_results.json` (structured JSON,
embeds into report appendices) and `output/<site_id>_report.txt`
(human-readable). A successful run carries the `attestation` and
`authorization` blocks; a refusal carries `authorization: {authorized:
false, ...}` with the denial reason and the citing rules.

## Tests

```bash
python -m pytest tests/ -v
```

The characterization tests pin the physics engine's correctness against
known analytical limits. The most important is
`test_low_dispersion_matches_pure_advection_with_decay`, which verifies that
Ogata-Banks reduces to the pure-advection-with-decay result as dispersivity
approaches zero — if it fails, the engine is broken. The governance tests
prove the boundary cannot be crossed without a valid, config-bound
authorization, and that a refused site never invokes the physics engine.

## What this is NOT

This is a screening tool. It is one-dimensional, steady-state,
saturated-zone, homogeneous-soil. It is not a substitute for HYDRUS-1D,
MODFLOW + MT3DMS, or any other numerical model needed when:

- the soil profile is layered or strongly heterogeneous,
- vadose-zone transport governs the result,
- the water table is transient,
- preferential flow / macropores are likely,
- the site is in EARZ, karst, or on a fractured-rock aquifer.

Most of these are caught by the preflight and the tool refuses to run.
When in doubt, escalate.

## Sources

- Van Genuchten, M.Th. and Alves, W.J. (1982). Analytical solutions of
  the one-dimensional convective-dispersive solute transport equation.
  USDA Technical Bulletin 1661.
- Carsel, R.F. and Parrish, R.S. (1988). Developing joint probability
  distributions of soil water retention characteristics. *Water Resources
  Research* 24(5):755–769.
- USEPA (1996). *Soil Screening Guidance: Technical Background Document.*
  EPA/540/R-95/128.
- USEPA (2002). *Onsite Wastewater Treatment Systems Manual.*
  EPA/625/R-00/008.
- Pang, L. (2009). Microbial removal rates in subsurface media.
  *Journal of Environmental Quality* 38:1531–1559.
- 30 TAC Ch. 285 — Texas OSSF rules.

## Disclaimer

Screening tool. Results support — do not replace — the professional
engineering judgment of a licensed P.E. familiar with the specific site,
its soils, and the applicable regulatory framework. Use of this toolkit
does not constitute nor imply a regulatory determination by TCEQ or any
other authority.

## License

MIT — see `LICENSE`.
