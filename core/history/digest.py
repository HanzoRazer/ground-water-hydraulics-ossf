"""
core/history/digest.py
======================

Deterministic history chain and artifact digests (OSSF-GW-005).

``history_chain_digest`` hashes governed semantic content only (no
timestamps, no absolute paths, no artifact-digest field).

``history_artifact_digest`` hashes the final serialized artifact payload
excluding only the artifact-digest field itself.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..governance import sha256_of_json_stable
from .identity import HISTORY_SCHEMA_VERSION, canonical_artifact_bindings
from .models import CaseHistory, CaseRevision, DecisionRecord, ExecutionRecord


def revision_chain_payload(revision: CaseRevision) -> dict:
    """Semantic revision projection for the chain digest (no created_utc)."""
    return {
        "revision_id": revision.revision_id,
        "revision_number": revision.revision_number,
        "parent_revision_id": revision.parent_revision_id,
        "site_digest": revision.site_digest,
        "evidence_digest": revision.evidence_digest,
        "readiness_digest": revision.readiness_digest,
        "authorization_id": revision.authorization_id,
        "result_digest": revision.result_digest,
        "created_reason": revision.created_reason.value,
    }


def decision_chain_payload(decision: DecisionRecord) -> dict:
    return {
        "decision_id": decision.decision_id,
        "sequence": decision.sequence,
        "category": decision.category.value,
        "event_type": decision.event_type.value,
        "authority": decision.authority.to_dict(),
        "outcome_code": decision.outcome_code.value,
        "summary": decision.summary,
        "related_revision_id": decision.related_revision_id,
        "related_ids": list(decision.related_ids),
    }


def execution_chain_payload(execution: ExecutionRecord) -> dict:
    """Semantic execution projection (timestamps excluded)."""
    bindings = canonical_artifact_bindings(
        [a.to_dict() for a in execution.generated_artifacts]
    )
    return {
        "execution_id": execution.execution_id,
        "revision_id": execution.revision_id,
        "authorization_id": execution.authorization_id,
        "result_digest": execution.result_digest,
        "status": execution.status.value,
        "generated_artifacts": list(bindings),
    }


def history_chain_payload(
    *,
    history_id: str,
    revisions: Sequence[CaseRevision],
    decisions: Sequence[DecisionRecord],
    executions: Sequence[ExecutionRecord],
    schema_version: str = HISTORY_SCHEMA_VERSION,
) -> dict:
    return {
        "schema_version": schema_version,
        "history_id": history_id,
        "revisions": [revision_chain_payload(r) for r in revisions],
        "decisions": [decision_chain_payload(d) for d in decisions],
        "executions": [execution_chain_payload(e) for e in executions],
    }


def compute_history_chain_digest(
    *,
    history_id: str,
    revisions: Sequence[CaseRevision],
    decisions: Sequence[DecisionRecord],
    executions: Sequence[ExecutionRecord],
    schema_version: str = HISTORY_SCHEMA_VERSION,
) -> str:
    return sha256_of_json_stable(history_chain_payload(
        history_id=history_id,
        revisions=revisions,
        decisions=decisions,
        executions=executions,
        schema_version=schema_version,
    ))


def compute_history_artifact_digest(serialized: Mapping[str, Any]) -> str:
    """Hash the serialized artifact excluding ``history_artifact_digest``."""
    payload = {k: v for k, v in serialized.items() if k != "history_artifact_digest"}
    return sha256_of_json_stable(payload)


def stamp_history_digests(
    *,
    history_id: str,
    site_id: str,
    revisions: Sequence[CaseRevision],
    decisions: Sequence[DecisionRecord],
    executions: Sequence[ExecutionRecord],
    schema_version: str = HISTORY_SCHEMA_VERSION,
    serialize_fn,
) -> CaseHistory:
    """Build a CaseHistory with chain + artifact digests stamped.

    ``serialize_fn(history_without_artifact_digest)`` must return a dict that
    includes ``history_chain_digest`` and all records; the artifact digest is
    then computed and the final CaseHistory returned.
    """
    chain = compute_history_chain_digest(
        history_id=history_id,
        revisions=revisions,
        decisions=decisions,
        executions=executions,
        schema_version=schema_version,
    )
    # Placeholder artifact digest — replaced after serialization projection.
    provisional = CaseHistory(
        schema_version=schema_version,
        history_id=history_id,
        site_id=site_id,
        history_chain_digest=chain,
        history_artifact_digest="0" * 16,
        revisions=tuple(revisions),
        decisions=tuple(decisions),
        executions=tuple(executions),
    )
    serialized = serialize_fn(provisional)
    artifact = compute_history_artifact_digest(serialized)
    return CaseHistory(
        schema_version=schema_version,
        history_id=history_id,
        site_id=site_id,
        history_chain_digest=chain,
        history_artifact_digest=artifact,
        revisions=tuple(revisions),
        decisions=tuple(decisions),
        executions=tuple(executions),
    )


__all__ = [
    "revision_chain_payload",
    "decision_chain_payload",
    "execution_chain_payload",
    "history_chain_payload",
    "compute_history_chain_digest",
    "compute_history_artifact_digest",
    "stamp_history_digests",
]
