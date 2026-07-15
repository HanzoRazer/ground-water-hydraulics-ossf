"""
test_site_case_legacy.py
========================

Explicit legacy (pre-V1) conversion tests (OSSF-GW-002 §5.24 / §8.12).

The legacy converter is deterministic and non-inventive: known narrative
values map through an explicit table; anything materially ambiguous is
REFUSED rather than guessed. A successful conversion returns a fully
validated ``SiteCaseV1``.

Run: python -m pytest tests/test_site_case_legacy.py -v
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import load_dbs
from core.contracts import (
    LegacyConfigError,
    SCHEMA_VERSION,
    SiteCaseV1,
    convert_legacy_site_config_to_v1,
)

SOILS, CONS = load_dbs()
LEGACY_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "site_case_legacy.json"


def _legacy() -> dict:
    return json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))


def _convert(raw, warnings_out=None) -> SiteCaseV1:
    return convert_legacy_site_config_to_v1(
        raw, soil_database=SOILS, constituent_database=CONS, warnings_out=warnings_out
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_known_legacy_fixture_converts_to_valid_v1():
    case = _convert(_legacy())
    assert isinstance(case, SiteCaseV1)
    assert case.schema_version == SCHEMA_VERSION
    assert case.site_id == "EX-001"
    # Narrative treatment mapped to structured fields.
    assert case.treatment.treatment_level.value == "secondary"
    assert case.treatment.disinfection_status.value == "disinfected"
    assert case.treatment.disinfection_method.value == "chlorine"


def test_conversion_generates_stable_receptor_ids():
    case = _convert(_legacy())
    ids = [r.receptor_id for r in case.receptors]
    assert ids == [f"receptor_{i + 1}" for i in range(len(ids))]


def test_conversion_warnings_are_deterministic():
    w1: list[str] = []
    w2: list[str] = []
    _convert(_legacy(), warnings_out=w1)
    _convert(_legacy(), warnings_out=w2)
    assert w1 == w2
    assert any("treatment_class" in w for w in w1)
    assert any("receptor_id" in w for w in w1)


def test_nitrate_maps_to_reference_only():
    case = _convert(_legacy())
    nitrate = next(c for c in case.constituents if c.constituent_id == "nitrate_as_N")
    assert nitrate.role.value == "reference_only"


def test_comparison_soils_preserved():
    case = _convert(_legacy())
    assert case.reporting.comparison_soil_ids == ("sandy_loam", "loamy_sand")


# ---------------------------------------------------------------------------
# Refusals — ambiguity is never guessed
# ---------------------------------------------------------------------------

def test_already_versioned_input_rejected():
    raw = _legacy()
    raw["schema_version"] = SCHEMA_VERSION
    with pytest.raises(LegacyConfigError):
        _convert(raw)


def test_missing_site_id_rejected():
    raw = _legacy()
    raw["project"].pop("site_id")
    with pytest.raises(LegacyConfigError):
        _convert(raw)


def test_ambiguous_treatment_narrative_rejected():
    raw = _legacy()
    raw["source"]["treatment_class"] = "Some unlisted aerobic thing"
    with pytest.raises(LegacyConfigError):
        _convert(raw)


def test_legacy_treatment_whitespace_normalization():
    raw = _legacy()
    raw["source"]["treatment_class"] = "  Class I Aerobic + Disinfection (TCEQ Ch. 285.32)  "
    case = _convert(raw)
    assert case.treatment.treatment_level.value == "secondary"


def test_legacy_c0_override_uses_estimated_basis():
    raw = _legacy()
    raw["source"]["C0_overrides"] = {"e_coli": 42.0}
    case = _convert(raw)
    e_coli = next(c for c in case.constituents if c.constituent_id == "e_coli")
    assert e_coli.source_concentration == 42.0
    assert e_coli.source_basis.value == "estimated"


def test_unknown_receptor_type_rejected():
    raw = _legacy()
    raw["receptors"][0]["type"] = "lake"
    with pytest.raises(LegacyConfigError):
        _convert(raw)


def test_missing_material_field_is_not_invented():
    """Dropping a required engineering value (soil thickness) must surface as
    a validation failure, not a silently fabricated default."""
    raw = copy.deepcopy(_legacy())
    raw["subsurface"].pop("soil_thickness_m")
    with pytest.raises(Exception):  # ContractValidationError via parse
        _convert(raw)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
