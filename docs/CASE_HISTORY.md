# Case History (OSSF-GW-005)

Append-only, file-based chronology for an OSSF screening case.

History is **observational**: it records revisions, engineering decisions,
executions, and artifact lineage. It does not authorize, validate, or
interpret engineering data.

## Artifact

Default path:

```text
output/<site_id>_history.json
```

Schema version: `screening-case-history-1.0.0`  
JSON Schema: `schemas/case_history.schema.json`

## When history is emitted

| Pipeline outcome | History? | Execution records |
|------------------|----------|-------------------|
| Parse / contract failure | No | — |
| Evidence validation failure | No | — |
| Readiness `not_ready` | Yes | 0 |
| Authorization denied | Yes | 0 |
| Authorized pass / fail | Yes | 1 |

## Driver usage

```bash
# Standalone run → Revision 1
python simulate.py config/site_example.json

# Append Revision N+1
python simulate.py config/site_example.json \
  --prior-history output/EX-001_history.json
```

Malformed or incompatible `--prior-history` exits `1`, writes no new
artifacts, and leaves the prior file untouched.

## Result contract reference

Success, refusal, and readiness-failure JSON artifacts include:

```json
"history": {
  "schema_version": "screening-case-history-1.0.0",
  "history_id": "…",
  "chain_digest": "…",
  "artifact_digest": "…",
  "revision_count": 1,
  "latest_revision_id": "…",
  "execution_count": 1,
  "history_artifact": "output/<site_id>_history.json"
}
```

The full chronology lives only in the history file.

## Digests

- **`history_chain_digest`** — semantic chain identity (no timestamps).
- **`history_artifact_digest`** — exact emitted file instance (includes
  timestamps and relative artifact paths).
- **`result_digest`** (inside executions) — semantic screening result
  **before** the `history` summary is embedded (avoids digest cycles).

Upstream `evidence_digest` / `readiness_digest` values are recorded as
opaque governed inputs. GW-005 does not re-sort or reinterpret GW-003
evidence ordering.

## Package API

```python
from core.history import (
    build_history,
    append_revision,
    load_and_validate_history,
    write_history,
    compute_result_digest,
)
```

See ADR-0008 for architectural boundaries and locked design decisions.
