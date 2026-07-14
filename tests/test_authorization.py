"""
test_authorization.py
======================

Unit, serialization, and invariant tests for the screening authorization
contract (core/authorization.py).

These pin the contract that the physics boundary relies on:

  * a refused site is not authorizable (no token, ever);
  * a token is bound to the exact config it was minted from;
  * a token is tamper-evident (digest + id recompute);
  * ids and digests are deterministic for identical inputs.

Run: python -m pytest tests/test_authorization.py -v
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.preflight import RuleFinding, SiteAppropriatenessDetermination
from core.governance import PREFLIGHT_RULESET_VERSION, sha256_of_json_stable
from core.authorization import (
    AUTHORIZATION_SCHEMA_VERSION,
    PERMITTING_DISPOSITIONS,
    AuthorizationDeniedError,
    AuthorizationMismatchError,
    AuthorizedFinding,
    ScreeningAuthorization,
    authorize_screening,
    validate_authorization,
    findings_digest,
    authorization_to_dict,
    authorization_from_dict,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _proceed_sad() -> SiteAppropriatenessDetermination:
    return SiteAppropriatenessDetermination(
        disposition="proceed",
        findings=[
            RuleFinding("SAD-001", "proceed", "Not in EARZ.", "30 TAC 285.40-42"),
            RuleFinding("SAD-004", "proceed", "clay_loam ok.", "Ch. 285.30(a)(3)"),
        ],
    )


def _warn_sad() -> SiteAppropriatenessDetermination:
    return SiteAppropriatenessDetermination(
        disposition="warn",
        findings=[
            RuleFinding("SAD-001", "proceed", "Not in EARZ.", "30 TAC 285.40-42"),
            RuleFinding("SAD-005", "warn", "Receptor at 3.0 m.", "EPA SSG 1996"),
        ],
    )


def _refuse_sad() -> SiteAppropriatenessDetermination:
    return SiteAppropriatenessDetermination(
        disposition="refuse",
        findings=[
            RuleFinding("SAD-001", "refuse", "In EARZ.", "30 TAC 285.40-42"),
            RuleFinding("SAD-005", "warn", "Receptor at 3.0 m.", "EPA SSG 1996"),
        ],
    )


def _cfg(**overrides) -> dict:
    base = {
        "project": {"site_id": "EX-001"},
        "subsurface": {"soil_type": "clay_loam", "hydraulic_gradient": 0.01},
        "physics": {"engine": "ogata_banks_1d"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

def test_proceed_yields_permitting_authorization():
    auth = authorize_screening(_cfg(), _proceed_sad())
    assert auth.disposition == "proceed"
    assert auth.permits_execution is True
    assert auth.schema_version == AUTHORIZATION_SCHEMA_VERSION
    assert auth.ruleset_version == PREFLIGHT_RULESET_VERSION
    assert len(auth.authorization_id) == 16
    assert len(auth.findings_digest) == 16


def test_warn_yields_permitting_authorization_with_warnings():
    auth = authorize_screening(_cfg(), _warn_sad())
    assert auth.disposition == "warn"
    assert auth.permits_execution is True
    warns = auth.warnings()
    assert len(warns) == 1 and warns[0].rule_id == "SAD-005"


def test_refuse_is_not_authorizable():
    with pytest.raises(AuthorizationDeniedError) as ei:
        authorize_screening(_cfg(), _refuse_sad())
    # The denial message should name the refusing rule.
    assert "SAD-001" in str(ei.value)


def test_all_permitting_dispositions_are_authorizable():
    assert set(PERMITTING_DISPOSITIONS) == {"proceed", "warn"}


def test_config_hash_matches_governance_algorithm():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    assert auth.site_config_hash == sha256_of_json_stable(cfg)


# ---------------------------------------------------------------------------
# Determinism / invariants
# ---------------------------------------------------------------------------

def test_authorization_id_and_digest_are_deterministic():
    a1 = authorize_screening(_cfg(), _proceed_sad())
    a2 = authorize_screening(_cfg(), _proceed_sad())
    assert a1.authorization_id == a2.authorization_id
    assert a1.findings_digest == a2.findings_digest
    # granted_utc may differ; identity is not time-dependent.


def test_authorization_id_changes_with_config():
    a1 = authorize_screening(_cfg(), _proceed_sad())
    a2 = authorize_screening(
        _cfg(subsurface={"soil_type": "loam", "hydraulic_gradient": 0.02}),
        _proceed_sad(),
    )
    assert a1.authorization_id != a2.authorization_id
    assert a1.site_config_hash != a2.site_config_hash


def test_authorization_id_changes_with_findings():
    a1 = authorize_screening(_cfg(), _proceed_sad())
    a2 = authorize_screening(_cfg(), _warn_sad())
    assert a1.findings_digest != a2.findings_digest
    assert a1.authorization_id != a2.authorization_id


def test_findings_digest_is_order_sensitive():
    f1 = [
        AuthorizedFinding("SAD-001", "proceed", "a", "auth"),
        AuthorizedFinding("SAD-002", "proceed", "b", "auth"),
    ]
    f2 = list(reversed(f1))
    assert findings_digest(f1) != findings_digest(f2)


def test_config_hash_is_key_order_independent():
    """Canonical-JSON hashing means reordering keys does not change the
    binding — the authorization still validates."""
    cfg_a = {"a": 1, "b": {"x": 1, "y": 2}}
    cfg_b = {"b": {"y": 2, "x": 1}, "a": 1}
    auth = authorize_screening(cfg_a, _proceed_sad())
    # Validates against a semantically identical, reordered config.
    validate_authorization(auth, cfg_b)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_success_returns_authorization():
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())
    assert validate_authorization(auth, cfg) is auth


def test_validate_rejects_config_mismatch():
    auth = authorize_screening(_cfg(), _proceed_sad())
    other = _cfg(subsurface={"soil_type": "sand", "hydraulic_gradient": 0.5})
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(auth, other)


def test_validate_rejects_schema_mismatch():
    auth = authorize_screening(_cfg(), _proceed_sad())
    tampered = dataclasses.replace(auth, schema_version="screening-authorization-9.9.9")
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(tampered, _cfg())


def test_validate_rejects_tampered_findings_digest():
    auth = authorize_screening(_cfg(), _proceed_sad())
    tampered = dataclasses.replace(auth, findings_digest="0000000000000000")
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(tampered, _cfg())


def test_validate_rejects_tampered_id():
    auth = authorize_screening(_cfg(), _proceed_sad())
    tampered = dataclasses.replace(auth, authorization_id="deadbeefdeadbeef")
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(tampered, _cfg())


def test_validate_rejects_smuggled_nonpermitting_disposition():
    """A hand-built token whose disposition field says 'refuse' but whose
    hashes are otherwise consistent must still be rejected at the boundary
    (id derivation does not include disposition, so the defensive check
    matters)."""
    auth = authorize_screening(_cfg(), _proceed_sad())
    smuggled = dataclasses.replace(auth, disposition="refuse")
    with pytest.raises(AuthorizationDeniedError):
        validate_authorization(smuggled, _cfg())


def test_validate_rejects_non_authorization_object():
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(object(), _cfg())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_serialization_round_trip_preserves_identity_and_validates():
    cfg = _cfg()
    auth = authorize_screening(cfg, _warn_sad())
    data = authorization_to_dict(auth)
    restored = authorization_from_dict(data)
    assert restored == auth
    # A round-tripped token still validates against the original config.
    validate_authorization(restored, cfg)


def test_to_dict_is_json_safe_and_complete():
    import json
    auth = authorize_screening(_cfg(), _warn_sad())
    data = authorization_to_dict(auth)
    # Round-trips through JSON without error.
    reparsed = json.loads(json.dumps(data))
    assert reparsed["authorization_id"] == auth.authorization_id
    assert reparsed["disposition"] == "warn"
    assert isinstance(reparsed["findings"], list)
    assert reparsed["findings"][0]["rule_id"] == "SAD-001"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
