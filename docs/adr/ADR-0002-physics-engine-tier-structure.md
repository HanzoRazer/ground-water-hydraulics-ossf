# ADR-0002: Physics Engine Tier Structure

## Status

Accepted — screening-1.0.0

## Context

The tool's initial physics implementation was pure 1D advection with
first-order decay and linear-equilibrium retardation. This is the
simplest possible transport model. It is defensible as a *conservative*
screening approach (no dispersion means no dispersion-driven early
arrival of solute mass at the receptor), but it under-represents the
physics of real subsurface transport in one important way:

**Real plumes spread longitudinally.** Some solute mass travels faster
than the mean velocity, some slower. For a decaying species (which is
the entire point of the OSSF pathogen argument), the fast-moving fraction
spends less time attenuating and reaches the receptor at higher
concentration than pure advection predicts. A reviewer with any
subsurface transport background will notice this and may challenge the
conservatism claim.

Longitudinal dispersion is well-characterized analytically. The
Van Genuchten & Alves (1982) A1 solution to the 1D
advection-dispersion equation with decay and retardation is the
textbook result. Adding it to the tool is a modest lift with real
defensibility upside.

## Decision

The tool implements a **physics engine registry** in
`core/physics_registry.py`. Every physics engine registered there
must:

- be marked with `@methodology_attested(engine_name, engine_version)`
- expose an `evaluate(**kwargs)` callable with the standard signature
- have a documented sanity-limit test in `tests/` that pins its
  correctness against known analytical or numerical results
- be documented as an ADR (this file, and one per future engine)

### Engine tier

**Tier 1: `ogata_banks_1d` (screening-1.0.0 default).**
Van Genuchten & Alves (1982) A1 solution: 1D advection-dispersion
with first-order decay and linear retardation. Continuous source,
semi-infinite domain. Steady-state and transient forms both available.
Longitudinal dispersivity from EPA SSG default (α_L = 0.1 · L) or
Xu-Eckstein empirical fit. Scope: on-axis receptors, homogeneous
soils, steady flow.

**Tier 1 legacy: pure advection (`core/transport.py`).**
Retained in the codebase for regression comparison. Not registered
as an engine. In the low-dispersion limit, `ogata_banks_1d` reduces
to this legacy result exactly (see `tests/test_physics_ogata_banks.py`,
`test_low_dispersion_matches_pure_advection_with_decay`).

**Tier 2 planned: `domenico_3d`.**
Domenico (1987) analytical solution: 3D advection-dispersion with
transverse and longitudinal dispersion. Needed for off-axis receptors
where the assumption that flow is along the source-receptor line is
inappropriate. Deferred until there is a business case for off-axis
receptor evaluation and until the well-known approximation errors near
the source (Wexler 1992; Srinivasan et al. 2007) are documented and
bounded.

**Tier 3 planned: `hydrus_1d_wrapper`.**
Not an analytical engine but a wrapper that generates HYDRUS-1D input,
runs the executable, and parses results. Needed for vadose-zone
transport in layered soils. Deferred; escalation to HYDRUS is currently
handled outside the tool by the engineer of record.

## Consequences

**Positive.** The tool's default physics is now defensible against the
"where's your dispersion" review challenge. The registry pattern means
adding new engines is additive (no rewrite required). Every output
stamps which engine was used, so a submittal sealed today can be
exactly reproduced years later.

**Negative.** Dispersivity is now an input, and the input choice
(EPA SSG default vs. Xu-Eckstein) affects the answer. This is honest
about the physics but does not eliminate reviewer challenges — it moves
them from "why no dispersion?" to "why did you pick 10% of L instead of
Xu-Eckstein?". Both defaults are cited to primary sources in the
engine module and in the report.

**Neutral.** Domenico 3D is not yet needed because the current use case
is on-axis receptors (setback distance is the source-to-receptor
line). When off-axis receptors become material, we implement
`domenico_3d` and open ADR-000X.

## Sanity-limit tests

The following must pass for `ogata_banks_1d` to be considered valid:

1. Conservative tracer (λ = 0): C_ss = C₀ at every downgradient point.
2. Low-dispersion limit (D_L → 0): C_ss = C₀ · exp(-λ·R·x/v).
   **This is the fundamental correctness test.** If it fails, the
   engine is broken; do not use.
3. Dispersion increases receptor concentration relative to
   advection-only (for decaying species): the "why we added dispersion"
   test.
4. Monotonic decrease with distance for fixed physics.
5. `U ≥ v` by construction (mathematical identity).
6. Transient at t = 0 gives C = 0.
7. Transient at large t converges to steady-state within tolerance.

All tests live in `tests/test_physics_ogata_banks.py` and must pass
before any release.

## References

- Ogata, A. and Banks, R.B. (1961). A solution of the differential
  equation of longitudinal dispersion in porous media. USGS Professional
  Paper 411-A.
- Van Genuchten, M.Th. and Alves, W.J. (1982). Analytical solutions of
  the one-dimensional convective-dispersive solute transport equation.
  USDA Technical Bulletin 1661.
- Bear, J. (1972). *Dynamics of Fluids in Porous Media*, Ch. 10.
- Gelhar, L.W., Welty, C., and Rehfeldt, K.R. (1992). A critical review
  of data on field-scale dispersion in aquifers. *Water Resources
  Research* 28(7):1955–1974.
- Xu, M. and Eckstein, Y. (1995). Use of weighted least-squares method
  in evaluation of the relationship between dispersivity and field
  scale. *Ground Water* 33(6):905–908.
- USEPA (1996), *Soil Screening Guidance: Technical Background
  Document*, EPA/540/R-95/128.
