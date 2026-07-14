"""
test_site_case_validation.py
============================

Parser-level structural, cross-field, database-reference, and engine-
compatibility validation for ``SiteCaseV1`` (OSSF-GW-002 §5.22 / §8.2-8.9).

Everything here goes through the canonical ``parse_site_case_dict`` path with
the real soil / constituent databases, so it mirrors exactly what the driver
does before preflight. Failures raise typed exceptions carrying field-pathed
``FieldValidationError`` records.

Run: python -m pytest tests/test_site_case_validation.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import load_dbs, v1_dict
from core.contracts import (
    ContractValidationError,
    CrossFieldValidationError,
    SiteCaseV1,
    UnknownConstituentError,
    UnknownEngineError,
    UnknownSoilError,
    UnsupportedSchemaVersionError,
    parse_site_case_dict,
)

SOILS, CONS = load_dbs()


def _parse(cfg: dict) -> SiteCaseV1:
    return parse_site_case_dict(cfg, soil_database=SOILS, constituent_database=CONS)


def _paths(exc: ContractValidationError) -> set:
    return {e.path for e in exc.errors}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_case_parses():
    case = _parse(v1_dict())
    assert isinstance(case, SiteCaseV1)
    assert case.site_id == "T-1"


def test_xu_eckstein_is_compatible_with_ogata_banks():
    cfg = v1_dict()
    cfg["physics"]["dispersivity_method"] = "xu_eckstein"
    assert _parse(cfg).physics.dispersivity_method.value == "xu_eckstein"


# ---------------------------------------------------------------------------
# Schema-version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [None, "", "  ", "ossf-site-case-2.0.0",
                                 "ossf-result-1.0.0"])
def test_bad_schema_versions_rejected(bad):
    cfg = v1_dict()
    if bad is None:
        del cfg["schema_version"]
    else:
        cfg["schema_version"] = bad
    with pytest.raises(UnsupportedSchemaVersionError):
        _parse(cfg)


# ---------------------------------------------------------------------------
# Required-field / structural
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("section", ["project", "regulatory_location", "treatment",
                                     "source", "subsurface", "groundwater",
                                     "receptors", "constituents", "physics"])
def test_missing_required_section_reports_field_path(section):
    cfg = v1_dict()
    del cfg[section]
    with pytest.raises(ContractValidationError) as ei:
        _parse(cfg)
    assert any(section in p for p in _paths(ei.value))


def test_unknown_top_level_field_rejected():
    cfg = v1_dict()
    cfg["bogus_field"] = 1
    with pytest.raises(ContractValidationError) as ei:
        _parse(cfg)
    assert any("bogus_field" in p for p in _paths(ei.value))


def test_multiple_errors_accumulate_in_one_pass():
    cfg = v1_dict()
    cfg["site_id"] = ""                       # bad id
    del cfg["treatment"]                       # missing section
    cfg["groundwater"]["hydraulic_gradient"] = "oops"  # wrong type
    with pytest.raises(ContractValidationError) as ei:
        _parse(cfg)
    assert len(ei.value.errors) >= 3


# ---------------------------------------------------------------------------
# Numeric validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["not_a_number", None])
def test_nonnumeric_gradient_rejected(value):
    cfg = v1_dict()
    cfg["groundwater"]["hydraulic_gradient"] = value
    with pytest.raises(ContractValidationError):
        _parse(cfg)


def test_zero_depth_rejected():
    cfg = v1_dict()
    cfg["groundwater"]["depth_to_groundwater_m"] = 0
    with pytest.raises(ContractValidationError):
        _parse(cfg)


def test_negative_gradient_rejected():
    cfg = v1_dict()
    cfg["groundwater"]["hydraulic_gradient"] = -0.01
    with pytest.raises(ContractValidationError):
        _parse(cfg)


def test_negative_receptor_distance_rejected():
    cfg = v1_dict()
    cfg["receptors"][0]["distance_m"] = -5.0
    with pytest.raises(ContractValidationError):
        _parse(cfg)


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

def test_narrative_treatment_string_rejected():
    cfg = v1_dict()
    cfg["treatment"]["treatment_level"] = "Class I Aerobic + Disinfection"
    with pytest.raises(ContractValidationError):
        _parse(cfg)


def test_unknown_receptor_type_rejected():
    cfg = v1_dict()
    cfg["receptors"][0]["receptor_type"] = "lake"
    with pytest.raises(ContractValidationError):
        _parse(cfg)


def test_unknown_dispersivity_method_rejected():
    cfg = v1_dict()
    cfg["physics"]["dispersivity_method"] = "made_up"
    with pytest.raises(ContractValidationError):
        _parse(cfg)


# ---------------------------------------------------------------------------
# Identifier uniqueness
# ---------------------------------------------------------------------------

def test_duplicate_receptor_ids_rejected():
    cfg = v1_dict()
    cfg["receptors"][1]["receptor_id"] = cfg["receptors"][0]["receptor_id"]
    with pytest.raises(CrossFieldValidationError):
        _parse(cfg)


def test_duplicate_constituent_ids_rejected():
    cfg = v1_dict()
    cfg["constituents"][1]["constituent_id"] = cfg["constituents"][0]["constituent_id"]
    with pytest.raises(CrossFieldValidationError):
        _parse(cfg)


# ---------------------------------------------------------------------------
# Treatment / disinfection consistency
# ---------------------------------------------------------------------------

def test_disinfection_method_without_status_rejected():
    cfg = v1_dict()
    cfg["treatment"]["disinfection_status"] = "none"
    cfg["treatment"]["disinfection_method"] = "chlorine"
    with pytest.raises(CrossFieldValidationError):
        _parse(cfg)


def test_disinfected_without_method_rejected():
    cfg = v1_dict()
    cfg["treatment"]["disinfection_status"] = "disinfected"
    cfg["treatment"]["disinfection_method"] = "none"
    with pytest.raises(CrossFieldValidationError):
        _parse(cfg)


# ---------------------------------------------------------------------------
# Source concentration (explicit XOR governed default)
# ---------------------------------------------------------------------------

def test_missing_source_concentration_rejected():
    cfg = v1_dict()
    cfg["constituents"][0] = {"constituent_id": "e_coli", "role": "gating"}
    with pytest.raises(CrossFieldValidationError):
        _parse(cfg)


def test_ambiguous_source_concentration_rejected():
    cfg = v1_dict()
    cfg["constituents"][0] = {
        "constituent_id": "e_coli", "role": "gating",
        "source_concentration": 100.0, "use_governed_default": True,
    }
    with pytest.raises(CrossFieldValidationError):
        _parse(cfg)


def test_explicit_source_concentration_accepted():
    cfg = v1_dict()
    cfg["constituents"][0] = {
        "constituent_id": "e_coli", "role": "gating",
        "source_concentration": 100.0, "source_basis": "measured",
    }
    case = _parse(cfg)
    assert case.constituents[0].source_concentration == 100.0


# ---------------------------------------------------------------------------
# Database references
# ---------------------------------------------------------------------------

def test_unknown_soil_rejected_before_preflight():
    cfg = v1_dict()
    cfg["subsurface"]["soil_id"] = "unobtanium"
    with pytest.raises(UnknownSoilError):
        _parse(cfg)


def test_unknown_comparison_soil_rejected():
    cfg = v1_dict()
    cfg["reporting"]["comparison_soil_ids"] = ["not_a_soil"]
    with pytest.raises(UnknownSoilError):
        _parse(cfg)


def test_unknown_constituent_rejected():
    cfg = v1_dict()
    cfg["constituents"][0]["constituent_id"] = "unobtanium"
    with pytest.raises(UnknownConstituentError):
        _parse(cfg)


# ---------------------------------------------------------------------------
# Engine registration
# ---------------------------------------------------------------------------

def test_unknown_engine_rejected():
    cfg = v1_dict()
    cfg["physics"]["engine"] = "no_such_engine"
    with pytest.raises(UnknownEngineError):
        _parse(cfg)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
