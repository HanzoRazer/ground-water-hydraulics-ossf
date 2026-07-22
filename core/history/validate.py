"""
core/history/validate.py
========================

Structural and identity validation for prior CaseHistory chains
(OSSF-GW-005). Used by ``--prior-history`` loading.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .digest import (
    compute_history_artifact_digest,
    compute_history_chain_digest,
)
from .errors import HistoryIdentityError, HistoryValidationError
from .identity import (
    HISTORY_SCHEMA_VERSION,
    canonical_artifact_bindings,
    derive_decision_id,
    derive_execution_id,
    derive_history_id,
    derive_revision_id,
)
from .models import CaseHistory
from .serialization import history_from_dict, history_to_dict, load_history


def _hex_ok(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) in (16, 64)
        and all(c in "0123456789abcdef" for c in value)
    )


def validate_history_object(
    history: CaseHistory,
    *,
    expected_site_id: Optional[str] = None,
) -> CaseHistory:
    """Validate chain integrity, ID recomputation, and digests.

    Raises :class:`HistoryValidationError` / :class:`HistoryIdentityError`.
    Returns ``history`` unchanged on success.
    """
    if history.schema_version != HISTORY_SCHEMA_VERSION:
        raise HistoryValidationError(
            f"schema_version must be {HISTORY_SCHEMA_VERSION!r}, "
            f"got {history.schema_version!r}"
        )

    if expected_site_id is not None and history.site_id != expected_site_id:
        raise HistoryIdentityError(
            f"site_id mismatch: history has {history.site_id!r}, "
            f"case has {expected_site_id!r}"
        )

    revisions = history.revisions
    if not revisions:
        raise HistoryValidationError("history has no revisions")

    # Ascending contiguous revision numbers starting at 1.
    numbers = [r.revision_number for r in revisions]
    if numbers != list(range(1, len(revisions) + 1)):
        raise HistoryValidationError(
            f"revision numbers must be contiguous starting at 1; got {numbers}"
        )

    if revisions[0].parent_revision_id is not None:
        raise HistoryValidationError("revision 1 must have null parent_revision_id")

    rev_ids = [r.revision_id for r in revisions]
    if len(set(rev_ids)) != len(rev_ids):
        raise HistoryValidationError("duplicate revision_id values")

    # history_id must match recomputation from revision 1 site_digest.
    expected_hid = derive_history_id(
        site_id=history.site_id,
        initial_site_digest=revisions[0].site_digest,
        schema_version=history.schema_version,
    )
    if history.history_id != expected_hid:
        raise HistoryIdentityError(
            f"history_id mismatch: stored {history.history_id!r}, "
            f"expected {expected_hid!r}"
        )

    for i, rev in enumerate(revisions):
        if i == 0:
            if rev.parent_revision_id is not None:
                raise HistoryValidationError(
                    "revision 1 parent_revision_id must be null"
                )
        else:
            prev = revisions[i - 1]
            if rev.parent_revision_id != prev.revision_id:
                raise HistoryValidationError(
                    f"revision {rev.revision_number} parent_revision_id "
                    f"{rev.parent_revision_id!r} != preceding "
                    f"{prev.revision_id!r}"
                )
        expected_rid = derive_revision_id(
            history_id=history.history_id,
            revision_number=rev.revision_number,
            parent_revision_id=rev.parent_revision_id,
            site_digest=rev.site_digest,
            evidence_digest=rev.evidence_digest,
            readiness_digest=rev.readiness_digest,
            authorization_id=rev.authorization_id,
            created_reason=rev.created_reason.value,
            schema_version=history.schema_version,
        )
        if rev.revision_id != expected_rid:
            raise HistoryValidationError(
                f"revision {rev.revision_number} revision_id does not recompute"
            )

    rev_id_set = set(rev_ids)

    # Decisions
    decision_ids = [d.decision_id for d in history.decisions]
    if len(set(decision_ids)) != len(decision_ids):
        raise HistoryValidationError("duplicate decision_id values")

    by_rev_seq: dict[str, list[int]] = {}
    for d in history.decisions:
        if d.related_revision_id not in rev_id_set:
            raise HistoryValidationError(
                f"decision {d.decision_id} references unknown revision "
                f"{d.related_revision_id!r}"
            )
        by_rev_seq.setdefault(d.related_revision_id, []).append(d.sequence)
        expected_did = derive_decision_id(
            revision_id=d.related_revision_id,
            sequence=d.sequence,
            category=d.category.value,
            event_type=d.event_type.value,
            authority=d.authority.to_dict(),
            outcome_code=d.outcome_code.value,
            related_ids=d.related_ids,
        )
        if d.decision_id != expected_did:
            raise HistoryValidationError(
                f"decision_id {d.decision_id!r} does not recompute"
            )

    for rid, seqs in by_rev_seq.items():
        ordered = sorted(seqs)
        if ordered != list(range(1, len(seqs) + 1)):
            raise HistoryValidationError(
                f"decision sequences for revision {rid} must be contiguous "
                f"starting at 1; got {seqs}"
            )

    # Executions
    execution_ids = [e.execution_id for e in history.executions]
    if len(set(execution_ids)) != len(execution_ids):
        raise HistoryValidationError("duplicate execution_id values")

    exe_by_rev: dict[str, int] = {}
    for e in history.executions:
        if e.revision_id not in rev_id_set:
            raise HistoryValidationError(
                f"execution {e.execution_id} references unknown revision "
                f"{e.revision_id!r}"
            )
        exe_by_rev[e.revision_id] = exe_by_rev.get(e.revision_id, 0) + 1
        if exe_by_rev[e.revision_id] > 1:
            raise HistoryValidationError(
                f"revision {e.revision_id} has more than one execution (v1)"
            )
        for a in e.generated_artifacts:
            if not _hex_ok(a.sha256):
                raise HistoryValidationError(
                    f"malformed artifact binding digest {a.sha256!r}"
                )
        bindings = canonical_artifact_bindings(
            [a.to_dict() for a in e.generated_artifacts]
        )
        expected_eid = derive_execution_id(
            revision_id=e.revision_id,
            authorization_id=e.authorization_id,
            result_digest=e.result_digest,
            artifact_bindings=bindings,
        )
        if e.execution_id != expected_eid:
            raise HistoryValidationError(
                f"execution_id {e.execution_id!r} does not recompute"
            )

    # Digests
    if not history.history_chain_digest or not history.history_artifact_digest:
        raise HistoryValidationError("top-level digest fields are missing")

    chain = compute_history_chain_digest(
        history_id=history.history_id,
        revisions=history.revisions,
        decisions=history.decisions,
        executions=history.executions,
        schema_version=history.schema_version,
    )
    if history.history_chain_digest != chain:
        raise HistoryValidationError("history_chain_digest does not recompute")

    serialized = history_to_dict(history)
    artifact = compute_history_artifact_digest(serialized)
    if history.history_artifact_digest != artifact:
        raise HistoryValidationError("history_artifact_digest does not recompute")

    return history


def validate_history_dict(
    raw: Mapping[str, Any],
    *,
    expected_site_id: Optional[str] = None,
) -> CaseHistory:
    try:
        history = history_from_dict(raw)
    except HistoryValidationError:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        raise HistoryValidationError(str(exc)) from exc
    return validate_history_object(history, expected_site_id=expected_site_id)


def load_and_validate_history(
    path: Union[str, Path],
    *,
    expected_site_id: Optional[str] = None,
) -> CaseHistory:
    """Load prior history from disk and fully validate the chain."""
    history = load_history(path)
    return validate_history_object(history, expected_site_id=expected_site_id)


def load_schema() -> dict:
    """Load the CaseHistory JSON Schema document."""
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "case_history.schema.json"
    )
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_against_json_schema(raw: Mapping[str, Any]) -> None:
    """Structural JSON Schema check (optional dependency: jsonschema)."""
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover
        raise HistoryValidationError(
            "jsonschema package required for schema validation"
        ) from exc
    schema = load_schema()
    try:
        jsonschema.validate(instance=dict(raw), schema=schema)
    except jsonschema.ValidationError as exc:
        raise HistoryValidationError(
            f"schema validation failed: {exc.message}"
        ) from exc


__all__ = [
    "validate_history_object",
    "validate_history_dict",
    "load_and_validate_history",
    "load_schema",
    "validate_against_json_schema",
]
