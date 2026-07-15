# ADR-0001: Screening Scope and Refusal Doctrine

## Status

Accepted — sad-1.0.0

> **Amended by ADR-0003 (screening-authorization-1.0.0).** The refusal
> *doctrine* below is unchanged and remains in force. The enforcement
> *mechanism* originally described here — the `@screening_boundary`
> decorator and `ScreeningScopeError` in `core/governance.py` — has been
> superseded by the **authorization contract** (`core/authorization.py`)
> and the **execution boundary** (`core/physics_registry.run_authorized_engine`).
> The decorator only permitted `proceed` (it would have wrongly blocked the
> permitted `warn` disposition) and constituted a second, competing
> authority. Where the text below says enforcement is "via the
> `@screening_boundary` decorator", read it as "via the authorization
> contract and registry boundary" per ADR-0003. There is still no override.

## Context

The tool produces P.E.-sealable calculations backing OSSF setback waiver
requests. Its physics engine (analytical 1D advection-dispersion with
decay and retardation) is defensible only within a bounded envelope of
site conditions. Outside that envelope — Edwards Aquifer Recharge Zone,
karst terrain, very shallow water table, pure sand, receptor already
inside a regulatory minimum setback, extreme hydraulic gradients — the
tool's output is either meaningless, misleading, or both.

The failure mode this ADR governs is *silent overreach*: the tool
produces a plausible-looking number for a site where the underlying
physics does not apply, and the engineer of record seals it because the
tool did not object.

## Decision

The tool implements a **preflight Site Appropriateness Determination
(SAD)** that runs before any physics is dispatched. The SAD returns one
of three dispositions:

- `proceed` — screening physics may run
- `warn` — physics runs; report carries a prominent caveat with the
  triggering rule and its regulatory authority
- `refuse` — physics **must not run**. The tool produces a documented
  refusal artifact instead of a screening result.

Refusal is a hard boundary. It is enforced in code via the
`@screening_boundary` decorator in `core/governance.py`, which raises
`ScreeningScopeError` if a physics function is called for a refused
site. There is no override flag, no `--force` bypass, no `if_you_are_sure`
kwarg. If the tool refuses, the engineer of record escalates to a
numerical model or to the WPAP process, or amends the site config to
correct the triggering condition (if the triggering condition was a
data-entry error).

The SAD ruleset is versioned: `PREFLIGHT_RULESET_VERSION` is stamped
into every output artifact. Adding, removing, or modifying a rule
increments the version and requires an ADR update.

## Consequences

**Positive.** The tool cannot silently overreach. Every refusal is
documented with a regulatory citation. Version-stamped rulesets mean
every historical output can be reproduced against the exact rules that
were in force at the time of sealing.

**Negative.** Some sites that a numerical model could handle
successfully will be refused because they fall outside the screening
envelope. This is the correct tradeoff for a screening tool but adds
friction — sites that could have been handled with a screening
justification now require escalation to HYDRUS-1D or MODFLOW.

**Neutral.** The ruleset will need periodic revision as Ch. 285 is
amended and as EPA guidance evolves. This is expected and healthy.

## Rules in sad-1.0.0

- SAD-001: Edwards Aquifer Recharge Zone → refuse
- SAD-002: Karst terrain → refuse
- SAD-003: Water table depth (< 2 ft refuse; 2–4 ft warn)
- SAD-004: Soil class (sand refuse; loamy_sand warn)
- SAD-005: Receptor distance (below regulatory minimum refuse;
  < 15 m warn)
- SAD-006: Hydraulic gradient (> 0.1 refuse; 0.05–0.1 warn;
  < 0.001 warn)
- SAD-007: Treatment class (primary-only refuse; unspecified
  disinfection warn)

Each rule cites its regulatory authority in the code and in its
`RuleFinding.authority` field.

## References

- 30 TAC Ch. 285 (OSSF rules), particularly §285.30, §285.32,
  §285.33, §285.40–42, §285.91
- USEPA (1996), Soil Screening Guidance: Technical Background
  Document, EPA/540/R-95/128
- Bear, J. (1972), *Dynamics of Fluids in Porous Media*, Ch. 10
