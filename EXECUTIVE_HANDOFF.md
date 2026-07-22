# Executive Handoff & Developer Onboarding

**Project:** `ground-water-hydraulics-ossf` — Governed OSSF Groundwater Screening Tool
**Document type:** Executive handoff + developer onboarding
**Prepared:** 2026-07-14
**Source of analysis:** `files - 2026-07-14T002532.309/` snapshot (14 files: core modules, tests, ADRs, governance docs, config, example outputs)
**Status:** Functional core; pre-integration. See [§7 Gaps & Risks](#7-gaps--risks) and [§8 Recommended Next Steps](#8-recommended-next-steps).

---

## 1. Executive Summary

`ground-water-hydraulics-ossf` is a Python + JSON toolkit that converts the standard *"Darcy's Law / native soils provide attenuation"* argument used in **Texas OSSF (on-site sewage facility) setback-waiver requests** into a **reproducible, defensible, version-stamped calculation** under **30 TAC Ch. 285**.

The product's differentiator is **governance, not physics**. The underlying transport math (1D advection-dispersion) is textbook. What makes this tool valuable to a licensed P.E. is that it:

- **Refuses to run** on sites where the screening physics is not defensible (karst, Edwards Aquifer Recharge Zone, water table too shallow, etc.) — eliminating the "silent overreach" liability where a tool emits a plausible-but-wrong number that gets sealed.
- **Stamps every output** with methodology version, ruleset version, engine version, input-database hashes, and a config hash — so a submittal sealed today is **exactly reproducible from source in five years**.
- **Pins correctness** to non-negotiable characterization tests derived from known analytical limits.

**Bottom line for decision-makers:** the tool is designed to reduce professional-liability risk and audit friction for setback-waiver submittals. It is a *screening* tool that supports — never replaces — P.E. judgment and numerical models (HYDRUS-1D, MODFLOW+MT3DMS).

---

## 2. What the Tool Does (Plain Language)

Given a site description (soil type, water-table depth, hydraulic gradient, effluent treatment class, and a list of receptors such as wells and property lines), the tool answers one question:

> *"At each receptor, will each contaminant of concern stay below its regulatory limit — and is this site even appropriate for a screening-level analysis at all?"*

It produces two artifacts per run:

- `output/<site_id>_results.json` — structured, machine-readable, embeds into report appendices.
- `output/<site_id>_report.txt` — human-readable, carries the attestation block.

Exit codes signal outcome for automation: **`0` = passed screening**, **`2` = refused by preflight**.

---

## 3. Architecture: The Three-Phase Pipeline

All execution flows through `simulate.py` in strict order. **Physics never runs before preflight clears the site.**

```
  Site config (JSON) + soil/pathogen databases
                     │
                     ▼
        ┌─────────────────────────┐
        │  1. PREFLIGHT (SAD)      │   preflight.py
        │  7 rules → proceed /     │   ruleset: sad-1.0.0
        │  warn / refuse           │
        └─────────────────────────┘
                     │
          refuse ────┴──── proceed / warn
             │                   │
             ▼                   ▼
     Refusal artifact   ┌─────────────────────────┐
     (exit 2)           │  2. PHYSICS             │   physics_ogata_banks.py
                        │  per constituent ×      │   engine: ogata_banks_1d v1.0.0
                        │  per receptor           │
                        └─────────────────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │  3. ATTESTATION         │   governance.py
                        │  version + hash stamp   │   methodology: screening-1.0.0
                        └─────────────────────────┘
                                     │
                                     ▼
                    output/<site_id>_results.json + _report.txt (exit 0)
```

### Phase 1 — Preflight / Site Appropriateness Determination (`preflight.py`)
Seven rules, each citing a specific regulatory authority, each returning `proceed` / `warn` / `refuse`. The **worst** disposition wins.

| Rule | Condition | Disposition |
|---|---|---|
| SAD-001 | Edwards Aquifer Recharge Zone | refuse |
| SAD-002 | Karst terrain | refuse |
| SAD-003 | Water table < 2 ft (refuse) / 2–4 ft (warn) | refuse / warn |
| SAD-004 | Soil = sand (refuse) / loamy_sand (warn) | refuse / warn |
| SAD-005 | Receptor below regulatory minimum setback / < 15 m | refuse / warn |
| SAD-006 | Gradient > 0.1 (refuse) / 0.05–0.1 / < 0.001 (warn) | refuse / warn |
| SAD-007 | Primary-only treatment (refuse) / no disinfection (warn) | refuse / warn |

Refusal is a **hard boundary** — there is no `--force` flag or override kwarg (see ADR-0001).

### Phase 2 — Physics (`physics_ogata_banks.py`, dispatched via `physics_registry.py`)
Default engine `ogata_banks_1d` implements the **Van Genuchten & Alves (1982) A1 solution**: 1D advection-dispersion with linear-equilibrium retardation and first-order decay, continuous source, semi-infinite domain. Steady-state form is the reported worst-case; a full transient form is also implemented. Longitudinal dispersivity is selectable (`epa_ssg` = 0.1·L, or `xu_eckstein` empirical fit).

Engines are looked up through a **registry** (`physics_registry.py`) — the single canonical authority for which engines exist, their versions, and their scope-of-applicability.

### Phase 3 — Attestation (`governance.py`)
Every artifact carries a provenance block: `methodology_version`, `preflight_ruleset_version`, `physics_engine` + version, SHA-256 short digests of the soil and pathogen databases, a canonical-JSON hash of the site config, and a UTC timestamp.

---

## 4. Governance Model (Why This Is More Than a Calculator)

The tool is governed at four layers — this is the core intellectual property and the reason it is trustworthy for sealed submittals:

1. **Architecture Decision Records (ADRs)** — every non-trivial decision is a numbered, immutable record under `docs/adr/`. Currently: ADR-0001 (refusal doctrine), ADR-0002 (engine tier structure).
2. **Decorators** (`governance.py`):
   - `@screening_boundary` — raises `ScreeningScopeError` if physics is invoked for a non-`proceed` site. No bypass.
   - `@methodology_attested(engine_name, engine_version)` — marks output as P.E.-sealable and carries engine identity into the stamp.
3. **Attestation** — the version + hash stamp on every artifact (see §3, Phase 3).
4. **Characterization tests** — non-negotiable sanity-limit tests; if they fail, the engine must not produce sealed output.

**Versions currently in force:** methodology `screening-1.0.0` · preflight `sad-1.0.0` · engine `ogata_banks_1d v1.0.0`.

---

## 5. Codebase Map

| Path | Responsibility |
|---|---|
| `simulate.py` | Governed driver: load → preflight → physics → attest → write JSON + text report. |
| `core/governance.py` | Version anchors, hash utilities, attestation dataclass, `@screening_boundary` / `@methodology_attested` decorators, `ScreeningScopeError`. |
| `core/preflight.py` | The 7 SAD rules, `RuleFinding` / `SiteAppropriatenessDetermination`, `evaluate_site()`. |
| `core/physics_ogata_banks.py` | Default engine: dispersivity, retardation, steady-state + transient concentration solvers. |
| `core/physics_registry.py` | Canonical engine registry; `get_engine()`, `list_engines()`, `DEFAULT_ENGINE`. |
| `core/darcy.py` | Darcy flux + seepage-velocity primitives, unit helpers (`evaluate_flow`, `m_per_s_to_cm_per_hr`). |
| `core/transport.py` | Legacy pure-advection engine, retained for regression reference (not registered). |
| `core/attenuation.py` | Permeability classification helpers (`classify_permeability`). |
| `data/soil_database.json` | USDA soil hydraulic properties. |
| `data/pathogens.json` | Constituent decay constants + regulatory limits. |
| `config/site_example.json` | Site-scenario template with narrative-to-field mapping. |
| `docs/GOVERNANCE.md` | Governance model + processes for adding engines / editing rules. |
| `docs/adr/ADR-0001…` | Screening scope & refusal doctrine. |
| `docs/adr/ADR-0002…` | Physics engine tier structure. |
| `tests/test_physics_ogata_banks.py` | 10 characterization tests pinning engine correctness. |
| `output/` | Generated artifacts (gitignored). |

---

## 6. How to Run & Test

**Run a screening:**
```bash
python simulate.py config/site_example.json
```
Writes to `output/<site_id>_results.json` and `output/<site_id>_report.txt`. Exit `0` = passed, `2` = refused.

**Run the correctness tests:**
```bash
python -m pytest tests/test_physics_ogata_banks.py -v
# or standalone:
python tests/test_physics_ogata_banks.py
```

**The one test that matters most:** `test_low_dispersion_matches_pure_advection_with_decay`. It verifies Ogata-Banks reduces to `exp(-λ·R·x/v)` as dispersivity → 0. If it fails, the engine is broken — do not produce sealed output.

**Worked examples (from the snapshot):**
- `EX-001` — a clay-loam site **passes**; all pathogens attenuate to effectively zero (e.g. E. coli `≈2.0e-312` vs. limit 126) well within limits; nitrate is flagged `REF-ONLY`.
- `EARZ-TEST` — a site in the Edwards Aquifer Recharge Zone is **refused** by SAD-001; physics never runs.

---

## 7. Gaps & Risks

These are the items a receiving developer must address before the snapshot is production-integrated.

| # | Item | Severity | Notes |
|---|---|---|---|
| 1 | **Snapshot is flattened.** The `files - 2026-07-14…` folder has no package structure. `physics_ogata_banks.py` and `physics_registry.py` use relative imports (`from .governance import …`). They **must** live inside `core/` to import correctly. | High | Blocks execution until placed. |
| 2 | **Cross-module dependencies not in snapshot.** The engine/driver reference `core/darcy.py`, `core/attenuation.py`, `core/transport.py`, and the two `data/*.json` databases. These exist in the repo but must be confirmed compatible with the snapshot versions. | High | Reconcile before running. |
| 3 | **`docs/` not physically present in repo root.** README references `docs/GOVERNANCE.md` and `docs/adr/`, but the repo tree does not yet contain a `docs/` directory. | Medium | Create `docs/` and `docs/adr/` on integration. |
| 4 | **GitHub remote / shell environment.** The local repo's `origin` remote was added by direct `.git/config` edit; a live `git fetch`/`push` has **not** been executed because the shell environment was unresponsive during handoff. | Medium | Verify remote sync with a working terminal. |
| 5 | **Dispersivity choice is a reviewer-exposed knob.** `epa_ssg` vs. `xu_eckstein` changes the answer (documented honestly in ADR-0002). | Low | Ensure the chosen method is cited in every sealed report. |
| 6 | **Single engine only.** Tiers 2 (`domenico_3d`, off-axis receptors) and 3 (`hydrus_1d_wrapper`, vadose/layered soils) are planned but not implemented. Off-axis receptor problems currently fall to escalation. | Low | Roadmap, not a blocker. |

---

## 8. Recommended Next Steps

1. **Integrate the snapshot into the package layout.** Move the four Python modules into `core/`, tests into `tests/`, ADRs into `docs/adr/`, governance doc into `docs/`, and reconcile `config/site_example.json`. Do a file-level diff against the versions already in the repo to identify intentional changes vs. drift.
2. **Establish a working shell + verify git remote.** Restart the terminal environment, then `git fetch origin`, set upstream tracking, and confirm the local `master` reconciles with `github.com/HanzoRazer/ground-water-hydraulics-ossf`.
3. **Run the full test suite green** before any release, treating `test_low_dispersion_matches_pure_advection_with_decay` as a release gate.
4. **Package hygiene.** Confirm `pyproject.toml` declares the `core` package and any dependencies; add CI to run the characterization tests on every push.
5. **Governance discipline going forward.** Any new physics engine or ruleset change must (a) bump the relevant version anchor in `governance.py`, (b) add/extend characterization tests, and (c) open or update an ADR — per the documented process in `docs/GOVERNANCE.md`.

---

## 9. Scope Boundaries (State Explicitly in Any Submittal)

This is a **1D, steady-state, saturated-zone, homogeneous-soil screening tool.** It is **not** a substitute for HYDRUS-1D or MODFLOW+MT3DMS when the soil profile is layered/heterogeneous, vadose-zone transport governs, the water table is transient, preferential flow is likely, or the site is in EARZ/karst/fractured rock. Most of these are caught by the preflight and refused. **When in doubt, escalate.** Results support — do not replace — the professional judgment of a licensed P.E., and do not constitute a regulatory determination by TCEQ.

---

## 10. Key References

- Van Genuchten, M.Th. & Alves, W.J. (1982). *Analytical solutions of the one-dimensional convective-dispersive solute transport equation.* USDA Tech. Bulletin 1661. (Solution A1 — the default engine.)
- Ogata, A. & Banks, R.B. (1961). USGS Professional Paper 411-A.
- USEPA (1996). *Soil Screening Guidance: Technical Background Document.* EPA/540/R-95/128.
- USEPA (2002). *Onsite Wastewater Treatment Systems Manual.* EPA/625/R-00/008.
- Xu, M. & Eckstein, Y. (1995). *Ground Water* 33(6):905–908. (Alternate dispersivity fit.)
- 30 TAC Ch. 285 — Texas OSSF rules (§285.30, .32, .33, .40–42, .91).
- Internal: `docs/adr/ADR-0001`, `docs/adr/ADR-0002`, `docs/GOVERNANCE.md`.

---

*Disclaimer: This handoff document describes a screening tool. Its outputs support, and do not replace, the professional engineering judgment of a licensed P.E. familiar with the specific site. Use of this toolkit does not constitute nor imply a regulatory determination by TCEQ or any other authority.*
