"""
authorization.py
================

The screening authorization contract.

Where ``preflight.py`` decides *whether* a site is appropriate for the
screening model, this module turns an appropriate determination into an
explicit, tamper-evident **authorization token** that the physics layer
requires before it will run. Nothing downstream trusts a bare determination;
it trusts a validated ``ScreeningAuthorization``.

The doctrine is that a refused site must never reach the physics engine. The
authorization contract enforces that doctrine as a *positive capability*:
the engine boundary (``physics_registry``) will only execute when handed an
authorization that:

  1. carries a permitting disposition (``proceed`` or ``warn``),
  2. was minted from the *same* site config it is now being used with
     (config-binding, checked by recomputing the canonical-JSON hash),
  3. has not been tampered with (its ``findings_digest`` and
     ``authorization_id`` recompute to the stored values).

Refusal is not representable as an authorization: ``authorize_screening``
raises ``AuthorizationDeniedError`` for a refused determination. There is
no override flag, no ``force`` kwarg.

Schema version: ``screening-authorization-1.0.0``. Bump when the token's
shape or the derivation of its identifiers changes.

Design notes
------------
* Config hashing reuses ``governance.sha256_of_json_stable`` — there is
  exactly one canonical-JSON hash algorithm in this codebase.
* ``findings_digest`` is the SHA-256 (16 hex) of the canonical JSON of the
  normalized, order-preserved findings.
* ``authorization_id`` is a deterministic digest derived from
  ``site_config_hash + ruleset_version + findings_digest +
  schema_version``. It is reproducible for identical inputs and is NOT a
  substitute for the config or findings hashes — it binds them together.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Tuple

from .governance import PREFLIGHT_RULESET_VERSION, sha256_of_json_stable


# ---------------------------------------------------------------------------
# Version anchor
# ---------------------------------------------------------------------------

AUTHORIZATION_SCHEMA_VERSION = "screening-authorization-1.0.0"

PERMITTING_DISPOSITIONS: Tuple[str, ...] = ("proceed", "warn")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthorizationError(RuntimeError):
    """Base class for all authorization-contract failures."""


class AuthorizationDeniedError(AuthorizationError):
    """Raised when authorization cannot be granted because the preflight
    refused the site (or otherwise did not yield a permitting disposition).

    This is the positive-capability form of the refusal doctrine:
    a refused site produces no authorization, so the physics boundary has
    nothing to accept. There is no bypass."""


class AuthorizationMismatchError(AuthorizationError):
    """Raised when an authorization does not validate against the site
    config or has been tampered with: wrong schema version, config hash
    mismatch, or a recomputed digest/id that disagrees with the stored value.
    """


# ---------------------------------------------------------------------------
# Normalized finding
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuthorizedFinding:
    """A preflight finding, normalized into the authorization record.

    Deliberately a copy (not a reference to ``RuleFinding``) so the
    authorization is a self-contained, serializable record of exactly what
    the preflight said at mint time."""
    rule_id: str
    disposition: str
    message: str
    authority: str

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "disposition": self.disposition,
            "message": self.message,
            "authority": self.authority,
        }


def normalize_findings(findings: Iterable) -> Tuple[AuthorizedFinding, ...]:
    """Normalize an iterable of duck-typed findings into a tuple of
    ``AuthorizedFinding``, preserving order."""
    normalized = []
    for f in findings:
        normalized.append(
            AuthorizedFinding(
                rule_id=getattr(f, "rule_id"),
                disposition=getattr(f, "disposition"),
                message=getattr(f, "message"),
                authority=getattr(f, "authority"),
            )
        )
    return tuple(normalized)


def findings_digest(findings: Iterable[AuthorizedFinding]) -> str:
    """SHA-256 (16 hex) of the canonical JSON of the normalized,
    order-preserved findings."""
    payload = [f.as_dict() for f in findings]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _derive_authorization_id(
    site_config_hash: str,
    ruleset_version: str,
    findings_dig: str,
    schema_version: str,
) -> str:
    """Deterministic 16-hex id binding config hash, ruleset version,
    findings digest, and schema version together."""
    material = "|".join(
        [site_config_hash, ruleset_version, findings_dig, schema_version]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Authorization token
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScreeningAuthorization:
    """Tamper-evident capability that the physics boundary requires.

    An instance exists only for a site whose preflight disposition permits
    screening (``proceed`` or ``warn``). Its identifiers bind it to the
    exact site config and ruleset it was minted from."""
    schema_version: str
    authorization_id: str
    site_config_hash: str
    ruleset_version: str
    disposition: str
    findings: Tuple[AuthorizedFinding, ...]
    findings_digest: str
    granted_utc: str

    @property
    def permits_execution(self) -> bool:
        return self.disposition in PERMITTING_DISPOSITIONS

    def warnings(self) -> Tuple[AuthorizedFinding, ...]:
        return tuple(f for f in self.findings if f.disposition == "warn")


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

def authorize_screening(site_config: dict, determination) -> ScreeningAuthorization:
    """Mint a ``ScreeningAuthorization`` from a site config and its
    preflight determination.

    Raises
    ------
    AuthorizationDeniedError
        if the determination's disposition does not permit screening.
    """
    disposition = getattr(determination, "disposition", None)
    findings = normalize_findings(getattr(determination, "findings", ()))

    if disposition not in PERMITTING_DISPOSITIONS:
        refusal_ids = [
            f.rule_id for f in findings if f.disposition == "refuse"
        ]
        raise AuthorizationDeniedError(
            f"Screening authorization denied: preflight disposition is "
            f"'{disposition}', which does not permit execution. "
            f"Refusing rule(s): {', '.join(refusal_ids) or '(none recorded)'}. "
            "A refused site is not authorizable."
        )

    site_config_hash = sha256_of_json_stable(site_config)
    dig = findings_digest(findings)
    auth_id = _derive_authorization_id(
        site_config_hash=site_config_hash,
        ruleset_version=PREFLIGHT_RULESET_VERSION,
        findings_dig=dig,
        schema_version=AUTHORIZATION_SCHEMA_VERSION,
    )

    return ScreeningAuthorization(
        schema_version=AUTHORIZATION_SCHEMA_VERSION,
        authorization_id=auth_id,
        site_config_hash=site_config_hash,
        ruleset_version=PREFLIGHT_RULESET_VERSION,
        disposition=disposition,
        findings=findings,
        findings_digest=dig,
        granted_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# ---------------------------------------------------------------------------
# Validation (the boundary check)
# ---------------------------------------------------------------------------

def validate_authorization(
    authorization: ScreeningAuthorization,
    site_config: dict,
) -> ScreeningAuthorization:
    """Validate an authorization against the site config it is being used with.

    This is the heavy check called once per run (by ``RunSession.__enter__``).

    Returns the authorization unchanged on success (for chaining).

    Raises
    ------
    AuthorizationMismatchError
        - not a ScreeningAuthorization
        - wrong schema_version
        - config hash mismatch (authorization minted for a different config)
        - stored findings_digest or authorization_id does not recompute
    AuthorizationDeniedError
        - disposition does not permit execution
    """
    if not isinstance(authorization, ScreeningAuthorization):
        raise AuthorizationMismatchError(
            "Object provided to the physics boundary is not a "
            "ScreeningAuthorization."
        )

    if authorization.schema_version != AUTHORIZATION_SCHEMA_VERSION:
        raise AuthorizationMismatchError(
            f"Authorization schema version "
            f"'{authorization.schema_version}' does not match the current "
            f"contract '{AUTHORIZATION_SCHEMA_VERSION}'."
        )

    expected_config_hash = sha256_of_json_stable(site_config)
    if authorization.site_config_hash != expected_config_hash:
        raise AuthorizationMismatchError(
            "Authorization is bound to a different site config "
            f"(authorized hash {authorization.site_config_hash}, "
            f"current config hash {expected_config_hash})."
        )

    recomputed_digest = findings_digest(authorization.findings)
    if authorization.findings_digest != recomputed_digest:
        raise AuthorizationMismatchError(
            "Authorization findings_digest does not match the stored "
            f"findings (stored {authorization.findings_digest}, "
            f"recomputed {recomputed_digest}). Token integrity failure."
        )

    recomputed_id = _derive_authorization_id(
        site_config_hash=authorization.site_config_hash,
        ruleset_version=authorization.ruleset_version,
        findings_dig=authorization.findings_digest,
        schema_version=authorization.schema_version,
    )
    if authorization.authorization_id != recomputed_id:
        raise AuthorizationMismatchError(
            "Authorization id does not match its bound fields "
            f"(stored {authorization.authorization_id}, recomputed "
            f"{recomputed_id}). Token integrity failure."
        )

    if not authorization.permits_execution:
        raise AuthorizationDeniedError(
            f"Authorization disposition '{authorization.disposition}' does "
            "not permit execution."
        )

    return authorization


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def authorization_to_dict(authorization: ScreeningAuthorization) -> dict:
    """Serialize an authorization to a JSON-safe dict."""
    return {
        "schema_version": authorization.schema_version,
        "authorization_id": authorization.authorization_id,
        "site_config_hash": authorization.site_config_hash,
        "ruleset_version": authorization.ruleset_version,
        "disposition": authorization.disposition,
        "findings_digest": authorization.findings_digest,
        "granted_utc": authorization.granted_utc,
        "findings": [f.as_dict() for f in authorization.findings],
    }


def authorization_from_dict(data: dict) -> ScreeningAuthorization:
    """Reconstruct a ``ScreeningAuthorization`` from its serialized dict.

    Does not validate; call ``validate_authorization`` afterward if the
    source is untrusted."""
    findings = tuple(
        AuthorizedFinding(
            rule_id=f["rule_id"],
            disposition=f["disposition"],
            message=f["message"],
            authority=f["authority"],
        )
        for f in data.get("findings", [])
    )
    return ScreeningAuthorization(
        schema_version=data["schema_version"],
        authorization_id=data["authorization_id"],
        site_config_hash=data["site_config_hash"],
        ruleset_version=data["ruleset_version"],
        disposition=data["disposition"],
        findings=findings,
        findings_digest=data["findings_digest"],
        granted_utc=data["granted_utc"],
    )
