# Release reconciliation commit inventory

**Base:** `origin/main` @ `f84938d`  
**Source integration tip:** `1e80e6e` (`feat/ossf-gw-001-governed-authorization`)  
**Reconciliation branch:** `release/reconcile-gw-stack`

| Commit | Classification | Replay? |
|---|---|---|
| `481b754` | Bootstrap/snapshot — governed toolkit foundation (attenuation, darcy, transport, DBs, pyproject) | Yes — selective; `main` lacks this subsystem layout |
| `1ab17e6` | Bootstrap/chore — MIT license, anonymized example, README | Yes — merge with `main` README/LICENSE |
| `3eb8a3c` | **GW-001** — authorization contract + governed baseline | Yes |
| `f8ce430` | **GW-001** — authorization through governed artifacts | Yes |
| `e13150a` | **GW-001** — proceed/warn/refuse workflow tests | Yes |
| `9819a55` | **GW-001** — ADR-0003 documentation | Yes |
| `5d45943` | **GW-001** — setback fix + engine boundary hardening | Yes |
| `5746c4f` | **GW-002** — contract enums and errors | Yes |
| `0677bff` | **GW-002** — SiteCaseV1 domain contract | Yes |
| `c0fd5d4` | **GW-002** — cross-field validation | Yes |
| `523e161` | **GW-002** — serialization + JSON Schema | Yes |
| `36199c5` | **GW-002** — legacy migration | Yes |
| `6b3d8a3` | **GW-002** — preflight/auth consume SiteCaseV1 | Yes |
| `13efcc1` | **GW-002** — simulation driver integration | Yes |
| `ef68b4e` | **GW-002** — contract documentation | Yes |
| `ce24ccd` | **GW-002** — review-risk hardening | Yes |
| `1a6bc43` | Merge commit (PR #19) | **No** — replay constituents only |
| `1d79473` | **PR #20** — active-receptor e2e call-count invariant | Yes |
| `02915a9` | Merge commit (PR #20) | **No** |
| `1e80e6e` | **GW-003** — handoff documentation only | Yes |

**Excluded from replay:** merge commits; unrelated integration-root-only artifacts not required on `main` (`ground-water-hydraulics-ossf.code-workspace` unless needed).

**Conflict policy:** `main` owns repo identity; GW audited implementation owns governed screening subsystem files.

For a full commit-by-commit risk table of the PR #21 stack, see
[`PR21_COMMIT_RISK_TABLE.md`](PR21_COMMIT_RISK_TABLE.md).

## Post-replay cleanup (user-facing breakage)

After replay, orphaned flat-toolkit modules that still documented the pre-V1
schema were removed so they cannot be mistaken for the live contract:

* removed: `core/validation.py`, `core/report.py`, `tests/test_validation.py`,
  `data/soils.json`, `data/constituents.json`
* retained & wired: `core/result_contract.py` + ADR-0004 (governed driver now
  emits top-level `schema_version` / `status`)
* LICENSE copyright restored to `Ross Echols` (authoritative line from
  `origin/main`)
* README: correct `cd ground-water-hydraulics-ossf`, SiteCaseV1 migration map,
  EX-001 expected warn + ADR-0004 exit taxonomy
