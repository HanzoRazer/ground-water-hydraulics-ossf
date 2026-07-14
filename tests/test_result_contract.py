"""
test_result_contract.py
=======================

Unit tests for the shared output-artifact contract (core/result_contract.py).
These pin the canonical status vocabulary and exit-code taxonomy so the two
drivers (flat toolkit and governed OSSF-GW-001) cannot drift apart — see
ADR-0004.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import result_contract as rc


def test_schema_version_is_pinned():
    assert rc.RESULT_SCHEMA_VERSION == "screening-result-2.0"


def test_status_vocabulary():
    assert rc.STATUSES == ("pass", "fail", "refused")
    # "authorized" must never be a status value (that is the whole point).
    assert "authorized" not in rc.STATUSES


def test_exit_code_taxonomy_values():
    assert (rc.EXIT_PASS, rc.EXIT_ERROR, rc.EXIT_REFUSED, rc.EXIT_FAIL) == (0, 1, 2, 3)


@pytest.mark.parametrize(
    "status, code",
    [("pass", 0), ("fail", 3), ("refused", 2)],
)
def test_exit_code_for_each_status(status, code):
    assert rc.exit_code_for(status) == code


def test_exit_code_for_rejects_unknown_status():
    with pytest.raises(ValueError):
        rc.exit_code_for("authorized")


def test_resolve_status_refused_when_unauthorized():
    # all_criteria_met is ignored when not authorized.
    assert rc.resolve_status(authorized=False, all_criteria_met=None) == "refused"
    assert rc.resolve_status(authorized=False, all_criteria_met=True) == "refused"


def test_resolve_status_pass_and_fail_when_authorized():
    assert rc.resolve_status(authorized=True, all_criteria_met=True) == "pass"
    assert rc.resolve_status(authorized=True, all_criteria_met=False) == "fail"


def test_resolve_status_requires_determinate_outcome_when_authorized():
    with pytest.raises(ValueError):
        rc.resolve_status(authorized=True, all_criteria_met=None)


def test_status_to_exit_round_trip_is_collision_free():
    # Each status maps to a distinct exit code, and 1 (error) is reserved.
    codes = {rc.exit_code_for(s) for s in rc.STATUSES}
    assert codes == {0, 2, 3}
    assert rc.EXIT_ERROR == 1 and rc.EXIT_ERROR not in codes


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
