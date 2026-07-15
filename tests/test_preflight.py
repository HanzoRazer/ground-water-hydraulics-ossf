"""
test_preflight.py
=================

Focused unit tests for individual Site Appropriateness Determination (SAD)
rules, now driven by validated ``SiteCaseV1`` records (OSSF-GW-002).

Structural / malformed-input cases (missing fields, non-finite or negative
numbers, unknown soil) are no longer preflight concerns — they are rejected by
the contract layer before preflight and are covered in
``test_site_case_validation.py``. These tests exercise the surviving rule
logic and preserved SAD thresholds:

  * type-specific well setbacks enforced across ALL receptors, not just the
    nearest one (regression for the receptor-selection bug);
  * gradient magnitude warn/refuse envelope;
  * structured treatment (SAD-007) keyed off enums, not narrative text.

Run: python -m pytest tests/test_preflight.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import constituent, make_case, receptor
from core.contracts import DisinfectionMethod, DisinfectionStatus, TreatmentLevel
from core.preflight import (
    evaluate_site,
    rule_gradient,
    rule_receptor_distance,
    rule_treatment_class,
)


# ---------------------------------------------------------------------------
# rule_receptor_distance — type-specific minimums across ALL receptors
# ---------------------------------------------------------------------------

def test_nearest_only_bug_fixed_private_well_behind_property_line():
    """A nearer property boundary must NOT mask a farther but still-illegal
    private well. Property line at 3 m (nearest), private well at 12 m
    (~39 ft < 50 ft) => the well violation must drive a refusal."""
    case = make_case(receptors=(
        receptor("pl", "property_boundary", 3.0, "Property line"),
        receptor("well", "private_well", 12.0, "Neighbor well"),
    ))
    finding = rule_receptor_distance(case)
    assert finding.rule_id == "SAD-005"
    assert finding.disposition == "refuse"
    assert "private well" in finding.message.lower()


def test_public_well_behind_property_line_refuses():
    case = make_case(receptors=(
        receptor("pl", "property_boundary", 3.0, "Property line"),
        receptor("city", "public_well", 30.0, "City well"),  # ~98 ft < 150
    ))
    finding = rule_receptor_distance(case)
    assert finding.disposition == "refuse"
    assert "public water supply" in finding.message.lower()


def test_compliant_wells_proceed():
    case = make_case(receptors=(
        receptor("well", "private_well", 30.5, "Private well"),  # 100 ft
        receptor("pl", "property_boundary", 20.0, "Property line"),
    ))
    finding = rule_receptor_distance(case)
    assert finding.disposition == "proceed"


def test_generic_short_distance_still_warns_without_well_violation():
    case = make_case(receptors=(receptor("pl", "property_boundary", 10.0, "PL"),))
    finding = rule_receptor_distance(case)
    assert finding.disposition == "warn"


def test_inactive_receptor_ignored_by_preflight_setback():
    """An inactive private well inside the 50-ft minimum must not refuse if
    only active receptors are compliant."""
    case = make_case(receptors=(
        receptor("inactive_well", "private_well", 10.0, "Inactive well", active=False),
        receptor("pl", "property_boundary", 30.0, "Property line"),
    ))
    finding = rule_receptor_distance(case)
    assert finding.disposition == "proceed"


def test_no_active_receptors_refuses():
    case = make_case(receptors=(
        receptor("off", "private_well", 30.5, "Off well", active=False),
    ))
    finding = rule_receptor_distance(case)
    assert finding.disposition == "refuse"
    assert "active" in finding.message.lower()


# ---------------------------------------------------------------------------
# rule_gradient — magnitude envelope (sign/finiteness enforced by contract)
# ---------------------------------------------------------------------------

def test_low_gradient_warns():
    assert rule_gradient(make_case(gradient=0.0005)).disposition == "warn"


def test_high_gradient_refuses():
    assert rule_gradient(make_case(gradient=0.2)).disposition == "refuse"


def test_moderately_high_gradient_warns():
    assert rule_gradient(make_case(gradient=0.06)).disposition == "warn"


def test_normal_gradient_proceeds():
    assert rule_gradient(make_case(gradient=0.01)).disposition == "proceed"


# ---------------------------------------------------------------------------
# rule_treatment_class (SAD-007) — structured, not narrative
# ---------------------------------------------------------------------------

def test_primary_treatment_refuses():
    case = make_case(
        treatment_level=TreatmentLevel.PRIMARY,
        disinfection_status=DisinfectionStatus.NONE,
        disinfection_method=DisinfectionMethod.NONE,
    )
    f = rule_treatment_class(case)
    assert f.rule_id == "SAD-007" and f.disposition == "refuse"


def test_secondary_without_disinfection_warns():
    case = make_case(
        treatment_level=TreatmentLevel.SECONDARY,
        disinfection_status=DisinfectionStatus.NONE,
        disinfection_method=DisinfectionMethod.NONE,
    )
    assert rule_treatment_class(case).disposition == "warn"


def test_secondary_with_disinfection_proceeds():
    assert rule_treatment_class(make_case()).disposition == "proceed"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_evaluate_site_aggregates_to_worst_disposition():
    # karst -> SAD-002 refuse dominates.
    case = make_case(regulatory_location={"karst_terrain": True})
    det = evaluate_site(case)
    assert det.disposition == "refuse"
    assert any(f.rule_id == "SAD-002" and f.disposition == "refuse" for f in det.findings)
    # All seven SAD rule IDs are present.
    ids = {f.rule_id for f in det.findings}
    assert ids == {"SAD-001", "SAD-002", "SAD-003", "SAD-004", "SAD-005", "SAD-006", "SAD-007"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
