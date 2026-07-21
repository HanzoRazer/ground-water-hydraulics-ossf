"""
core/history/builder.py
=======================

Construct and append CaseHistory revisions from governed pipeline outcomes
(OSSF-GW-005). Observational only — does not authorize or re-validate
engineering data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from ..contracts.serialization import site_case_hash
from ..contracts.site_case_v1 import SiteCaseV1
from ..governance import sha256_of_json_stable
from .decision_categories import (
    AuthorityType,
    CreatedReason,
    DecisionCategory,
    DecisionOutcomeCode,
    ExecutionStatus,
)
from .digest import stamp_history_digests
from .errors import HistoryConstructionError, HistoryIdentityError
from .events import HistoryEventType
from .identity import (
    HISTORY_SCHEMA_VERSION,
    canonical_artifact_bindings,
    derive_decision_id,
    derive_execution_id,
    derive_history_id,
    derive_revision_id,
)
from .models import (
    ArtifactBinding,
    AuthorityRecord,
    CaseHistory,
    CaseRevision,
    DecisionRecord,
    ExecutionRecord,
)
from .serialization import history_to_dict
from .validate import validate_history_object


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _evidence_digest(evidence_summary: Any) -> str:
    digest = getattr(evidence_summary, "evidence_digest", None)
    if digest is None and isinstance(evidence_summary, Mapping):
        digest = evidence_summary.get("evidence_digest")
    if not digest:
        raise HistoryConstructionError(
            "evidence_digest is required whenever history is emitted"
        )
    return digest


def _readiness_digest(readiness_result: Any) -> str:
    digest = getattr(readiness_result, "readiness_digest", None)
    if digest is None and isinstance(readiness_result, Mapping):
        digest = readiness_result.get("readiness_digest")
    if not digest:
        raise HistoryConstructionError(
            "readiness_digest is required for all GW-005 history revisions"
        )
    return digest


def semantic_result_payload(result_contract: Mapping[str, Any]) -> dict:
    """Strip history references and wall-clock / path presentation fields."""
    exclude_top = {
        "history",
        "generated_utc",
        "started_utc",
        "completed_utc",
    }

    def _scrub(obj: Any, *, top: bool = False) -> Any:
        if isinstance(obj, Mapping):
            out = {}
            for k, v in obj.items():
                if top and k in exclude_top:
                    continue
                if k in ("generated_utc", "started_utc", "completed_utc"):
                    continue
                if k in ("output_path", "report_path", "history_artifact"):
                    continue
                out[k] = _scrub(v, top=False)
            return out
        if isinstance(obj, list):
            return [_scrub(x, top=False) for x in obj]
        return obj

    return _scrub(dict(result_contract), top=True)


def compute_result_digest(result_contract: Mapping[str, Any]) -> str:
    """Digest of the execution result before GW-005 history references."""
    return sha256_of_json_stable(semantic_result_payload(result_contract))


@dataclass(frozen=True)
class AuthorizationDenial:
    """Explicit denial input for history construction (no auth token)."""

    findings: Tuple[Any, ...] = ()
    message: str = "Authorization denied"


@dataclass(frozen=True)
class ExecutionOutcome:
    """Execution result inputs for an authorized history revision."""

    status: ExecutionStatus
    result_digest: str
    started_utc: str
    completed_utc: str


def _system_authority(component: str) -> AuthorityRecord:
    return AuthorityRecord(
        authority_type=AuthorityType.SYSTEM,
        authority_id=component,
    )


def _policy_authority(policy_id: str) -> AuthorityRecord:
    return AuthorityRecord(
        authority_type=AuthorityType.POLICY,
        authority_id=policy_id,
    )


def _finding_ids(findings: Sequence[Any], *, attr_candidates: Sequence[str]) -> Tuple[str, ...]:
    """Preserve upstream order; skip blanks."""
    out: list[str] = []
    for f in findings:
        if isinstance(f, str):
            if f.strip():
                out.append(f.strip())
            continue
        for attr in attr_candidates:
            val = getattr(f, attr, None)
            if val is None and isinstance(f, Mapping):
                val = f.get(attr)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
                break
    return tuple(out)


def _make_decision(
    *,
    revision_id: str,
    sequence: int,
    category: DecisionCategory,
    event_type: HistoryEventType,
    outcome_code: DecisionOutcomeCode,
    authority: AuthorityRecord,
    summary: str,
    related_ids: Sequence[str],
) -> DecisionRecord:
    related = tuple(related_ids)
    did = derive_decision_id(
        revision_id=revision_id,
        sequence=sequence,
        category=category.value,
        event_type=event_type.value,
        authority=authority.to_dict(),
        outcome_code=outcome_code.value,
        related_ids=related,
    )
    return DecisionRecord(
        decision_id=did,
        sequence=sequence,
        category=category,
        event_type=event_type,
        authority=authority,
        outcome_code=outcome_code,
        summary=summary,
        related_revision_id=revision_id,
        related_ids=related,
    )


def _normalize_artifacts(
    generated_artifacts: Sequence[Union[ArtifactBinding, Mapping[str, Any]]],
) -> Tuple[ArtifactBinding, ...]:
    out: list[ArtifactBinding] = []
    for a in generated_artifacts:
        if isinstance(a, ArtifactBinding):
            out.append(a)
        else:
            out.append(ArtifactBinding(
                artifact_type=a["artifact_type"],
                relative_path=a["relative_path"],
                sha256=a["sha256"],
            ))
    # Canonical order for identity; preserve as tuple after sort.
    ordered = canonical_artifact_bindings([a.to_dict() for a in out])
    return tuple(
        ArtifactBinding(
            artifact_type=b["artifact_type"],
            relative_path=b["relative_path"],
            sha256=b["sha256"],
        )
        for b in ordered
    )


def build_history(
    *,
    case: SiteCaseV1,
    prior_history: Optional[CaseHistory] = None,
    evidence_summary: Any,
    readiness_result: Any,
    authorization_result: Any = None,
    authorization_denial: Optional[AuthorizationDenial] = None,
    execution_result: Optional[ExecutionOutcome] = None,
    generated_artifacts: Sequence[Union[ArtifactBinding, Mapping[str, Any]]] = (),
    created_reason: Union[CreatedReason, str],
    created_utc: Optional[str] = None,
) -> CaseHistory:
    """Build an initial chain or append exactly one revision.

    Emission paths:
    * readiness not_ready — no authorization, no execution
    * authorization denied — denial decision, no execution
    * authorized proceed/warn — auth + execution (+ optional reporting)
    """
    if isinstance(created_reason, str):
        created_reason = CreatedReason(created_reason)

    site_id = case.site_id
    site_digest = site_case_hash(case)
    evidence_digest = _evidence_digest(evidence_summary)
    readiness_digest = _readiness_digest(readiness_result)
    created_utc = created_utc or _utc_now()
    artifacts = _normalize_artifacts(generated_artifacts)

    disposition = getattr(readiness_result, "disposition", None)
    if disposition is None and isinstance(readiness_result, Mapping):
        disposition = readiness_result.get("disposition")

    # --- Prior chain ---
    if prior_history is not None:
        validate_history_object(prior_history, expected_site_id=site_id)
        history_id = prior_history.history_id
        parent = prior_history.revisions[-1]
        revision_number = parent.revision_number + 1
        parent_revision_id = parent.revision_id
        prior_revisions = list(prior_history.revisions)
        prior_decisions = list(prior_history.decisions)
        prior_executions = list(prior_history.executions)
        if created_reason is CreatedReason.INITIAL_RUN:
            raise HistoryConstructionError(
                "created_reason initial_run is only valid for revision 1"
            )
    else:
        history_id = derive_history_id(
            site_id=site_id,
            initial_site_digest=site_digest,
        )
        revision_number = 1
        parent_revision_id = None
        prior_revisions = []
        prior_decisions = []
        prior_executions = []
        if created_reason is not CreatedReason.INITIAL_RUN:
            raise HistoryConstructionError(
                "revision 1 requires created_reason=initial_run"
            )

    # Resolve authorization_id / result_digest for the revision
    auth_token = authorization_result
    denial = authorization_denial
    if auth_token is not None and denial is not None:
        raise HistoryConstructionError(
            "pass either authorization_result or authorization_denial, not both"
        )

    authorization_id: Optional[str] = None
    result_digest: Optional[str] = None
    if auth_token is not None:
        authorization_id = getattr(auth_token, "authorization_id", None)
        if not authorization_id:
            raise HistoryConstructionError(
                "authorization_result is missing authorization_id"
            )
    if execution_result is not None:
        result_digest = execution_result.result_digest
        if not result_digest:
            raise HistoryConstructionError(
                "execution_result.result_digest is required when execution ran"
            )
        if authorization_id is None:
            raise HistoryConstructionError(
                "execution_result requires a successful authorization_result"
            )

    # not_ready path: authorization must not be set
    if disposition == "not_ready":
        if auth_token is not None or denial is not None or execution_result is not None:
            raise HistoryConstructionError(
                "not_ready history must not include authorization or execution"
            )
        authorization_id = None
        result_digest = None

    revision_id = derive_revision_id(
        history_id=history_id,
        revision_number=revision_number,
        parent_revision_id=parent_revision_id,
        site_digest=site_digest,
        evidence_digest=evidence_digest,
        readiness_digest=readiness_digest,
        authorization_id=authorization_id,
        created_reason=created_reason.value,
    )

    revision = CaseRevision(
        revision_id=revision_id,
        revision_number=revision_number,
        parent_revision_id=parent_revision_id,
        site_digest=site_digest,
        evidence_digest=evidence_digest,
        readiness_digest=readiness_digest,
        authorization_id=authorization_id,
        result_digest=result_digest,
        created_reason=created_reason,
        created_utc=created_utc,
    )

    new_decisions: list[DecisionRecord] = []
    new_executions: list[ExecutionRecord] = []
    seq = 1

    # --- Decisions / execution by gate ---
    if disposition == "not_ready":
        findings = getattr(readiness_result, "findings", ()) or ()
        # Blocking findings preferred; fall back to all finding IDs.
        blocking = [
            f for f in findings
            if getattr(f, "severity", None) == "block"
            or (isinstance(f, Mapping) and f.get("severity") == "block")
        ]
        related = _finding_ids(
            blocking or findings, attr_candidates=("finding_id",)
        )
        new_decisions.append(_make_decision(
            revision_id=revision_id,
            sequence=seq,
            category=DecisionCategory.READINESS,
            event_type=HistoryEventType.READINESS_NOT_READY,
            outcome_code=DecisionOutcomeCode.NOT_READY,
            authority=_system_authority("core.readiness"),
            summary=(
                f"Practitioner readiness disposition is not_ready "
                f"({len(related)} finding ref(s))"
            ),
            related_ids=related,
        ))
    elif denial is not None:
        related = _finding_ids(
            denial.findings, attr_candidates=("rule_id", "finding_id")
        )
        new_decisions.append(_make_decision(
            revision_id=revision_id,
            sequence=seq,
            category=DecisionCategory.AUTHORIZATION,
            event_type=HistoryEventType.AUTHORIZATION_DENIED,
            outcome_code=DecisionOutcomeCode.DENIED,
            authority=_policy_authority("preflight"),
            summary=denial.message,
            related_ids=related,
        ))
    elif auth_token is not None:
        auth_disp = getattr(auth_token, "disposition", None)
        if auth_disp == "warn":
            event = HistoryEventType.AUTHORIZATION_PROCEEDED_WITH_WARNINGS
            outcome = DecisionOutcomeCode.PROCEED_WITH_WARNINGS
            summary = "Authorization granted with warnings"
        elif auth_disp == "proceed":
            event = HistoryEventType.AUTHORIZATION_PROCEEDED
            outcome = DecisionOutcomeCode.PROCEED
            summary = "Authorization granted"
        else:
            raise HistoryConstructionError(
                f"unsupported authorization disposition {auth_disp!r}"
            )
        findings = getattr(auth_token, "findings", ()) or ()
        related = _finding_ids(findings, attr_candidates=("rule_id", "finding_id"))
        new_decisions.append(_make_decision(
            revision_id=revision_id,
            sequence=seq,
            category=DecisionCategory.AUTHORIZATION,
            event_type=event,
            outcome_code=outcome,
            authority=_policy_authority("authorization"),
            summary=summary,
            related_ids=related,
        ))
        seq += 1

        if execution_result is None:
            raise HistoryConstructionError(
                "authorized history requires execution_result in GW-005 v1"
            )

        bindings = artifacts
        exe_id = derive_execution_id(
            revision_id=revision_id,
            authorization_id=authorization_id,
            result_digest=result_digest,
            artifact_bindings=[a.to_dict() for a in bindings],
        )
        new_executions.append(ExecutionRecord(
            execution_id=exe_id,
            revision_id=revision_id,
            authorization_id=authorization_id,
            result_digest=result_digest,
            status=execution_result.status,
            generated_artifacts=bindings,
            started_utc=execution_result.started_utc,
            completed_utc=execution_result.completed_utc,
        ))

        if execution_result.status is ExecutionStatus.PASSED:
            exe_event = HistoryEventType.SCREENING_EXECUTED
            exe_outcome = DecisionOutcomeCode.EXECUTED
            exe_summary = "Screening executed; criteria met"
        else:
            exe_event = HistoryEventType.SCREENING_FAILED
            exe_outcome = DecisionOutcomeCode.FAILED
            exe_summary = "Screening executed; criteria not met"

        new_decisions.append(_make_decision(
            revision_id=revision_id,
            sequence=seq,
            category=DecisionCategory.EXECUTION,
            event_type=exe_event,
            outcome_code=exe_outcome,
            authority=_system_authority("simulate.py"),
            summary=exe_summary,
            related_ids=(exe_id,),
        ))
        seq += 1

        report_written = any(a.artifact_type == "report_text" for a in bindings)
        if report_written:
            new_decisions.append(_make_decision(
                revision_id=revision_id,
                sequence=seq,
                category=DecisionCategory.REPORTING,
                event_type=HistoryEventType.REPORT_GENERATED,
                outcome_code=DecisionOutcomeCode.REPORT_GENERATED,
                authority=_system_authority("simulate.py"),
                summary="Text report written",
                related_ids=tuple(
                    a.relative_path for a in bindings
                    if a.artifact_type == "report_text"
                ),
            ))
    else:
        raise HistoryConstructionError(
            "build_history requires not_ready readiness, authorization_denial, "
            "or authorization_result"
        )

    return stamp_history_digests(
        history_id=history_id,
        site_id=site_id,
        revisions=prior_revisions + [revision],
        decisions=prior_decisions + new_decisions,
        executions=prior_executions + new_executions,
        schema_version=HISTORY_SCHEMA_VERSION,
        serialize_fn=history_to_dict,
    )


def append_revision(
    prior_history: CaseHistory,
    **kwargs: Any,
) -> CaseHistory:
    """Append Revision N+1 to an existing validated chain."""
    if "prior_history" in kwargs:
        raise TypeError("pass prior_history as the first positional argument")
    return build_history(prior_history=prior_history, **kwargs)


def revision_lookup(
    history: CaseHistory,
    revision_id: str,
) -> CaseRevision:
    for rev in history.revisions:
        if rev.revision_id == revision_id:
            return rev
    raise HistoryIdentityError(f"revision_id {revision_id!r} not found")


__all__ = [
    "AuthorizationDenial",
    "ExecutionOutcome",
    "semantic_result_payload",
    "compute_result_digest",
    "build_history",
    "append_revision",
    "revision_lookup",
]
