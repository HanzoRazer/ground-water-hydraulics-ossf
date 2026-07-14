"""
test_site_case_v1.py
====================

Local (record-level) construction and validation tests for the immutable
``SiteCaseV1`` contract and its nested records (OSSF-GW-002 §5.21 / §8.1).

These tests exercise the fail-fast ``__post_init__`` validation that each
record performs at construction time: type coercion (str -> enum, int ->
float), immutability, and per-field range/format checks. Multi-error
accumulation with field paths is the parser's job and is covered in
``test_site_case_validation.py``.

Run: python -m pytest tests/test_site_case_v1.py -v
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import constituent, make_case, receptor
from core.contracts import (
    SCHEMA_VERSION,
    ConstituentRole,
    ContractValidationError,
    DisinfectionMethod,
    DisinfectionStatus,
    DispersivityMethod,
    GroundwaterConfiguration,
    ProjectMetadata,
    ReceptorDefinition,
    ReceptorType,
    SourceConfiguration,
    SubsurfaceConfiguration,
    TreatmentConfiguration,
    TreatmentLevel,
    UnsupportedSchemaVersionError,
)


# ---------------------------------------------------------------------------
# Valid construction + normalization
# ---------------------------------------------------------------------------

def test_make_case_builds_a_valid_contract():
    case = make_case()
    assert case.schema_version == SCHEMA_VERSION
    assert case.site_id == "TEST-1"
    assert case.treatment.treatment_level == TreatmentLevel.SECONDARY
    assert case.physics.dispersivity_method == DispersivityMethod.EPA_SSG


def test_string_values_coerce_to_enums():
    t = TreatmentConfiguration(
        treatment_level="advanced_secondary",
        disinfection_status="disinfected",
        disinfection_method="uv",
    )
    assert t.treatment_level is TreatmentLevel.ADVANCED_SECONDARY
    assert t.disinfection_status is DisinfectionStatus.DISINFECTED
    assert t.disinfection_method is DisinfectionMethod.UV


def test_int_numeric_fields_normalize_to_float():
    g = GroundwaterConfiguration(depth_to_groundwater_m=5, hydraulic_gradient=0)
    assert isinstance(g.depth_to_groundwater_m, float)
    assert isinstance(g.hydraulic_gradient, float)
    assert g.hydraulic_gradient == 0.0  # zero gradient permitted (SAD warns)


def test_receptor_list_coerces_to_tuple_and_is_immutable():
    case = make_case()
    assert isinstance(case.receptors, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        case.site_id = "OTHER"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

def test_wrong_schema_version_rejected():
    with pytest.raises(UnsupportedSchemaVersionError):
        dataclasses.replace(make_case(), schema_version="ossf-site-case-2.0.0")


# ---------------------------------------------------------------------------
# Local field validation (fail-fast)
# ---------------------------------------------------------------------------

def test_blank_site_id_rejected():
    with pytest.raises(ContractValidationError):
        make_case(site_id="")


def test_bad_stable_id_characters_rejected():
    with pytest.raises(ContractValidationError):
        make_case(site_id="has spaces")


def test_nonpositive_depth_rejected():
    with pytest.raises(ContractValidationError):
        GroundwaterConfiguration(depth_to_groundwater_m=0.0, hydraulic_gradient=0.01)


def test_negative_gradient_rejected_at_contract():
    with pytest.raises(ContractValidationError):
        GroundwaterConfiguration(depth_to_groundwater_m=4.5, hydraulic_gradient=-0.01)


def test_nonpositive_soil_thickness_rejected():
    with pytest.raises(ContractValidationError):
        SubsurfaceConfiguration(soil_id="clay_loam", soil_thickness_m=0.0)


def test_negative_design_flow_rejected():
    with pytest.raises(ContractValidationError):
        SourceConfiguration(design_flow_gpd=-1.0)


def test_nonpositive_receptor_distance_rejected():
    with pytest.raises(ContractValidationError):
        ReceptorDefinition(receptor_id="r", receptor_type="private_well",
                           distance_m=0.0, display_name="R")


def test_unknown_enum_value_rejected():
    with pytest.raises(ContractValidationError):
        TreatmentConfiguration(treatment_level="tertiary",  # not a valid level
                               disinfection_status="none")


@pytest.mark.parametrize("nan_or_inf", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_rejected(nan_or_inf):
    with pytest.raises(ContractValidationError):
        GroundwaterConfiguration(depth_to_groundwater_m=nan_or_inf, hydraulic_gradient=0.01)


def test_blank_display_name_rejected():
    with pytest.raises(ContractValidationError):
        ReceptorDefinition(receptor_id="r", receptor_type=ReceptorType.PRIVATE_WELL,
                           distance_m=30.5, display_name="")


def test_constituent_defaults_to_governed_default_helper():
    c = constituent("e_coli")
    assert c.use_governed_default is True
    assert c.source_concentration is None
    assert c.role is ConstituentRole.GATING


def test_project_requires_nonempty_fields():
    with pytest.raises(ContractValidationError):
        ProjectMetadata(name="", engineer="E", county="C", regulatory_authority="A")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
