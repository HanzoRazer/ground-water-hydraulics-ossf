"""
test_site_case_serialization.py
===============================

Canonical serialization, round-trip, hashing, and JSON-Schema tests for
``SiteCaseV1`` (OSSF-GW-002 §5.23 / §8.10-8.11 / §8.18).

The single canonical serializer (``site_case_to_dict`` / ``_canonical_json`` /
``site_case_hash``) is the one route used for hashing, schema validation,
artifact metadata, and round-trips — so its determinism and key-order
invariance are load-bearing for the whole governance model.

Run: python -m pytest tests/test_site_case_serialization.py -v
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import load_dbs, load_fixture_case, receptor, v1_dict
from core.contracts import (
    DispersivityMethod,
    TreatmentLevel,
    parse_site_case_dict,
    site_case_hash,
    site_case_to_canonical_json,
    site_case_to_dict,
    validate_site_case_schema,
)

SOILS, CONS = load_dbs()
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def _parse(cfg):
    return parse_site_case_dict(cfg, soil_database=SOILS, constituent_database=CONS)


# ---------------------------------------------------------------------------
# Determinism + round-trip
# ---------------------------------------------------------------------------

def test_serialization_is_deterministic():
    case = _parse(v1_dict())
    assert site_case_to_canonical_json(case) == site_case_to_canonical_json(case)


def test_enums_serialize_to_string_values():
    d = site_case_to_dict(_parse(v1_dict()))
    assert d["treatment"]["treatment_level"] == "secondary"
    assert d["physics"]["dispersivity_method"] == "epa_ssg"
    assert d["receptors"][0]["receptor_type"] == "private_well"


def test_tuples_serialize_to_arrays():
    d = site_case_to_dict(_parse(v1_dict()))
    assert isinstance(d["receptors"], list)
    assert isinstance(d["constituents"], list)
    assert isinstance(d["reporting"]["comparison_soil_ids"], list)


def test_round_trip_reparses_to_identical_case():
    case = _parse(v1_dict())
    reparsed = _parse(site_case_to_dict(case))
    assert site_case_to_dict(reparsed) == site_case_to_dict(case)
    assert site_case_hash(reparsed) == site_case_hash(case)


def test_canonical_json_is_valid_json_and_sorted():
    case = _parse(v1_dict())
    text = site_case_to_canonical_json(case)
    reparsed = json.loads(text)
    assert reparsed["site_id"] == "T-1"
    # sorted keys => the raw text has schema_version after receptors, etc.
    assert text == json.dumps(reparsed, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def test_same_case_same_hash():
    assert site_case_hash(_parse(v1_dict())) == site_case_hash(_parse(v1_dict()))


def test_key_order_does_not_change_hash():
    cfg = v1_dict()
    shuffled = dict(reversed(list(cfg.items())))
    shuffled["groundwater"] = dict(reversed(list(cfg["groundwater"].items())))
    assert site_case_hash(_parse(cfg)) == site_case_hash(_parse(shuffled))


def _mutations():
    base = _parse(v1_dict())
    yield "soil", dataclasses.replace(base, subsurface=dataclasses.replace(base.subsurface, soil_id="loam"))
    yield "gradient", dataclasses.replace(base, groundwater=dataclasses.replace(base.groundwater, hydraulic_gradient=0.02))
    yield "treatment", dataclasses.replace(base, treatment=dataclasses.replace(base.treatment, treatment_level=TreatmentLevel.ADVANCED_SECONDARY))
    yield "receptor_distance", dataclasses.replace(base, receptors=(receptor("well", "private_well", 99.0, "Well"),))
    yield "dispersivity", dataclasses.replace(base, physics=dataclasses.replace(base.physics, dispersivity_method=DispersivityMethod.XU_ECKSTEIN))


@pytest.mark.parametrize("name,mutated", list(_mutations()), ids=lambda v: v if isinstance(v, str) else "")
def test_material_field_change_changes_hash(name, mutated):
    base_hash = site_case_hash(_parse(v1_dict()))
    assert site_case_hash(mutated) != base_hash


def test_explicit_source_concentration_changes_hash():
    a = _parse(v1_dict())
    cfg = v1_dict()
    cfg["constituents"][0] = {"constituent_id": "e_coli", "role": "gating",
                              "source_concentration": 42.0, "source_basis": "measured"}
    b = _parse(cfg)
    assert site_case_hash(a) != site_case_hash(b)


# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------

def test_parsed_case_validates_against_schema():
    validate_site_case_schema(_parse(v1_dict()))  # raises on failure


@pytest.mark.parametrize("fixture", ["proceed", "warn", "refuse"])
def test_canonical_fixtures_validate_against_schema(fixture):
    validate_site_case_schema(load_fixture_case(fixture))


def test_config_example_validates_against_schema():
    raw = json.loads((REPO_ROOT / "config" / "site_example.json").read_text(encoding="utf-8"))
    validate_site_case_schema(raw)


def test_schema_rejects_unknown_field():
    import jsonschema
    d = site_case_to_dict(_parse(v1_dict()))
    d["bogus"] = 1
    with pytest.raises(jsonschema.ValidationError):
        validate_site_case_schema(d)


def test_schema_rejects_bad_enum():
    import jsonschema
    d = site_case_to_dict(_parse(v1_dict()))
    d["treatment"]["treatment_level"] = "tertiary"
    with pytest.raises(jsonschema.ValidationError):
        validate_site_case_schema(d)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
