# Output Contract — screening-3.0.0

This document specifies the public output contract for the OSSF Groundwater
Screening Toolkit. Changes to this contract require a MAJOR version bump to
`METHODOLOGY_VERSION`.

---

## Version

`METHODOLOGY_VERSION = "screening-3.0.0"` (as of this document).

---

## Screening run pipeline

Execution of a site screening follows this pipeline:

1. **Load** site config JSON and databases (soils, constituents).
2. **Validate config** (`core/validation.py`) — structural and cross-field
   validation. Raises `ConfigValidationError` (all problems reported
   together) if any field is missing, malformed, or out of range.
3. **Preflight** (`core/preflight.py`) — Site Appropriateness Determination.
   Emits `proceed`, `warn`, or `refuse` based on regulatory and
   methodological rules (SAD ruleset `sad-1.0.0`).
4. **Authorize** (`core/authorization.py`) — mint a `ScreeningAuthorization`
   from the proceed/warn determination. Refused sites raise
   `AuthorizationDeniedError`; no token is produced.
5. **RunSession** (`core/run_session.py`) — validate the authorization
   exactly once, yield a `SessionScopedExecutor`.
6. **Physics** (`core/physics_registry.run_authorized_engine`) — run the
   engine for each (receptor, constituent) pair inside the `RunSession`
   context block.
7. **Output** — structured JSON results + human-readable text report.

---

## Entry-point signature change (breaking, screening-3.0.0)

`AbstractPhysicsEngine.run()` and `run_authorized_engine()` now require a
`SessionScopedExecutor` (obtained from `RunSession.__enter__`), not a raw
`ScreeningAuthorization`. Passing a raw authorization raises `TypeError`.

**Before (screening-2.x):**
```python
result = run_authorized_engine(
    engine_name, site_config, authorization, engine_inputs
)
```

**After (screening-3.0.0):**
```python
with RunSession(authorization, site_config, soils_db, constituents_db) as executor:
    result = run_authorized_engine(engine_name, executor, **engine_inputs)
```

---

## Authorization contract

A `ScreeningAuthorization` token:
- is minted by `authorize_screening(site_config, sad)` from a
  `proceed` or `warn` preflight determination only;
- carries the SHA-256 hash of the canonical JSON of the site config
  (`site_config_hash`), a `findings_digest`, and an `authorization_id`
  that deterministically binds all three;
- is validated exactly once per run by `RunSession.__enter__`
  (schema version, config-binding, tamper detection, disposition check).

---

## Per-call authorization guard

`SessionScopedExecutor.authorize_call()` is called by every engine
invocation. It performs an O(1) set membership check (`_token in
_LIVE_SESSIONS`) and raises `SessionExpiredError` if the session has exited
or the executor was constructed outside a live session.

---

## JSON output fields

| Field | Description |
|---|---|
| `meta.methodology_version` | `screening-3.0.0` |
| `meta.generated_utc` | ISO-8601 timestamp (UTC) |
| `meta.config_schema_version` | Site config schema version |
| `meta.provenance.soils_db_sha256` | 16-hex SHA-256 of `data/soils.json` |
| `meta.provenance.constituents_db_sha256` | 16-hex SHA-256 of `data/constituents.json` |
| `site.*` | Site metadata from config |
| `receptor_results[].receptor_name` | Receptor name |
| `receptor_results[].distance_m` | Receptor distance [m] |
| `receptor_results[].t_adv_days` | Advective travel time [days] |
| `receptor_results[].constituents[].passes` | `true` / `false` screening outcome |
| `receptor_results[].constituents[].C_receptor` | Modeled receptor concentration |
| `receptor_results[].constituents[].limit` | Regulatory screening limit |

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Run completed successfully |
| `1` | Input error (config validation failure, file not found, etc.) |

---

## Breaking changes log

| Version | Change |
|---|---|
| `screening-3.0.0` | `run()` / `run_authorized_engine()` require `SessionScopedExecutor`; full validation moved to `RunSession.__enter__` (once per run) |
| `screening-2.0.0` | `AbstractPhysicsEngine` base class; `EngineMetadata` return type for `get_engine()` |
| `screening-1.0.0` | Initial governed-screening release |

---

## Known limitations

- Session scope is single-process only. `SessionScopedExecutor` instances
  must not be shared across process boundaries (see ADR-0006).
- The screening model is 1D, steady-state, saturated-zone, homogeneous-
  soil. See `docs/adr/ADR-0006-run-session-scoped-authorization.md` and
  README for scope limitations.
