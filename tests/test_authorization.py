"""
test_authorization.py
======================

Unit, serialization, and invariant tests for the screening authorization
contract (core/authorization.py), now binding to a validated ``SiteCaseV1``
(OSSF-GW-002):

  * a refused site is not authorizable (no token, ever);
  * a token is bound to the exact validated case it was minted from
    (canonical contract hash);
  * a token is tamper-evident (digest + id recompute);
  * ids and digests are deterministic for identical inputs;
  * raw mappings are rejected at the governed boundary.

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

from _v1_helpers import evidence_result_for, make_case
from core.contracts import site_case_hash
from core.preflight import RuleFinding, SiteAppropriatenessDetermination
from core.governance import PREFLIGHT_RULESET_VERSION
from core.authorization import (
    AUTHORIZATION_SCHEMA_VERSION,
    PERMITTING_DISPOSITIONS,
    AuthorizationDeniedError,
    AuthorizationError,
    AuthorizationMismatchError,
    AuthorizedFinding,
    authorize_screening,
    validate_authorization,
    findings_digest,
    authorization_to_dict,
    authorization_from_dict,
)


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




def _auth(case, sad):
    return authorize_screening(case, sad, evidence_result_for(case))

# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

def test_proceed_yields_permitting_authorization():
    auth = _auth(make_case(), _proceed_sad())
    assert auth.disposition == "proceed"
    assert auth.permits_execution is True
    assert auth.schema_version == AUTHORIZATION_SCHEMA_VERSION
    assert auth.ruleset_version == PREFLIGHT_RULESET_VERSION
    assert len(auth.authorization_id) == 16
    assert len(auth.findings_digest) == 16
    assert len(auth.evidence_digest) == 16


def test_warn_yields_permitting_authorization_with_warnings():
    auth = _auth(make_case(), _warn_sad())
    assert auth.disposition == "warn"
    assert auth.permits_execution is True
    warns = auth.warnings()
    assert len(warns) == 1 and warns[0].rule_id == "SAD-005"


def test_refuse_is_not_authorizable():
    with pytest.raises(AuthorizationDeniedError) as ei:
        _auth(make_case(), _refuse_sad())
    assert "SAD-001" in str(ei.value)


def test_all_permitting_dispositions_are_authorizable():
    assert set(PERMITTING_DISPOSITIONS) == {"proceed", "warn"}


def test_config_hash_matches_canonical_contract_hash():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    assert auth.site_config_hash == site_case_hash(case)


def test_raw_mapping_is_rejected_at_authorization_boundary():
    with pytest.raises(AuthorizationError):
        authorize_screening({"site_id": "X"}, _proceed_sad(), evidence_result_for(make_case()))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Determinism / invariants
# ---------------------------------------------------------------------------

def test_authorization_id_and_digest_are_deterministic():
    a1 = _auth(make_case(), _proceed_sad())
    a2 = _auth(make_case(), _proceed_sad())
    assert a1.authorization_id == a2.authorization_id
    assert a1.findings_digest == a2.findings_digest


def test_authorization_id_changes_with_config():
    a1 = _auth(make_case(soil_id="clay_loam"), _proceed_sad())
    a2 = _auth(make_case(soil_id="loam", gradient=0.02), _proceed_sad())
    assert a1.authorization_id != a2.authorization_id
    assert a1.site_config_hash != a2.site_config_hash


def test_authorization_id_changes_with_findings():
    a1 = _auth(make_case(), _proceed_sad())
    a2 = _auth(make_case(), _warn_sad())
    assert a1.findings_digest != a2.findings_digest
    assert a1.authorization_id != a2.authorization_id


def test_findings_digest_is_order_sensitive():
    f1 = [
        AuthorizedFinding("SAD-001", "proceed", "a", "auth"),
        AuthorizedFinding("SAD-002", "proceed", "b", "auth"),
    ]
    f2 = list(reversed(f1))
    assert findings_digest(f1) != findings_digest(f2)


def test_hash_is_construction_order_independent():
    """Canonical serialization means two independently-built identical cases
    hash the same and cross-validate."""
    case_a = make_case()
    case_b = make_case()
    auth = _auth(case_a, _proceed_sad())
    assert validate_authorization(auth, case_b) is auth


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_success_returns_authorization():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    assert validate_authorization(auth, case) is auth


def test_validate_rejects_config_mismatch():
    auth = _auth(make_case(), _proceed_sad())
    other = make_case(soil_id="sand", gradient=0.05)
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(auth, other)


def test_validate_rejects_schema_mismatch():
    auth = _auth(make_case(), _proceed_sad())
    tampered = dataclasses.replace(auth, schema_version="screening-authorization-9.9.9")
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(tampered, make_case())


def test_validate_rejects_tampered_findings_digest():
    auth = _auth(make_case(), _proceed_sad())
    tampered = dataclasses.replace(auth, findings_digest="0000000000000000")
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(tampered, make_case())


def test_validate_rejects_tampered_evidence_digest():
    case = make_case()
    auth = _auth(case, _proceed_sad())
    tampered = dataclasses.replace(auth, evidence_digest="0000000000000000")
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(tampered, case)


def test_validate_rejects_tampered_id():
    auth = _auth(make_case(), _proceed_sad())
    tampered = dataclasses.replace(auth, authorization_id="deadbeefdeadbeef")
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(tampered, make_case())


def test_validate_rejects_smuggled_nonpermitting_disposition():
    auth = _auth(make_case(), _proceed_sad())
    smuggled = dataclasses.replace(auth, disposition="refuse")
    with pytest.raises(AuthorizationDeniedError):
        validate_authorization(smuggled, make_case())


def test_validate_rejects_non_authorization_object():
    with pytest.raises(AuthorizationMismatchError):
        validate_authorization(object(), make_case())  # type: ignore[arg-type]


def test_validate_rejects_raw_mapping_case():
    auth = _auth(make_case(), _proceed_sad())
    with pytest.raises(AuthorizationError):
        validate_authorization(auth, {"site_id": "X"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_serialization_round_trip_preserves_identity_and_validates():
    case = make_case()
    auth = _auth(case, _warn_sad())
    data = authorization_to_dict(auth)
    restored = authorization_from_dict(data)
    assert restored == auth
    validate_authorization(restored, case)


def test_to_dict_is_json_safe_and_complete():
    import json
    auth = _auth(make_case(), _warn_sad())
    data = authorization_to_dict(auth)
    reparsed = json.loads(json.dumps(data))
    assert reparsed["authorization_id"] == auth.authorization_id
    assert reparsed["disposition"] == "warn"
    assert reparsed["evidence_digest"] == auth.evidence_digest
    assert isinstance(reparsed["findings"], list)
    assert reparsed["findings"][0]["rule_id"] == "SAD-001"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
