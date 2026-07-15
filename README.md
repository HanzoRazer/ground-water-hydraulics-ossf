# Groundwater Impact Screening — OSSF Waiver Support

A small, transparent Python + JSON system that produces the calculations
backing the standard waiver narrative:

> *"Groundwater movement beneath the site can be evaluated using Darcy's Law…
> the native soils exhibit relatively low to moderate K_sat … reduces the rate
> at which effluent can migrate … increasing contact time for natural
> attenuation … not anticipated to result in adverse impacts to groundwater
> quality, surrounding wells, or public health."*

Each clause in that narrative maps to a specific calculation here so the
statement is defensible rather than boilerplate.

## Layout

```
groundwater_sim/
├── README.md
├── data/
│   ├── soil_database.json     # K_sat, n, ρ_b for USDA texture classes
│   └── pathogens.json         # decay constants, K_d, regulatory limits
├── config/
│   └── site_example.json      # site-specific scenario template
├── core/
│   ├── darcy.py               # q = Ki, v = q/n, travel time
│   ├── transport.py           # retardation + first-order decay
│   └── attenuation.py         # narrative-clause attestation
├── simulate.py                # CLI entry point
└── output/                    # JSON results + text report
```

## Narrative-to-calculation map

| Narrative clause                                           | Calculation                                                |
| ---------------------------------------------------------- | ---------------------------------------------------------- |
| *"evaluated using Darcy's Law"*                            | `core/darcy.py` — `q = K · i`, `v = q/n_eff`               |
| *"low to moderate saturated hydraulic conductivity"*       | `data/soil_database.json` lookup + `classify_permeability` |
| *"reduces the rate at which effluent can migrate"*         | `FlowResult.travel_time_days(distance_m)`                  |
| *"increasing contact time for natural attenuation"*        | `transport.py` — solute travel time × first-order decay    |
| *"in contrast, highly permeable soils would allow…"*       | `comparison_scenarios` block in site config                |
| *"not anticipated to result in adverse impacts"*           | `passes_screening` boolean per constituent per receptor    |

## Run

```bash
cd groundwater_sim
python simulate.py config/site_example.json
```

This writes `output/<site_id>_results.json` (machine-readable, embeds into
report appendices) and `output/<site_id>_report.txt` (human-readable
screening summary).

## Customizing for a real site

1. Copy `config/site_example.json` to a new file, e.g. `config/smith_residence.json`
2. Set `subsurface.soil_type` to the soil class observed in the site evaluation
   (the keys in `data/soil_database.json`).
3. Set `subsurface.hydraulic_gradient` from piezometer or topographic data.
4. Add every receptor — wells, property lines, surface water — with measured
   distances in meters.
5. (Optional) Override source concentrations under `source.C0_overrides` if
   ATU manufacturer data differs from the post-disinfection defaults.

## What this is *not*

This is a screening / setback-justification tool. It is one-dimensional and
analytical. For the following you need a numerical model (MODFLOW + MT3DMS,
HYDRUS-1D, etc.):

- Heterogeneous or layered soils
- Transient flow / variable water-table elevation
- Vadose-zone transport (this assumes saturated, advection-dominated flow)
- Macropore / preferential flow

For a TCEQ Ch. 285 setback waiver supported by a properly-functioning aerobic
treatment unit with disinfection on low-K_sat native soils, the screening
model here is consistent with EPA Soil Screening Guidance (1996) and
typically suffices.

## Sources

- Carsel & Parrish (1988), *Water Resources Research* 24(5):755–769
- USEPA (1996), *Soil Screening Guidance: Technical Background Document*, EPA/540/R-95/128
- USEPA (2002), *Onsite Wastewater Treatment Systems Manual*, EPA/625/R-00/008
- Pang, L. (2009), *J. Environ. Qual.* 38:1531–1559
- 30 TAC Ch. 285 (Texas OSSF rules)
