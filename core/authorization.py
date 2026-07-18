"""
authorization.py
================

The screening **authorization contract**.

Where ``preflight.py`` decides *whether* a site is appropriate for the
screening model (its ``SiteAppropriatenessDetermination``), this module
turns an appropriate determination into an explicit, tamper-evident
**authorization token** that the physics layer requires before it will
run. Nothing downstream trusts a bare determination; it trusts a
validated ``ScreeningAuthorization``.

The doctrine (ADR-0001) is that a refused site must never reach the
physics engine. The authorization contract enforces that doctrine as a
*positive capability*: the engine boundary (``physics_registry``) will
only execute when handed an authorization that:

  1. carries a permitting disposition (``proceed`` or ``warn``),
  2. was minted from the *same* site config it is now being used with
     (config-binding, checked by recomputing the canonical-JSON hash),
  3. has not been tampered with (its ``findings_digest`` and
     ``authorization_id`` recompute to the stored values).

Refusal is not representable as an authorization: ``authorize_screening``
raises ``AuthorizationDeniedError`` for a refused determination. There is
no override flag, no ``force`` kwarg. This is deliberate — see
ADR-0001, "no bypass".

Schema version: ``screening-authorization-1.2.0``. Bump when the token's
shape or the derivation of its identifiers changes; the version is part
of the ``authorization_id`` derivation so a schema change necessarily
changes every id.

Design notes
------------
* Config hashing reuses ``governance.sha256_of_json_stable`` — there is
  exactly one canonical-JSON hash algorithm in this codebase.
* ``findings_digest`` is the SHA-256 (16 hex) of the canonical JSON of the
  normalized, order-preserved findings.
* ``evidence_digest`` binds the evidence[] + field_bindings[] + linked
  assumptions subset (OSSF-GW-003); it is passed explicitly via
  ``evidence_result`` and included in ``authorization_id`` derivation.
* ``readiness_digest`` binds the practitioner readiness assessment
  (OSSF-GW-004); passed via ``readiness_result`` and included in
  ``authorization_id`` derivation.
* ``authorization_id`` is a deterministic digest derived from
  ``site_config_hash + ruleset_version + findings_digest +
  evidence_digest + readiness_digest + schema_version``. It is
  reproducible for identical inputs and is NOT a substitute for the
  config or findings hashes — it binds them together.

Identity semantics
------------------
``authorization_id`` is the identity of the **authorization *decision***,
not of a single execution event: the same config + findings + ruleset +
schema deliberately yield the same id on every run. That is what makes an
authorization reproducible and auditable ("this decision was reached for
this config"). The identity of a particular **run** is carried separately
by the timestamps — ``ScreeningAuthorization.granted_utc`` (when the token
was minted) and ``MethodologyAttestation.generated_utc`` (when the artifact
was produced). Do not use ``authorization_id`` as a per-execution nonce.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Tuple

from .contracts.site_case_v1 import SiteCaseV1
from .governance import PREFLIGHT_RULESET_VERSION, sha256_of_json_stable


# ---------------------------------------------------------------------------
# Version anchor
# ---------------------------------------------------------------------------

AUTHORIZATION_SCHEMA_VERSION = "screening-authorization-1.2.0"


def _case_hash(case: SiteCaseV1) -> str:
    """Canonical hash of a validated ``SiteCaseV1``. The single governed
    hashing route (OSSF-GW-002 §4.12): the authorization binds to the
    normalized, serialized contract — never to a raw dictionary."""
    from .contracts.serialization import site_case_to_dict
    return sha256_of_json_stable(site_case_to_dict(case))


def _require_case(case) -> SiteCaseV1:
    if not isinstance(case, SiteCaseV1):
        raise AuthorizationError(
            "Governed authorization requires a validated SiteCaseV1, not a "
            f"raw {type(case).__name__}. Parse and validate input through "
            "core.contracts before authorization (OSSF-GW-002)."
        )
    return case

# Dispositions that permit the physics engine to run. Refusal is absent by
# construction: a refused site cannot be authorized.
PERMITTING_DISPOSITIONS: Tuple[str, ...] = ("proceed", "warn")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthorizationError(RuntimeError):
    """Base class for all authorization-contract failures."""


class AuthorizationDeniedError(AuthorizationError):
    """Raised when authorization cannot be granted because the preflight
    refused the site (or otherwise did not yield a permitting disposition).

    This is the positive-capability form of ADR-0001's refusal doctrine:
    a refused site produces no authorization, so the physics boundary has
    nothing to accept. There is no bypass."""


class AuthorizationMismatchError(AuthorizationError):
    """Raised when an authorization does not validate against the site
    config or has been tampered with: wrong schema version, config hash
    mismatch (the authorization was minted for a different config), or a
    recomputed digest/id that disagrees with the stored value."""


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
    """Normalize an iterable of duck-typed findings (``.rule_id``,
    ``.disposition``, ``.message``, ``.authority``) into a tuple of
    ``AuthorizedFinding``, preserving order.

    Public so the refusal path (which cannot mint a token) can still record
    the same normalized findings and digest in its artifact."""
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


# Backwards-compatible private alias (kept for existing internal callers).
_normalize_findings = normalize_findings


def findings_digest(findings: Iterable[AuthorizedFinding]) -> str:
    """SHA-256 (16 hex) of the canonical JSON of the normalized,
    order-preserved findings. Order is significant: the digest captures
    the exact sequence of findings the preflight produced."""
    payload = [f.as_dict() for f in findings]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _derive_authorization_id(
    site_config_hash: str,
    ruleset_version: str,
    findings_dig: str,
    evidence_dig: str,
    readiness_dig: str,
    schema_version: str,
) -> str:
    """Deterministic 16-hex id binding the config hash, ruleset version,
    findings digest, evidence digest, readiness digest, and schema version
    together. Reproducible for identical inputs. NOT a replacement for the
    individual hashes."""
    material = "|".join(
        [
            site_config_hash,
            ruleset_version,
            findings_dig,
            evidence_dig,
            readiness_dig,
            schema_version,
        ]
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
    exact site config, evidence digest, readiness digest, and ruleset it
    was minted from."""
    schema_version: str
    authorization_id: str
    site_config_hash: str
    ruleset_version: str
    disposition: str
    findings: Tuple[AuthorizedFinding, ...]
    findings_digest: str
    evidence_digest: str
    readiness_digest: str
    granted_utc: str

    @property
    def permits_execution(self) -> bool:
        return self.disposition in PERMITTING_DISPOSITIONS

    def warnings(self) -> Tuple[AuthorizedFinding, ...]:
        return tuple(f for f in self.findings if f.disposition == "warn")


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

