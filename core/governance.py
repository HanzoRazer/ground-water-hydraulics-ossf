"""
governance.py
=============

Governance primitives for the OSSF groundwater screening tool.

Two responsibilities:

  1. Methodology attestation. Every output artifact stamps its provenance:
     which physics engine, which databases (with content hashes), which
     preflight ruleset. A submittal sealed today must be exactly reproducible
     from source in five years, even if the codebase evolves.

  2. Methodology-attestation marker. Functions whose outputs will be
     attached to a P.E. seal are marked with ``@methodology_attested``.

Scope enforcement (refusing to run the physics on an inappropriate site)
is NOT done here. It lives in the authorization contract
(``core/authorization.py``) and the registry boundary
(``core/physics_registry.run_authorized_engine``). Having a second
enforcement mechanism in this module (the former ``@screening_boundary``
decorator) created a competing authority — it only permitted ``proceed``
and would have wrongly blocked the permitted ``warn`` disposition — so it
was removed in favor of the single authorization authority (ADR-0001).

This module is the code-side analog of the ADRs under docs/adr/.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Version anchors. Bump these when the underlying rules or math change.
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION = "screening-1.0.0"
PREFLIGHT_RULESET_VERSION = "sad-1.0.0"


# ---------------------------------------------------------------------------
# Content-hash utilities. Used to fingerprint the databases at run time so
# every output stamps the exact soil / pathogen inputs it consumed.
# ---------------------------------------------------------------------------

def sha256_of_file(path: Path) -> str:
    """Return short SHA-256 hex digest (16 hex chars) of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def sha256_of_json_stable(obj: Any) -> str:
    """Hash a Python object as canonical JSON (sorted keys). Useful for
    hashing a config dict independent of key ordering or whitespace."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Attestation records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MethodologyAttestation:
    """Provenance stamp emitted on every successful output artifact.

    Beyond the methodology/engine/database provenance, the stamp now binds
    the run to the authorization it executed under: the authorization id and
    schema version, the preflight disposition, the findings digest, the
    evidence digest / review summary (OSSF-GW-003), the readiness digest /
    disposition (OSSF-GW-004), and the warning/refusal counts. A sealed
    submittal therefore records not just *what* ran but that it ran
    *authorized*, and against which findings, evidence, and readiness."""
    methodology_version: str
    preflight_ruleset_version: str
    preflight_disposition: str
    physics_engine: str
    physics_engine_version: str
    soil_db_hash: str
    pathogens_db_hash: str
    input_schema_version: str
    site_config_hash: str
    authorization_schema_version: str
    authorization_id: str
    findings_digest: str
    evidence_digest: str
    evidence_review_summary: dict
    readiness_digest: str
    readiness_disposition: str
    warning_count: int
    refusal_count: int
    generated_utc: str

    def as_dict(self) -> dict:
        return asdict(self)


def build_attestation(
    physics_engine: str,
    physics_engine_version: str,
    soil_db_path: Path,
    pathogens_db_path: Path,
    site_case,
    authorization,
    warning_count: int,
    refusal_count: int,
    evidence_result=None,
    readiness_result=None,
) -> MethodologyAttestation:
    """Build the provenance stamp for a successful (authorized) run.

    ``site_case`` is the validated :class:`~core.contracts.site_case_v1.SiteCaseV1`.
    Its canonical serialization provides the ``site_config_hash`` (the single
    governed hashing route) and its ``schema_version`` is stamped as
    ``input_schema_version`` (OSSF-GW-002 §5.16).

    ``authorization`` is a validated, permitting ``ScreeningAuthorization``.
    This is the final defensive gate before sealing: even though the
    execution boundary (``run_authorized_engine``) already validated the
    token, ``build_attestation`` independently re-checks the properties it
    is about to stamp and REFUSES to seal on any discrepancy. It validates:
    schema version, config-binding (recomputed canonical-JSON hash),
    findings-digest integrity (recomputed), evidence-digest binding,
    readiness-digest binding, ruleset compatibility, and a permitting
    disposition. An attested successful run must be authorized.

    ``evidence_result`` supplies the review summary stamped on the
    attestation (OSSF-GW-003). When omitted, a minimal summary is derived
    from the authorization's evidence_digest alone.

    ``readiness_result`` supplies the readiness disposition stamped on the
    attestation (OSSF-GW-004). When omitted, disposition is taken from the
    authorization's readiness_digest alone (unknown disposition string).

    (Imports from ``core.authorization`` are done lazily inside the function
    to avoid a module-load import cycle.)
    """
    from .authorization import (
        AUTHORIZATION_SCHEMA_VERSION,
        findings_digest as _recompute_findings_digest,
    )
    from .contracts.evidence_validation import compute_evidence_digest
    from .contracts.serialization import site_case_to_dict

    auth_id = getattr(authorization, "authorization_id", None)
    auth_schema = getattr(authorization, "schema_version", None)
    disposition = getattr(authorization, "disposition", None)
    dig = getattr(authorization, "findings_digest", None)
    auth_config_hash = getattr(authorization, "site_config_hash", None)
    auth_ruleset = getattr(authorization, "ruleset_version", None)
    auth_findings = getattr(authorization, "findings", None)
    auth_evidence_digest = getattr(authorization, "evidence_digest", None)
    auth_readiness_digest = getattr(authorization, "readiness_digest", None)

    site_config_hash = sha256_of_json_stable(site_case_to_dict(site_case))
    case_evidence_digest = compute_evidence_digest(site_case)

    if not auth_id or not auth_schema or not dig:
        raise ValueError(
            "build_attestation requires a validated ScreeningAuthorization; "
            "an attested successful run must carry authorization metadata."
        )
    if auth_schema != AUTHORIZATION_SCHEMA_VERSION:
        raise ValueError(
            f"build_attestation: authorization schema '{auth_schema}' does "
            f"not match the current contract '{AUTHORIZATION_SCHEMA_VERSION}'."
        )
    if disposition not in ("proceed", "warn"):
        raise ValueError(
            f"build_attestation refuses to stamp a run whose authorization "
            f"disposition is '{disposition}' (must permit execution)."
        )
    if auth_ruleset != PREFLIGHT_RULESET_VERSION:
        raise ValueError(
            f"build_attestation: authorization ruleset '{auth_ruleset}' is "
            f"not compatible with the active ruleset "
            f"'{PREFLIGHT_RULESET_VERSION}'."
        )
    if auth_config_hash != site_config_hash:
        raise ValueError(
            "build_attestation: authorization is bound to a different site "
            f"config (authorized {auth_config_hash}, current "
            f"{site_config_hash}); refusing to stamp."
        )
    if auth_findings is not None and _recompute_findings_digest(auth_findings) != dig:
        raise ValueError(
            "build_attestation: authorization findings_digest does not "
            "recompute from its findings; token integrity failure."
        )
    if not auth_evidence_digest:
        raise ValueError(
            "build_attestation requires authorization.evidence_digest "
            "(OSSF-GW-003)."
        )
    if auth_evidence_digest != case_evidence_digest:
        raise ValueError(
            "build_attestation: authorization evidence_digest does not match "
            f"the site case (authorized {auth_evidence_digest}, current "
            f"{case_evidence_digest}); refusing to stamp."
        )
    if not auth_readiness_digest:
        raise ValueError(
            "build_attestation requires authorization.readiness_digest "
            "(OSSF-GW-004)."
        )

    if evidence_result is not None:
        review_summary = dict(getattr(evidence_result, "review_summary", {}) or {})
        result_digest = getattr(evidence_result, "evidence_digest", None)
        if result_digest and result_digest != auth_evidence_digest:
            raise ValueError(
                "build_attestation: evidence_result.evidence_digest disagrees "
                "with authorization.evidence_digest; refusing to stamp."
            )
    else:
        review_summary = {
            "evidence_digest": auth_evidence_digest,
        }

    if readiness_result is not None:
        readiness_disposition = getattr(readiness_result, "disposition", None)
        ready_digest = getattr(readiness_result, "readiness_digest", None)
        if ready_digest and ready_digest != auth_readiness_digest:
            raise ValueError(
                "build_attestation: readiness_result.readiness_digest disagrees "
                "with authorization.readiness_digest; refusing to stamp."
            )
        if not readiness_disposition:
            raise ValueError(
                "build_attestation: readiness_result.disposition is required."
            )
        if not getattr(readiness_result, "permits_authorization", False):
            raise ValueError(
                "build_attestation refuses to stamp a run whose readiness "
                f"disposition is '{readiness_disposition}'."
            )
    else:
        readiness_disposition = "ready"  # minimal stamp when only digest known

    return MethodologyAttestation(
        methodology_version=METHODOLOGY_VERSION,
        preflight_ruleset_version=PREFLIGHT_RULESET_VERSION,
        preflight_disposition=disposition,
        physics_engine=physics_engine,
        physics_engine_version=physics_engine_version,
        soil_db_hash=sha256_of_file(soil_db_path),
        pathogens_db_hash=sha256_of_file(pathogens_db_path),
        input_schema_version=getattr(site_case, "schema_version", "unknown"),
        site_config_hash=site_config_hash,
        authorization_schema_version=auth_schema,
        authorization_id=auth_id,
        findings_digest=dig,
        evidence_digest=auth_evidence_digest,
        evidence_review_summary=review_summary,
        readiness_digest=auth_readiness_digest,
        readiness_disposition=readiness_disposition,
        warning_count=warning_count,
        refusal_count=refusal_count,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------
#
# NOTE: The former ``@screening_boundary`` decorator (and its
# ``ScreeningScopeError``) were removed. Scope refusal is now enforced by a
# single authority: ``core/authorization.py`` (the authorization contract)
# plus ``core/physics_registry.run_authorized_engine`` (the execution
# boundary). Keeping a decorator here that only permitted ``proceed`` would
# have wrongly blocked the permitted ``warn`` disposition and created a
# competing authority. See ADR-0001.


def methodology_attested(engine_name: str, engine_version: str) -> Callable:
    """Marks a function as producing output that will bear a P.E. seal.

    Attaches metadata for downstream introspection; the actual attestation
    stamp is emitted by ``build_attestation`` in the simulate driver.
    """
    def decorator(func: Callable) -> Callable:
        func.__methodology_attested__ = True  # type: ignore[attr-defined]
        func.__engine_name__ = engine_name  # type: ignore[attr-defined]
        func.__engine_version__ = engine_version  # type: ignore[attr-defined]
        return func
    return decorator
