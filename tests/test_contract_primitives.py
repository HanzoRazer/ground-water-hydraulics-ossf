"""Unit tests for contract enums and error accumulation (commit 1 surface)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.contracts import ContractValidationError, FieldValidationError, TreatmentLevel
from core.contracts.enums import parse_enum
from core.contracts.errors import ErrorCollector


def test_parse_enum_accepts_member_and_string():
    assert parse_enum(TreatmentLevel, "secondary", path="t") is TreatmentLevel.SECONDARY
    assert parse_enum(TreatmentLevel, TreatmentLevel.PRIMARY, path="t") is TreatmentLevel.PRIMARY


def test_parse_enum_rejects_unknown():
    with pytest.raises(ContractValidationError):
        parse_enum(TreatmentLevel, "tertiary", path="treatment.treatment_level")


def test_error_collector_accumulates_and_raises():
    ec = ErrorCollector()
    ec.add("a", "code", "msg one")
    ec.add("b", "code", "msg two")
    assert len(ec) == 2
    with pytest.raises(ContractValidationError) as ei:
        ec.raise_if_any()
    assert len(ei.value.errors) == 2
    assert isinstance(ei.value.errors[0], FieldValidationError)