def authorize_screening(
    case: SiteCaseV1, determination, evidence_result, readiness_result
) -> ScreeningAuthorization:
    """Mint a ``ScreeningAuthorization`` from a validated site case, its
    preflight determination, evidence-layer result, and readiness assessment.

    Parameters
    ----------
    case : the validated ``SiteCaseV1`` the preflight evaluated. The
        authorization binds to this case's canonical hash. Raw mappings are
        rejected (OSSF-GW-002 §5.15).
    determination : a ``SiteAppropriatenessDetermination`` (duck-typed:
        needs ``.disposition`` and ``.findings``).
    evidence_result : an ``EvidenceValidationResult`` (duck-typed: needs
        ``.evidence_digest`` and ``.permits_preflight``). Passed explicitly
        so the auth token binds the evidence digest that the driver gated on
        (OSSF-GW-003).
    readiness_result : a ``ReadinessAssessment`` (duck-typed: needs
        ``.readiness_digest`` and ``.permits_authorization``). Passed
        explicitly so the auth token binds the readiness digest (OSSF-GW-004).

    Raises
    ------
    AuthorizationError
        if ``case`` is not a validated ``SiteCaseV1``, or ``evidence_result``
        / ``readiness_result`` is missing or does not permit authorization.
    AuthorizationDeniedError
        if the determination's disposition does not permit screening
        (i.e., ``refuse``). No token is produced for a refused site.
    """
    _require_case(case)
    if evidence_result is None:
        raise AuthorizationError(
            "authorize_screening requires an EvidenceValidationResult; "
            "evidence must be validated before authorization (OSSF-GW-003)."
        )
    if not getattr(evidence_result, "permits_preflight", False):
        raise AuthorizationError(
            "authorize_screening refused: evidence_result does not permit "
            "preflight/authorization."
        )
    evidence_digest = getattr(evidence_result, "evidence_digest", None)
    if not evidence_digest or not isinstance(evidence_digest, str):
        raise AuthorizationError(
            "evidence_result.evidence_digest is required to mint an "
            "authorization (OSSF-GW-003)."
        )

    if readiness_result is None:
        raise AuthorizationError(
            "authorize_screening requires a ReadinessAssessment; "
            "practitioner readiness must be assessed before authorization "
            "(OSSF-GW-004)."
        )
    if not getattr(readiness_result, "permits_authorization", False):
        raise AuthorizationError(
            "authorize_screening refused: readiness_result does not permit "
            "authorization "
            f"(disposition={getattr(readiness_result, 'disposition', None)!r})."
        )
    readiness_digest = getattr(readiness_result, "readiness_digest", None)
    if not readiness_digest or not isinstance(readiness_digest, str):
        raise AuthorizationError(
            "readiness_result.readiness_digest is required to mint an "
            "authorization (OSSF-GW-004)."
        )
    # Cross-check: readiness must have been assessed against the same evidence.
    ready_evidence = getattr(readiness_result, "evidence_digest", None)
    if ready_evidence and ready_evidence != evidence_digest:
        raise AuthorizationError(
            "readiness_result.evidence_digest does not match "
            "evidence_result.evidence_digest; refusing to authorize."
        )

    disposition = getattr(determination, "disposition", None)
    findings = _normalize_findings(getattr(determination, "findings", ()))

    if disposition not in PERMITTING_DISPOSITIONS:
        refusal_ids = [
            f.rule_id for f in findings if f.disposition == "refuse"
        ]
        raise AuthorizationDeniedError(
            f"Screening authorization denied: preflight disposition is "
            f"'{disposition}', which does not permit execution. "
            f"Refusing rule(s): {', '.join(refusal_ids) or '(none recorded)'}. "
            "A refused site is not authorizable; escalate per ADR-0001."
        )

    site_config_hash = _case_hash(case)
    dig = findings_digest(findings)
    auth_id = _derive_authorization_id(
        site_config_hash=site_config_hash,
        ruleset_version=PREFLIGHT_RULESET_VERSION,
        findings_dig=dig,
        evidence_dig=evidence_digest,
        readiness_dig=readiness_digest,
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
        evidence_digest=evidence_digest,
        readiness_digest=readiness_digest,
        granted_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# ---------------------------------------------------------------------------
# Validation (the boundary check)
# ---------------------------------------------------------------------------

def ensure_execution_permitted(authorization) -> ScreeningAuthorization:
    """Lightweight guard for the innermost engine call (``evaluate``).

    Confirms that a permitting, schema-correct ``ScreeningAuthorization`` is
    present, so the engine cannot run tokenless. It deliberately does NOT
    perform config-binding — that is the boundary's responsibility
    (``validate_authorization``, called once by ``run_authorized_engine``).
    Its job is to make direct, unauthorized calls to ``evaluate`` fail.

    Raises
    ------
    AuthorizationError          if no ScreeningAuthorization was supplied.
    AuthorizationMismatchError  if the token's schema version is wrong.
    AuthorizationDeniedError    if the token does not permit execution.
    """
    if not isinstance(authorization, ScreeningAuthorization):
        raise AuthorizationError(
            "Physics engine invoked without a ScreeningAuthorization. The "
            "engine only runs on sites authorized through the preflight -> "
            "authorize_screening -> run_authorized_engine path (ADR-0001)."
        )
    if authorization.schema_version != AUTHORIZATION_SCHEMA_VERSION:
        raise AuthorizationMismatchError(
            f"Authorization schema version '{authorization.schema_version}' "
            f"does not match the current contract "
            f"'{AUTHORIZATION_SCHEMA_VERSION}'."
        )
    if not authorization.permits_execution:
        raise AuthorizationDeniedError(
            f"Authorization disposition '{authorization.disposition}' does "
            "not permit execution."
        )
    return authorization


def validate_authorization(
    authorization: ScreeningAuthorization, case: SiteCaseV1
) -> ScreeningAuthorization:
    """Validate an authorization against the validated ``SiteCaseV1`` it is
    being used with. This is the check the physics boundary performs before
    running.

    Returns the authorization unchanged on success (for chaining).

    Raises
    ------
    AuthorizationMismatchError
        - wrong ``schema_version``
        - the recomputed config hash differs (authorization was minted
          for a different config — config-binding violation)
        - the stored ``findings_digest`` or ``authorization_id`` does not
          recompute from the stored fields (tamper detection)
    AuthorizationDeniedError
        - the authorization's disposition does not permit execution
          (should be impossible for a well-formed token, but enforced
          defensively so a hand-built token cannot smuggle a non-permitting
          disposition past the boundary).
    """
    if not isinstance(authorization, ScreeningAuthorization):
        raise AuthorizationMismatchError(
            "Object provided to the physics boundary is not a "
            "ScreeningAuthorization."
        )
    _require_case(case)

    if authorization.schema_version != AUTHORIZATION_SCHEMA_VERSION:
        raise AuthorizationMismatchError(
            f"Authorization schema version "
            f"'{authorization.schema_version}' does not match the current "
            f"contract '{AUTHORIZATION_SCHEMA_VERSION}'."
        )

    # Config binding: the authorization must have been minted from this
    # exact validated case.
    expected_config_hash = _case_hash(case)
    if authorization.site_config_hash != expected_config_hash:
        raise AuthorizationMismatchError(
            "Authorization is bound to a different site config "
            f"(authorized hash {authorization.site_config_hash}, "
            f"current config hash {expected_config_hash}). The physics "
            "engine will not run against a config it was not authorized for."
        )

    # Tamper detection: findings digest must recompute from stored findings.
    recomputed_digest = findings_digest(authorization.findings)
    if authorization.findings_digest != recomputed_digest:
        raise AuthorizationMismatchError(
            "Authorization findings_digest does not match the stored "
            f"findings (stored {authorization.findings_digest}, "
            f"recomputed {recomputed_digest}). Token integrity failure."
        )

    # Tamper detection: evidence digest must match the case's evidence layer.
    from .contracts.evidence_validation import compute_evidence_digest
    expected_evidence_digest = compute_evidence_digest(case)
    auth_evidence = getattr(authorization, "evidence_digest", None)
    if auth_evidence != expected_evidence_digest:
        raise AuthorizationMismatchError(
            "Authorization evidence_digest does not match the site case "
            f"(authorized {auth_evidence}, current {expected_evidence_digest}). "
            "The physics engine will not run against evidence it was not "
            "authorized for."
        )

    # Tamper detection: readiness digest must be present and recompute into id.
    auth_readiness = getattr(authorization, "readiness_digest", None)
    if not auth_readiness or not isinstance(auth_readiness, str):
        raise AuthorizationMismatchError(
            "Authorization is missing readiness_digest (OSSF-GW-004)."
        )

    # Tamper detection: id must recompute from the bound fields.
    recomputed_id = _derive_authorization_id(
        site_config_hash=authorization.site_config_hash,
        ruleset_version=authorization.ruleset_version,
        findings_dig=authorization.findings_digest,
        evidence_dig=authorization.evidence_digest,
        readiness_dig=authorization.readiness_digest,
        schema_version=authorization.schema_version,
    )
    if authorization.authorization_id != recomputed_id:
        raise AuthorizationMismatchError(
            "Authorization id does not match its bound fields "
            f"(stored {authorization.authorization_id}, recomputed "
            f"{recomputed_id}). Token integrity failure."
        )

    # Defensive: a well-formed token always permits, but never trust the
    # disposition without checking it.
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
    """Serialize an authorization to a JSON-safe dict for embedding in
    output artifacts."""
    return {
        "schema_version": authorization.schema_version,
        "authorization_id": authorization.authorization_id,
        "site_config_hash": authorization.site_config_hash,
        "ruleset_version": authorization.ruleset_version,
        "disposition": authorization.disposition,
        "findings_digest": authorization.findings_digest,
        "evidence_digest": authorization.evidence_digest,
        "readiness_digest": authorization.readiness_digest,
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
        evidence_digest=data["evidence_digest"],
        readiness_digest=data["readiness_digest"],
        granted_utc=data["granted_utc"],
    )
