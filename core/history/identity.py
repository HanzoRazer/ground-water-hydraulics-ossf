"""
core/history/identity.py
========================

Deterministic 16-hex ID derivation for CaseHistory records (OSSF-GW-005).

Uses :func:`core.governance.sha256_of_json_stable` (already truncated to 16
hex). ID payloads use a fixed key shape with explicit JSON ``null`` for
nullable fields — never omitted keys, never empty-string substitutes.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from ..governance import sha256_of_json_stable

HISTORY_SCHEMA_VERSION = "screening-case-history-1.0.0"


def derive_history_id(
    *,
    site_id: str,
    initial_site_digest: str,
    schema_version: str = HISTORY_SCHEMA_VERSION,
) -> str:
    """Stable chain identity — constant across appended revisions."""
    return sha256_of_json_stable({
        "schema_version": schema_version,
        "site_id": site_id,
        "initial_site_digest": initial_site_digest,
    })


def revision_id_material(
    *,
    history_id: str,
    revision_number: int,
    parent_revision_id: Optional[str],
    site_digest: str,
    evidence_digest: str,
    readiness_digest: str,
    authorization_id: Optional[str],
    created_reason: str,
    schema_version: str = HISTORY_SCHEMA_VERSION,
) -> dict:
    """Fixed-shape payload for revision_id (nulls explicit)."""
    return {
        "schema_version": schema_version,
        "history_id": history_id,
        "revision_number": revision_number,
        "parent_revision_id": parent_revision_id,
        "site_digest": site_digest,
        "evidence_digest": evidence_digest,
        "readiness_digest": readiness_digest,
        "authorization_id": authorization_id,
        "created_reason": created_reason,
    }


def derive_revision_id(
    *,
    history_id: str,
    revision_number: int,
    parent_revision_id: Optional[str],
    site_digest: str,
    evidence_digest: str,
    readiness_digest: str,
    authorization_id: Optional[str],
    created_reason: str,
    schema_version: str = HISTORY_SCHEMA_VERSION,
) -> str:
    return sha256_of_json_stable(revision_id_material(
        history_id=history_id,
        revision_number=revision_number,
        parent_revision_id=parent_revision_id,
        site_digest=site_digest,
        evidence_digest=evidence_digest,
        readiness_digest=readiness_digest,
        authorization_id=authorization_id,
        created_reason=created_reason,
        schema_version=schema_version,
    ))


def decision_id_material(
    *,
    revision_id: str,
    sequence: int,
    category: str,
    event_type: str,
    authority: Mapping[str, Any],
    outcome_code: str,
    related_ids: Sequence[str],
) -> dict:
    """Fixed-shape payload for decision_id.

    ``related_ids`` are hashed in the order provided (canonical upstream
    order, or already lexically sorted by the caller).
    """
    return {
        "revision_id": revision_id,
        "sequence": sequence,
        "category": category,
        "event_type": event_type,
        "authority": dict(authority),
        "outcome_code": outcome_code,
        "related_ids": list(related_ids),
    }


def derive_decision_id(
    *,
    revision_id: str,
    sequence: int,
    category: str,
    event_type: str,
    authority: Mapping[str, Any],
    outcome_code: str,
    related_ids: Sequence[str],
) -> str:
    return sha256_of_json_stable(decision_id_material(
        revision_id=revision_id,
        sequence=sequence,
        category=category,
        event_type=event_type,
        authority=authority,
        outcome_code=outcome_code,
        related_ids=related_ids,
    ))


def execution_id_material(
    *,
    revision_id: str,
    authorization_id: str,
    result_digest: str,
    artifact_bindings: Sequence[Mapping[str, Any]],
) -> dict:
    """Fixed-shape payload for execution_id.

    ``artifact_bindings`` must already be in canonical order (sorted by
    artifact_type, then relative_path). Paths are provenance labels (may be
    ``external/...``), not absolute filesystem presentation.
    """
    return {
        "revision_id": revision_id,
        "authorization_id": authorization_id,
        "result_digest": result_digest,
        "artifact_bindings": [dict(b) for b in artifact_bindings],
    }


def derive_execution_id(
    *,
    revision_id: str,
    authorization_id: str,
    result_digest: str,
    artifact_bindings: Sequence[Mapping[str, Any]],
) -> str:
    return sha256_of_json_stable(execution_id_material(
        revision_id=revision_id,
        authorization_id=authorization_id,
        result_digest=result_digest,
        artifact_bindings=artifact_bindings,
    ))


def canonical_artifact_bindings(
    bindings: Sequence[Mapping[str, Any]],
) -> tuple:
    """Sort artifact bindings for identity / chain digests."""
    items = [dict(b) for b in bindings]
    items.sort(key=lambda b: (b.get("artifact_type", ""), b.get("relative_path", "")))
    return tuple(items)


__all__ = [
    "HISTORY_SCHEMA_VERSION",
    "derive_history_id",
    "revision_id_material",
    "derive_revision_id",
    "decision_id_material",
    "derive_decision_id",
    "execution_id_material",
    "derive_execution_id",
    "canonical_artifact_bindings",
]
