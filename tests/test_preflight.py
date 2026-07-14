"""
test_preflight.py
=================

Focused unit tests for individual Site Appropriateness Determination (SAD)
rules. These exercise rule logic directly (rather than only through
end-to-end fixtures) and specifically cover the edge cases that a coarse
happy-path fixture suite misses:

  * type-specific well setbacks must be enforced across ALL receptors, not
    just the nearest one (regression for the receptor-selection bug);
  * a negative / non-numeric hydraulic gradient is invalid input, not a
    low-magnitude "warn";
  * malformed receptor entries produce a governed refusal, not a KeyError.

Run: python -m pytest tests/test_preflight.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.preflight import (
    rule_gradient,
    rule_receptor_distance,
)

SOILS: dict = {}  # rule_receptor_distance / rule_gradient do not use soils


# ---------------------------------------------------------------------------
# rule_receptor_distance — type-specific minimums across ALL receptors
# ---------------------------------------------------------------------------

def test_nearest_only_bug_fixed_private_well_behind_property_line():
    """Regression: a nearer property boundary must NOT mask a farther but
    still-illegal private well. Property line at 3 m (nearest), private well
    at 12 m (~39 ft < 50 ft) => the well violation must drive a refusal."""
    cfg = {
        "receptors": [
            {"name": "Property line", "type": "property_boundary", "distance_m": 3.0},
            {"name": "Neighbor well", "type": "private_well", "distance_m": 12.0},
        ]
    }
    finding = rule_receptor_distance(cfg, SOILS)
    assert finding.rule_id == "SAD-005"
    assert finding.disposition == "refuse"
    assert "private well" in finding.message.lower()


def test_public_well_behind_property_line_refuses():
    cfg = {
        "receptors": [
            {"name": "Property line", "type": "property_boundary", "distance_m": 3.0},
            {"name": "City well", "type": "public_well", "distance_m": 30.0},  # ~98 ft < 150
        ]
    }
    finding = rule_receptor_distance(cfg, SOILS)
    assert finding.disposition == "refuse"
    assert "public water supply" in finding.message.lower()


def test_compliant_wells_proceed():
    cfg = {
        "receptors": [
            {"name": "Private well", "type": "private_well", "distance_m": 30.5},  # 100 ft
            {"name": "Property line", "type": "property_boundary", "distance_m": 20.0},
        ]
    }
    finding = rule_receptor_distance(cfg, SOILS)
    assert finding.disposition == "proceed"


def test_generic_short_distance_still_warns_without_well_violation():
    cfg = {"receptors": [{"name": "PL", "type": "property_boundary", "distance_m": 10.0}]}
    finding = rule_receptor_distance(cfg, SOILS)
    assert finding.disposition == "warn"


def test_no_receptors_refuses():
    finding = rule_receptor_distance({"receptors": []}, SOILS)
    assert finding.disposition == "refuse"


def test_malformed_receptor_distance_refuses_not_crashes():
    cfg = {"receptors": [{"name": "no distance", "type": "property_boundary"}]}
    finding = rule_receptor_distance(cfg, SOILS)
    assert finding.disposition == "refuse"
    assert "invalid distance_m" in finding.message


@pytest.mark.parametrize("bad", [-5.0, 0.0, "20", None, float("nan"), True])
def test_bad_distance_values_refuse(bad):
    cfg = {"receptors": [{"name": "r", "type": "property_boundary", "distance_m": bad}]}
    finding = rule_receptor_distance(cfg, SOILS)
    assert finding.disposition == "refuse"


# ---------------------------------------------------------------------------
# rule_gradient — negative / invalid input vs low-magnitude
# ---------------------------------------------------------------------------

def test_negative_gradient_refuses():
    finding = rule_gradient({"subsurface": {"hydraulic_gradient": -0.01}}, SOILS)
    assert finding.rule_id == "SAD-006"
    assert finding.disposition == "refuse"
    assert "negative" in finding.message.lower()


def test_non_numeric_gradient_refuses():
    finding = rule_gradient({"subsurface": {"hydraulic_gradient": "0.01"}}, SOILS)
    assert finding.disposition == "refuse"


def test_missing_gradient_refuses():
    finding = rule_gradient({"subsurface": {}}, SOILS)
    assert finding.disposition == "refuse"


def test_low_gradient_warns():
    finding = rule_gradient({"subsurface": {"hydraulic_gradient": 0.0005}}, SOILS)
    assert finding.disposition == "warn"


def test_high_gradient_refuses():
    finding = rule_gradient({"subsurface": {"hydraulic_gradient": 0.2}}, SOILS)
    assert finding.disposition == "refuse"


def test_normal_gradient_proceeds():
    finding = rule_gradient({"subsurface": {"hydraulic_gradient": 0.01}}, SOILS)
    assert finding.disposition == "proceed"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
