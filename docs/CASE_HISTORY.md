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

History is **always** written under the driver's `DEFAULT_OUTPUT_DIR`
(`output/`), even when `--output` / `--text` redirect the result JSON or text
report to another directory. There is no separate history-output CLI option.
Embedded `history.history_artifact` therefore points at the default history
path, which may differ from the directory of a custom `--output` file.

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

## Generated artifact bindings

`ExecutionRecord.generated_artifacts` binds **only final, immutable on-disk
bytes** that an auditor can re-hash after the run completes.

| Artifact | Bound? | Why |
|----------|--------|-----|
| `report_text` | Yes | Written once; never receives the embedded `history` block |
| `result_json` | **No** | Receives the embedded `history` summary; binding its bytes would create a digest cycle (recorded sha256 ≠ final on-disk file) |
| History file | **No** | Would create a self-reference cycle in chain/artifact digests |

Result identity is carried by `ExecutionOutcome.result_digest` (semantic
payload **before** the `history` block is embedded), not by hashing
`result_json` file bytes.

Readiness `not_ready` and authorization-denied revisions create **no**
`ExecutionRecord`, so they carry no `generated_artifacts`.

### Write sequencing note

The driver writes history, embeds the history reference into the JSON
artifact, then writes that JSON. If the final JSON write fails after a
successful history write, a new history revision can exist without a
matching result/refusal/readiness JSON. Cross-file atomicity is not
guaranteed in GW-005 v1.

## Artifact path representation (`ArtifactBinding.relative_path`)

Recorded paths are **provenance labels**, not filesystem access grants.

| Location | Recorded form |
|----------|---------------|
| Inside the repository | Repository-relative path (e.g. `output/site_report.txt`) |
| Outside the repository | `external/<normalized location components>` |

Examples:

```text
/tmp/run-a/report.txt
→ external/tmp/run-a/report.txt

C:\runs\a\report.txt
→ external/C/runs/a/report.txt

\\server\share\runs\a\report.txt
→ external/UNC/server/share/runs/a/report.txt
```

Content integrity remains `ArtifactBinding.sha256`. The result-summary field
`history.history_artifact` is a separate repository-relative pointer to the
history file and does **not** use the `external/` representation.

> `relative_path` is a recorded provenance label — not a filesystem path to
> open or join onto a root. Content integrity is `sha256`. Out-of-repo labels
> use `external/...` (older histories may still have basename-only forms).

Traversal rejection for externally authored history strings is **not**
implemented here (see GW-005-P1).

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
