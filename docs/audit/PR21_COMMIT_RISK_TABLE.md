# PR #21 — Commit-by-commit risk table

**Branch:** `release/reconcile-gw-stack`  
**Base:** `origin/main` @ `f84938d`  
**Audited tip at review:** `93b37b4` (plus follow-up fixes in this pass)  
**Method:** Inspect every commit message + `--stat`; spot-check high-risk diffs; compare physics/data tree to integration tip `1e80e6e`.

| # | Commit | Title | Risk | Key risks / notes |
|---|---|---|---|---|
| 1 | `94d7079` | chore: MIT / anonymize example / README intro | **High (docs)** | Introduced wrong `cd groundwater-screening-toolkit`; flattened README; LICENSE blanked copyright; example schema churn framed as “cleanup.” **Mitigated** in `93b37b4`. |
| 2 | `1b11a39` | feat(governance): authorization contract + baseline | **High** | Primary GW-001 surface: auth token, registry boundary, engine guard, attestation gate. Risk if dual authorities or bypasses remain. Covered by later harden + tests. |
| 3 | `a07f298` | feat(simulation): propagate authorization | **High** | Driver rewrite; refusal/success artifact shapes; exit codes. Predates ADR-0004 `status` adoption. |
| 4 | `6160688` | test(screening): proceed/warn/refuse coverage | **Low** | Strong governance regression suite; engine call-count + refuse=0. |
| 5 | `e71ca34` | docs(governance): ADR-0001/2/3 | **Low** | Documentation lock-in only. |
| 6 | `d388cfe` | fix(screening): setbacks + engine boundary | **Medium-High** | Correctness-critical setback fix; closes direct-evaluate bypass; gradient sign refusal. Behavior change vs soft warn. |
| 7 | `d95ecec` | feat(contracts): enums + errors | **Low** | Additive contract primitives; sticky public surface. |
| 8 | `dd6b0d7` | feat(contracts): SiteCaseV1 records | **Medium** | Load-bearing validation policy choices. |
| 9 | `2efcd1e` | feat(contracts): cross-field / DB validation | **Medium** | Fail-fast before preflight; operational rejection change. |
| 10 | `f0b1677` | feat(contracts): serialization + schema | **Medium-High** | Hash identity / canonicalization; schema↔parser dual SoT. |
| 11 | `26df419` | feat(migration): legacy converter | **Medium** | Narrow treatment map; intentional hard fail on ambiguity. |
| 12 | `1bf0904` | refactor(screening): consume SiteCaseV1 | **High** | Python API break (dict → SiteCaseV1) starts here. |
| 13 | `4f6f734` | feat(bootstrap): replay 481b754 foundation | **High (replay)** | Mid-stack overwrite of `simulate.py`, `darcy.py`, `README`, DBs. Ordering artifact of reconciliation; final physics/data match `1e80e6e`. Dropped `.code-workspace` (non-runtime). |
| 14 | `290f85f` | refactor(simulation): SiteCaseV1 driver | **High** | Full V1 execution path; fixture swap; expands API break. |
| 15 | `0fe18bc` | docs(contracts): publish SiteCaseV1 | **Low-Medium** | Docs/example lock-in; migration expectations. |
| 16 | `7d25720` | fix(contracts): harden after review | **Medium** | Active receptors, positive flow, legacy C0 basis, EX-001 pins. |
| 17 | `c375e35` | test(e2e): active-receptor call count | **Low** | PR #20 invariant; fixture-derived. |
| 18 | `17b9822` | docs(audit): GW-003 handoff | **Low** | Docs only; implementation not authorized. |
| 19 | `a41659b` | docs(audit): reconciliation inventory | **Low** | Process doc. |
| 20 | `ac56510` | test: remove flat screening tests | **Medium** | Necessary to retire dual-driver tests; coverage moves to GW e2e. |
| 21 | `93b37b4` | fix(release): user-facing breakage | **Medium** | Restores LICENSE/README; removes orphan flat modules; wires ADR-0004 into driver. |

## Cross-cutting findings from full-table pass

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| F1 | High (docs) | Wrong README `cd` path in `94d7079` | Fixed in `93b37b4` |
| F2 | Medium | Orphan flat-schema modules survived replay | Removed in `93b37b4` |
| F3 | Medium | ADR-0004 `status`/exit-3 not wired initially | Wired in `93b37b4` |
| F4 | Medium | No e2e covering authorized **fail** → exit `3` | **Fixed this pass** |
| F5 | Low | `warn` e2e allowed `status in (pass,fail)` while asserting exit 0 | **Tightened this pass** |
| F6 | Low | `result_contract` not exported from `core` package | **Fixed this pass** |
| F7 | Info | Physics/data vs `1e80e6e` identical | No change needed |
| F8 | Info | `authorization_id` binds config+ruleset+findings+schema (not disposition string); proceed/warn still diverge via findings digest | Accepted / documented |
| F9 | Low | `.code-workspace` dropped by bootstrap replay | Non-runtime; leave unless owner wants it restored |

## Release-gate snapshot after this pass

- Full suite green (see CI / local pytest)
- Physics/data unchanged vs audited integration tip
- EX-001 still exit 0 / `status: pass` with SAD-005 warn
- Refuse still exit 2 / `status: refused` / zero engine calls
