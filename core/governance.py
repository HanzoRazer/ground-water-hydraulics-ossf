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
    schema version, the preflight disposition, the findings digest, and the
    warning/refusal counts. A sealed submittal therefore records not just
    *what* ran but that it ran *authorized*, and against which findings."""
    methodology_version: str
    preflight_ruleset_version: str
    preflight_disposition: str
    physics_engine: str
    physics_engine_version: str
    soil_db_hash: str
    pathogens_db_hash: str
    site_config_hash: str
    authorization_schema_version: str
    authorization_id: str
    findings_digest: str
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
    site_config: dict,
    authorization,
    warning_count: int,
    refusal_count: int,
) -> MethodologyAttestation:
    """Build the provenance stamp for a successful (authorized) run.

    ``authorization`` is a validated, permitting ``ScreeningAuthorization``.
    This is the final defensive gate before sealing: even though the
    execution boundary (``run_authorized_engine``) already validated the
    token, ``build_attestation`` independently re-checks the properties it
    is about to stamp and REFUSES to seal on any discrepancy. It validates:
    schema version, config-binding (recomputed canonical-JSON hash),
    findings-digest integrity (recomputed), ruleset compatibility, and a
    permitting disposition. An attested successful run must be authorized.

    (Imports from ``core.authorization`` are done lazily inside the function
    to avoid a module-load import cycle.)
    """
    from .authorization import (
        AUTHORIZATION_SCHEMA_VERSION,
        findings_digest as _recompute_findings_digest,
    )

    auth_id = getattr(authorization, "authorization_id", None)
    auth_schema = getattr(authorization, "schema_version", None)
    disposition = getattr(authorization, "disposition", None)
    dig = getattr(authorization, "findings_digest", None)
    auth_config_hash = getattr(authorization, "site_config_hash", None)
    auth_ruleset = getattr(authorization, "ruleset_version", None)
    auth_findings = getattr(authorization, "findings", None)

    site_config_hash = sha256_of_json_stable(site_config)

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

    return MethodologyAttestation(
        methodology_version=METHODOLOGY_VERSION,
        preflight_ruleset_version=PREFLIGHT_RULESET_VERSION,
        preflight_disposition=disposition,
        physics_engine=physics_engine,
        physics_engine_version=physics_engine_version,
        soil_db_hash=sha256_of_file(soil_db_path),
        pathogens_db_hash=sha256_of_file(pathogens_db_path),
        site_config_hash=site_config_hash,
        authorization_schema_version=auth_schema,
        authorization_id=auth_id,
        findings_digest=dig,
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
