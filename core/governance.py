"""
governance.py
=============

Governance primitives for the OSSF groundwater screening tool.

Two responsibilities:

  1. Methodology attestation. Every output artifact stamps its provenance:
     which physics engine, which databases (with content hashes), which
     preflight ruleset. A submittal sealed today must be exactly reproducible
     from source in five years, even if the codebase evolves.

  2. Version anchors. ``METHODOLOGY_VERSION`` is the public API version of
     the screening methodology. A MAJOR bump signals a breaking change to
     callers (e.g. a signature change on the engine entry point).

Scope enforcement (refusing to run the physics on an inappropriate site)
lives in the authorization contract (``core/authorization.py``) and the
registry boundary (``core/physics_registry.run_authorized_engine``). This
module only records provenance — it does not decide who may run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Version anchors. Bump when rules, math, or public API shapes change.
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION = "screening-3.0.0"
PREFLIGHT_RULESET_VERSION = "sad-1.0.0"


# ---------------------------------------------------------------------------
# Content-hash utilities
# ---------------------------------------------------------------------------

def sha256_of_file(path: Path) -> str:
    """Return a short (16 hex char) SHA-256 digest of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def sha256_of_json_stable(obj: Any) -> str:
    """Hash a Python object as canonical JSON (sorted keys, no whitespace).

    Useful for hashing a config dict independent of key ordering so the
    hash is reproducible regardless of insertion order."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Attestation record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MethodologyAttestation:
    """Provenance stamp emitted on every successful output artifact.

    All fields are plain data — no callables, no mutable state — so
    instances can be serialized and compared.
    """
    methodology_version: str
    preflight_ruleset_version: str
    engine_name: str
    engine_version: str
    generated_utc: str
    soils_db_sha256: str
    constituents_db_sha256: str
    site_config_hash: str

    def as_dict(self) -> dict:
        return {
            "methodology_version": self.methodology_version,
            "preflight_ruleset_version": self.preflight_ruleset_version,
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "generated_utc": self.generated_utc,
            "soils_db_sha256": self.soils_db_sha256,
            "constituents_db_sha256": self.constituents_db_sha256,
            "site_config_hash": self.site_config_hash,
        }


def build_attestation(
    engine_name: str,
    engine_version: str,
    soils_db_sha256: str,
    constituents_db_sha256: str,
    site_config_hash: str,
) -> MethodologyAttestation:
    """Construct a methodology attestation for a completed run."""
    return MethodologyAttestation(
        methodology_version=METHODOLOGY_VERSION,
        preflight_ruleset_version=PREFLIGHT_RULESET_VERSION,
        engine_name=engine_name,
        engine_version=engine_version,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        soils_db_sha256=soils_db_sha256,
        constituents_db_sha256=constituents_db_sha256,
        site_config_hash=site_config_hash,
    )
