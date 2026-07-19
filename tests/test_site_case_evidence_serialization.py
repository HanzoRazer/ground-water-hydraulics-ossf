"""
test_site_case_evidence_serialization.py
========================================

Round-trip and schema equivalence for ossf-site-case-1.1.0 evidence sections.

Run: python -m pytest tests/test_site_case_evidence_serialization.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import load_dbs, load_fixture_case, v1_dict
from core.contracts import (
    SCHEMA_VERSION,
    compute_evidence_digest,
    parse_site_case_dict,
    site_case_hash,
    site_case_to_dict,
    validate_evidence_layer,
    validate_site_case_schema,
)

SOILS, CONS = load_dbs()


def test_round_trip_preserves_evidence_and_bindings():
    case = parse_site_case_dict(
        v1_dict(), soil_database=SOILS, constituent_database=CONS
    )
    again = parse_site_case_dict(
        site_case_to_dict(case), soil_database=SOILS, constituent_database=CONS
    )
    assert site_case_to_dict(case) == site_case_to_dict(again)
    assert site_case_hash(case) == site_case_hash(again)
    assert compute_evidence_digest(case) == compute_evidence_digest(again)


def test_fixture_proceed_matches_schema():
    case = load_fixture_case("proceed")
    assert case.schema_version == SCHEMA_VERSION
    assert case.evidence
    assert case.field_bindings
    validate_site_case_schema(case)
    result = validate_evidence_layer(case)
    assert result.disposition == "proceed"


@pytest.mark.parametrize("name", ["proceed", "warn", "refuse"])
def test_migrated_fixtures_validate_evidence(name):
    case = load_fixture_case(name)
    # refuse fixture may still have complete evidence — gate is independent of SAD
    result = validate_evidence_layer(case)
    assert result.permits_preflight


def test_schema_file_is_1_1_0():
    from core.contracts.serialization import schema_path
    assert schema_path().name == "ossf-site-case-1.1.0.schema.json"
