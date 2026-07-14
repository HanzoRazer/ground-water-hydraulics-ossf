# ADR-0004: Output artifact & exit-code contract

- **Status:** Accepted
- **Date:** 2026-07-14
- **Supersedes / clarifies:** the ad-hoc output fields introduced independently
  by the flat toolkit driver and the governed OSSF-GW-001 driver.

## Context

Two drivers emit screening artifacts and CLI exit codes:

- the **flat toolkit** (`main`) — a direct 1-D screening calculation, and
- the **governed OSSF-GW-001 pipeline** — preflight → authorization → physics
  → attestation.

They evolved a **namespace collision**. Both used the words `authorized` /
`refused` and both overloaded exit code `2`, but with different meanings:

| | Toolkit (pre-ADR) | Governed pipeline (pre-ADR) |
|---|---|---|
| `refused` means | a constituent exceeded its limit | preflight denied the run; physics never ran |
| exit `2` means | criteria not met | preflight refusal |
| `authorized` means | all constituents passed | preflight permitted execution |

A run has **two orthogonal facts**: *was it authorized to run?* and *did the
results meet the criteria?* Conflating them into one word and one exit code
makes `refused` and exit `2` ambiguous, and guarantees a conflict if both
drivers land on `main`.

Neither driver's output contract has shipped to a released consumer yet, so the
cost of fixing this is lowest **now**, before either PR merges.

## Decision

### 1. One non-colliding, artifact-level `status`

Every written artifact carries a top-level `status` with exactly one of:

| `status` | Meaning |
|---|---|
| `pass` | authorized run; every gating criterion met |
| `fail` | authorized run; one or more criteria not met (outputs still written) |
| `refused` | authorization/preflight denied; physics never ran |

`authorized` is **not** a `status` value. The authorization *decision*
(`proceed` / `warn` / `refuse`, ids, hashes) remains in the governed pipeline's
`authorization` block as metadata. This keeps `refused` meaning exactly one
thing.

An **errored** run (bad input, validation failure, unexpected exception) writes
no artifact and therefore has no `status`; it is signalled only by the exit
code.

### 2. Exit-code taxonomy

| Code | Name | Meaning |
|---|---|---|
| `0` | pass | authorized; all criteria met |
| `1` | error | input/validation/unexpected failure; no usable artifact |
| `2` | refused | authorization/preflight denied; physics did not run |
| `3` | fail | authorized; screening ran but one or more criteria not met |

Note: `argparse` emits exit `2` for CLI usage errors, so `2` is not *uniquely*
the refused outcome at the process level — consumers that must distinguish
should read the JSON `status`.

### 3. Single source of truth

`core/result_contract.py` owns `RESULT_SCHEMA_VERSION`, the `status`
constants, the exit-code constants, and the helpers `resolve_status(...)` and
`exit_code_for(...)`. **Both drivers import from it**; neither hard-codes these
values. This is the structural guard against the collision reappearing.

### 4. Schema version

`RESULT_SCHEMA_VERSION = "screening-result-2.0"`. The major bump reflects the
renamed/relocated discriminator relative to the unreleased `-1.0` field set.

## Consequences

- The flat toolkit stops using `authorized`/`refused`; an all-pass run is
  `status: pass` (exit `0`), an exceedance is `status: fail` (exit `3`). It
  never emits `refused` (it has no preflight) but the value is reserved.
- The governed pipeline derives top-level `status` from its per-constituent
  results (informational/reference-only constituents such as nitrate, whose
  `passes` is `None`, are **non-gating** and do not force `fail`), emits
  `refused` + exit `2` on preflight refusal, and `fail` + exit `3` on an
  authorized run with an exceedance.
- **Breaking (pre-release):** the toolkit's failing-run exit code moves from
  `0` to `3`; the `-1.0` `status` values (`authorized`/`refused`) are replaced.

## Migration / sequencing

1. Land this ADR + `core/result_contract.py` + its test on `main` (this PR).
2. Rebase the toolkit output-contract PR onto it; adopt the shared constants.
3. Rebase the governed OSSF-GW-001 PR onto it; adopt the shared constants and
   emit top-level `status`.
4. Follow-up: converge the two drivers (or make the toolkit a thin front-end
   over the governed pipeline) so the output logic is not duplicated.
