# OSSF-GW-005: Governed Case History and Decision Ledger — Rebaselined Handoff

**Program:** OSSF groundwater screening (`ground-water-hydraulics-ossf`)  
**Status:** **AUTHORIZED FOR IMPLEMENTATION** (rebaselined after GW-003 + GW-004)  
**Rebaselined:** 2026-07-18  
**Prerequisite stack tip:** branch `cursor/ossf-gw-004-readiness-d9ac` (includes GW-003)  
**Prior status:** Review-only lock (plan `GW-005 Review Lock`); implementation was blocked until evidence + readiness digests existed in final governed form.

---

## 0. Mission

Add a governed case-history and decision-ledger subsystem that records the
evolution of an OSSF screening case as a sequence of immutable engineering
decisions — without persistence, collaboration, or user accounts.

```text
SiteCase (1.1.0)
    ↓
EvidenceValidationResult.evidence_digest     (GW-003)
    ↓
ReadinessAssessment.readiness_digest         (GW-004)
    ↓
ScreeningAuthorization (1.2.0)               (GW-001 + digests)
    ↓
Execution / attestation
    ↓
CaseHistory artifact                         (GW-005 — NEW)
    ↓
Final result JSON (compact history summary)
```

---

## 1. Prerequisite verification (repository-grounded)

| Prerequisite | Location | Binding surface for history |
|---|---|---|
| GW-001 Authorization | `core/authorization.py` | `authorization_id`, disposition |
| GW-002 SiteCaseV1 | `core/contracts/site_case_v1.py` | `site_case_hash(case)` → `case_hash` |
| GW-003 Evidence | `core/contracts/evidence_validation.py` | `EvidenceValidationResult.evidence_digest` |
| GW-004 Readiness | `core/readiness/assessment.py` | `ReadinessAssessment.readiness_digest` |
| Canonical hashing | `core/governance.sha256_of_json_stable` | 16-hex digests |
| Result contract | `core/result_contract.py` | additive `history` summary only |
| Driver | `simulate.py` | emit history after auth refusal / authorized run |

**Not available / must not invent:** database storage, project management, UI.

---

## 2. Locked decisions (ratified)

| ID | Ruling | Meaning |
|---|---|---|
| **1A** | Prerequisites first | Implementation authorized only after GW-003 + GW-004 exist (now satisfied on this stack) |
| **2C** | Single + append | Default one-revision history; optional `--prior-history` file-in append |
| **3B** | Emission | Emit on authorized pass/fail and authorization refusal; **not** on contract/evidence/readiness failures |
| **4A** | Executions distinct | `CaseHistory` has `revisions`, `decisions`, **and** `executions` |
| **5** | Separate enums | `HistoryEventType` ≠ `DecisionCategory` |
| **6C** | Split digests | `history_chain_digest` (content, no timestamps) vs `history_artifact_digest` (instance) |
| **7** | Compact result ref | Separate `output/<site_id>_history.json` + result `history` summary |
| **8** | Commits, no auto-PR | Five commits; present for review; **open PR only on explicit authorization** |

---

## 3. Emission policy (driver)

| Outcome | History artifact |
|---|---|
| Contract / schema failure | None |
| Evidence failure (GW-003) | Evidence-failure artifact only |
| Readiness `not_ready` (GW-004) | Readiness-failure artifact only |
| Authorization refused (preflight) | `CaseHistory` with refusal decision; `execution_count: 0` |
| Authorized pass / fail | `CaseHistory` with execution record |

Prior history input is an **explicit** CLI contract (`--prior-history path`).
The driver must never search for or overwrite history automatically.

---

## 4. Contracts (implementation target)

Package: `core/history/`

```python
@dataclass(frozen=True)
class CaseRevision:
    revision_number: int
    revision_id: str
    previous_revision_id: str | None
    case_hash: str
    evidence_digest: str
    readiness_digest: str | None
    authorization_id: str | None

@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    category: DecisionCategory   # evidence|assumption|readiness|authorization|execution|reporting
    summary: str
    timestamp: str               # factual; excluded from chain digest

@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    revision_id: str             # explicit revision reference (not nested-only)
    engine_name: str
    result_status: str           # pass|fail (authorized paths)
    result_artifact: str         # relative path binding
    report_artifact: str | None
    executed_utc: str            # factual; excluded from chain digest

@dataclass(frozen=True)
class CaseHistory:
    schema_version: str          # ossf-case-history-1.0.0
    revisions: tuple[CaseRevision, ...]
    decisions: tuple[DecisionRecord, ...]
    executions: tuple[ExecutionRecord, ...]
```

Enums (separate):

- `HistoryEventType` — what happened (`case_created`, `authorization_denied`, …)
- `DecisionCategory` — why a judgment was made

Digests:

- `history_chain_digest` — content-only chain identity
- `history_artifact_digest` — serialized instance (may include timestamps)

Result JSON summary (additive):

```json
{
  "history": {
    "schema_version": "ossf-case-history-1.0.0",
    "chain_digest": "<stable>",
    "artifact_digest": "<instance>",
    "revision_count": 1,
    "latest_revision_id": "<id>",
    "execution_count": 0,
    "history_artifact": "output/<site_id>_history.json"
  }
}
```

---

## 5. File plan

**Create:** `core/history/{__init__,history,events,serialization,errors}.py`,  
`schemas/ossf-case-history-1.0.0.schema.json`,  
`tests/test_case_history.py`, `tests/test_history_serialization.py`,  
`tests/test_history_digest.py`, `docs/adr/ADR-0008-case-history-decision-ledger.md`

**Modify:** `core/result_contract.py` (embed_history_summary), `simulate.py`  
(`--prior-history`, emit history on refusal + authorized paths), docs/GOVERNANCE.md

**Protected:** physics, SAD thresholds, evidence/readiness semantics (history records only).

---

## 6. Commit stack

```text
1. feat(history): add immutable history contracts
2. feat(history): add history serialization
3. feat(history): add revision chain validation
4. feat(results): emit governed history artifact
5. docs(history): document engineering decision ledger
```

After each: focused tests. After final: full suite green.  
**Do not open a PR until explicit owner authorization.**

---

## 7. Acceptance

Complete when:

- immutable history contracts exist and schema validates
- chain digest is deterministic; append-only chain enforced
- execution emits history on authorized + auth-refusal paths only
- result contract references history without embedding full chronology
- full test suite green
- reviewer can answer: *Can every governed screening execution now be traced through a deterministic, append-only engineering decision history without altering scientific or regulatory behavior?*

---

## 8. Authorization statement

> **Authorized:** Implementation of OSSF-GW-005 per this rebaselined handoff  
> on the GW-003+GW-004 stack, incorporating locked decisions  
> `1A 2C 3B 4A 5-separate 6C 7-confirmed 8-commits-no-auto-PR`.  
> Date: 2026-07-18  
> Baseline: `cursor/ossf-gw-004-readiness-d9ac` tip

*End of OSSF-GW-005 rebaselined handoff.*
