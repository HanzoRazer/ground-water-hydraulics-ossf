# Groundwater Screening Toolkit

> A transparent, P.E.-authored screening tool for evaluating subsurface flow
> and contaminant attenuation at on-site sewage facility (OSSF) sites.

[![Status](https://img.shields.io/badge/status-screening--tool-blue)]()
[![Methodology](https://img.shields.io/badge/methodology-screening--3.0.0-green)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

---

## What this is

A small Python + JSON toolkit that turns the boilerplate "Darcy's Law / native
soils provide attenuation" language found in OSSF setback waiver requests
into a defensible, reproducible calculation. It maps every clause of the
standard waiver narrative to an explicit equation, soil property, or
constituent decay constant — so the engineering statement is backed by
numbers an outside reviewer can re-run, not just paragraphs of prose.

The toolkit is intentionally lightweight. It uses the analytical screening
framework consistent with EPA's *Soil Screening Guidance* (1996), draws soil
hydraulic properties from Carsel & Parrish (1988), and pulls pathogen decay
constants from peer-reviewed compilations. For a typical Ch. 285 OSSF waiver
on low-permeability native soils with secondary aerobic treatment plus
disinfection, this screening level is sufficient to produce a defensible
"no adverse impact" demonstration.

## What it does

Given a site configuration (soil class, hydraulic gradient, receptor
distances, treatment type), the toolkit computes:

- Darcy flux and seepage velocity through the native soil profile
- Advective travel time from the disposal area to each receptor (wells,
  property lines, surface water)
- Linear-equilibrium retardation factors for each effluent constituent
- First-order decay over the solute travel time
- Receptor concentrations vs. regulatory screening limits
- A side-by-side comparison against higher-permeability soils to back the
  "in contrast, highly permeable soils would allow more rapid transport"
  clause

Output is a structured JSON results file plus a human-readable text report
suitable for inclusion in a TCEQ submittal or engineering report appendix.

The toolkit is governed: every screening run requires a site appropriateness
determination (preflight), a signed authorization token, and a `RunSession`
scope. The physics engine is never invoked without a valid, live session.
See `docs/OUTPUT_CONTRACT.md` for the full output contract
and `docs/adr/ADR-0006-run-session-scoped-authorization.md` for the
authorization design.

## What it is not

This is a screening tool, not a numerical groundwater model. It is one-
dimensional, steady-state, saturated-zone, homogeneous-soil. It does not
substitute for HYDRUS-1D, MODFLOW + MT3DMS, or any other tool needed when:

- the soil profile is layered or strongly heterogeneous,
- vadose-zone transport governs the result,
- the water table is transient,
- preferential flow / macropores are likely,
- the receptor pathway involves surface-water mixing rather than direct
  groundwater advection.

When in doubt, escalate.

## Quick start

```bash
git clone https://github.com/HanzoRazer/ground-water-hydraulics-ossf.git
cd ground-water-hydraulics-ossf
python simulate.py config/site_example.json
```

Outputs are written to `output/<site_id>_results.json` and
`output/<site_id>_report.txt`.

To evaluate a real site: copy `config/site_example.json`, set the observed
soil class, gradient, and measured receptor distances, then point `simulate.py`
at the new file.

The CLI exits `0` on success and `1` with a message on any input problem
(missing/malformed JSON, or a configuration that fails validation).

## Input validation & screening policy

Two safeguards guard against the most common ways a screening tool can produce
a confident-looking but wrong answer:

- **Config validation** (`core/validation.py`). Before any calculation runs,
  the site configuration is validated in a single pass: required fields,
  types, finite/positive numeric ranges, known soil class and constituent
  names, unique receptor and constituent names, and structurally valid
  receptor objects. Effluent-concentration overrides must be supplied in the
  same unit the constituent database uses — **the tool performs no unit
  conversion and rejects a mismatched `unit` label** rather than silently
  trusting the number. All problems are reported together with a field path.

- **Non-detect pass/fail policy** (`core/transport.py`). For constituents with
  a positive limit, pass means `C_receptor <= limit`. For non-detect targets
  (limit `0`, e.g. pathogens), pass is judged against a documented
  **log-removal target** (default 4-log, per the USEPA GWUDI benchmark), not
  exact-zero float equality. A modeled concentration that underflows to zero is
  reported as being below the *computational floor* — explicitly a screening
  artifact, not a measured absence. A constituent may override the default via
  a `nondetect_log_removal_target` field in `data/constituents.json`.

Each run also stamps the SHA-256 of the soil and constituent databases and the
config schema version into the results, so a report can be reproduced and
audited even if the databases are later edited.

## Running the tests

```bash
pip install pytest
python -m pytest
```

The suite covers Darcy/seepage math, retardation and travel time, attenuation
overflow/underflow behavior, the non-detect log-removal policy, configuration
validation, and an end-to-end run (with provenance and report checks) against
`config/site_example.json`.

## Project layout

```
.
├── data/        # Soil hydraulic property database + constituent decay constants
├── config/      # Site-specific scenario inputs
├── core/        # Darcy + transport + validation + report modules
├── tests/       # pytest unit + integration suite
├── output/      # Generated reports and JSON result files
└── simulate.py  # CLI entry point
```

### Key config fields (`config/site_example.json`)

| Field | Description |
|---|---|
| `soil_class` | USDA texture class (must match a key in `data/soils.json`) |
| `hydraulic_gradient` | Measured or estimated dh/dL [dimensionless] |
| `receptors` | List of `{name, distance_m}` objects |
| `constituents` | Subset of keys from `data/constituents.json` |
| `comparison_soil` | High-permeability reference soil for the contrast section |
| `effluent_concentrations` | Override default C₀ values per constituent (any `unit` must match the constituent database's `limit_unit`) |

## Sources

- Carsel, R.F. & Parrish, R.S. (1988). Developing joint probability
  distributions of soil water retention characteristics. *Water Resources
  Research* 24(5):755–769.
- USEPA (1996). *Soil Screening Guidance: Technical Background Document.*
  EPA/540/R-95/128.
- USEPA (2002). *Onsite Wastewater Treatment Systems Manual.*
  EPA/625/R-00/008.
- Pang, L. (2009). Microbial removal rates in subsurface media estimated
  from published studies. *Journal of Environmental Quality* 38:1531–1559.
- 30 TAC Ch. 285 — Texas OSSF rules.

## Disclaimer

This software is provided as a technical screening aid. Results are
intended to support — not replace — the professional engineering judgment
of a licensed P.E. familiar with the specific site, its soils, and the
applicable regulatory framework. Use of this toolkit does not constitute
nor imply a regulatory determination by TCEQ or any other authority.

## License

MIT — see `LICENSE`.
