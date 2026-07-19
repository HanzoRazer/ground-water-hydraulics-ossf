"""
test_schema_compatibility_matrix.py
===================================

Executable migration boundary for SiteCase schema versions (OSSF-GW-003):

* explicit ``ossf-site-case-1.0.0`` → rejected at parse
* unversioned legacy → converts via ``convert_legacy_site_config_to_v1``
* true ``ossf-site-case-1.1.0`` → parses and passes evidence + readiness

Run: python -m pytest tests/test_schema_compatibility_matrix.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import load_dbs, load_fixture_case, v1_dict
from core.contracts import (
    SCHEMA_VERSION,
    UnsupportedSchemaVersionError,
    convert_legacy_site_config_to_v1,
    parse_provenance_class,
    parse_site_case_dict,
    validate_evidence_layer,
)
from core.contracts.enums import ProvenanceClass
from core.readiness import assess_readiness

SOILS, CONS = load_dbs()
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def test_explicit_1_0_0_is_rejected_with_migration_message():
    raw = json.loads(
        (FIXTURES / "site_case_v1_0_legacy_rejected.json").read_text(encoding="utf-8")
    )
    assert raw["schema_version"] == "ossf-site-case-1.0.0"
    with pytest.raises(UnsupportedSchemaVersionError) as ei:
        parse_site_case_dict(raw, soil_database=SOILS, constituent_database=CONS)
    msg = str(ei.value)
    assert "Migrate explicitly" in msg or "no longer accepted" in msg
    assert "1.1.0" in msg


def test_unversioned_legacy_converts_to_1_1_0_and_passes_gates():
    raw = json.loads((FIXTURES / "site_case_legacy.json").read_text(encoding="utf-8"))
    assert "schema_version" not in raw
    case = convert_legacy_site_config_to_v1(
        raw, soil_database=SOILS, constituent_database=CONS
    )
    assert case.schema_version == SCHEMA_VERSION
    evidence = validate_evidence_layer(case)
    assert evidence.permits_preflight
    readiness = assess_readiness(case, evidence)
    assert readiness.permits_authorization
    assert readiness.evidence_digest == evidence.evidence_digest


def test_true_1_1_0_parses_and_passes_evidence_and_readiness():
    case = load_fixture_case("proceed")
    assert case.schema_version == "ossf-site-case-1.1.0"
    evidence = validate_evidence_layer(case)
    readiness = assess_readiness(case, evidence)
    assert evidence.disposition == "proceed"
    assert readiness.disposition == "ready"
    assert readiness.evidence_digest == evidence.evidence_digest


def test_v1_dict_helper_emits_1_1_0_compatible_payload():
    cfg = v1_dict()
    assert cfg["schema_version"] == SCHEMA_VERSION
    case = parse_site_case_dict(cfg, soil_database=SOILS, constituent_database=CONS)
    evidence = validate_evidence_layer(case)
    readiness = assess_readiness(case, evidence)
    assert evidence.permits_preflight and readiness.permits_authorization


def test_legacy_provenance_strings_map_when_allow_legacy():
    assert parse_provenance_class(
        "estimated", path="t", allow_legacy=True
    ) is ProvenanceClass.ASSUMED
    assert parse_provenance_class(
        "literature", path="t", allow_legacy=True
    ) is ProvenanceClass.DOCUMENTED


def test_strict_provenance_rejects_legacy_strings():
    from core.contracts import ContractValidationError
    with pytest.raises(ContractValidationError) as ei:
        parse_provenance_class(
            "estimated", path="t.source_basis", allow_legacy=False
        )
    assert "ProvenanceClass" in str(ei.value)
