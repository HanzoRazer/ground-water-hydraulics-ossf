# OSSF-GW-004: Practitioner Readiness Workflow — Implemented Handoff

**Program:** OSSF groundwater screening (`ground-water-hydraulics-ossf`)  
**Status:** **IMPLEMENTED** — readiness gate wired on
  `cursor/ossf-gw-004-readiness-d9ac`  
  (readiness `screening-readiness-1.0.0`, auth `screening-authorization-1.2.0`,
  ADR-0007)  
**Implemented:** 2026-07-18  
**Upstream:** GW-003 tip (`cursor/ossf-gw-003-evidence-d9ac`, PR #22)

---

## Mission

Add a governed **practitioner readiness** assessment between evidence
validation and authorization, producing a deterministic `readiness_digest`
that GW-005 CaseHistory will later bind.

```text
parse SiteCase 1.1.0
  → validate_evidence_layer          (GW-003, unchanged)
  → assess_readiness                 (GW-004)
  → evaluate_site (preflight SAD)    (unchanged thresholds)
  → authorize_screening(..., evidence_result, readiness_result)
  → physics → attestation
```

---

## Delivered

| Area | Location |
|---|---|
| Assessment + findings + dispositions | `core/readiness/assessment.py` |
| `readiness_digest` | `core/readiness/digest.py` |
| Errors | `core/readiness/errors.py` |
| Auth bind (`1.2.0`) | `core/authorization.py` |
| Attestation stamps | `core/governance.py` |
| Driver gate + failure artifact | `simulate.py` |
| ADR | `docs/adr/ADR-0007-practitioner-readiness-workflow.md` |
| Tests | `tests/test_readiness_*.py`, e2e not-ready in `test_end_to_end.py` |

### Dispositions

- `ready` / `ready_with_warnings` → continue (permits authorization)
- `not_ready` → `{site_id}_readiness_failure.json`, exit **1**, no preflight/physics

### Digest

`readiness_digest` = `sha256_of_json_stable` of schema version, case hash,
evidence digest, disposition, and normalized findings (id/severity/code).
Stamped on authorization token, attestation, and result `readiness` block.

### Rules

RDY-001 (evidence permits) · RDY-002 (digest match) · RDY-003 (Important
warnings) · RDY-004 (critical accepted) · RDY-005 (pending_verification
assumptions warn)

---

## Non-goals (unchanged)

UI, persistence, collaboration, history ledger (GW-005), new SAD
thresholds, new physics, SiteCase schema 1.2.0, user accounts.

---

## Verification

```bash
python3 -m pytest tests/ -q
```

Expect green suite on this branch after the five-commit stack.
