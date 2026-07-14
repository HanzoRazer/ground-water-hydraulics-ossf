"""Unit tests for core.validation — site-configuration validation."""

import copy

import pytest

from core.validation import ConfigValidationError, validate_config

# Minimal in-memory databases (independent of the on-disk JSON files).
SOILS = {
    "_units": {},
    "Clay Loam": {"K_m_per_day": 0.0624, "n_e": 0.414, "rho_b_g_per_cm3": 1.43, "f_oc": 0.004},
    "Sand": {"K_m_per_day": 7.128, "n_e": 0.375, "rho_b_g_per_cm3": 1.66, "f_oc": 0.0005},
}
CONSTITUENTS = {
    "_units": {},
    "Nitrate-N": {"K_oc_mL_per_g": 0.0, "lambda_per_day": 0.02, "limit": 10.0,
                  "limit_unit": "mg/L", "C0_default": 40.0},
    "E. coli": {"K_oc_mL_per_g": 0.0, "lambda_per_day": 0.8, "limit": 0.0,
                "limit_unit": "CFU/100 mL", "C0_default": 100.0},
}


def _good_config():
    return {
        "_schema_version": "1.0",
        "site_id": "s1",
        "soil_class": "Clay Loam",
        "hydraulic_gradient": 0.01,
        "comparison_soil": "Sand",
        "constituents": ["Nitrate-N", "E. coli"],
        "receptors": [
            {"name": "well", "distance_m": 150.0},
            {"name": "prop_line", "distance_m": 60.0},
        ],
        "effluent_concentrations": {
            "Nitrate-N": {"C0": 25.0, "unit": "mg/L"},
        },
    }


def _assert_error_contains(cfg, needle):
    with pytest.raises(ConfigValidationError) as exc:
        validate_config(cfg, SOILS, CONSTITUENTS)
    joined = "\n".join(exc.value.errors)
    assert needle in joined, f"expected '{needle}' in:\n{joined}"


def test_valid_config_passes():
    validate_config(_good_config(), SOILS, CONSTITUENTS)  # no raise


def test_missing_schema_version():
    cfg = _good_config()
    del cfg["_schema_version"]
    _assert_error_contains(cfg, "_schema_version")


def test_unsupported_schema_version():
    cfg = _good_config()
    cfg["_schema_version"] = "9.9"
    _assert_error_contains(cfg, "unsupported")


def test_missing_site_id():
    cfg = _good_config()
    cfg["site_id"] = "   "
    _assert_error_contains(cfg, "site_id")


def test_unknown_soil_class():
    cfg = _good_config()
    cfg["soil_class"] = "Nonexistent"
    _assert_error_contains(cfg, "soil_class")


def test_nonpositive_gradient():
    cfg = _good_config()
    cfg["hydraulic_gradient"] = 0.0
    _assert_error_contains(cfg, "hydraulic_gradient")


def test_nan_gradient_rejected():
    cfg = _good_config()
    cfg["hydraulic_gradient"] = float("nan")
    _assert_error_contains(cfg, "hydraulic_gradient")


def test_bool_is_not_a_number():
    cfg = _good_config()
    cfg["hydraulic_gradient"] = True
    _assert_error_contains(cfg, "hydraulic_gradient")


def test_unknown_comparison_soil():
    cfg = _good_config()
    cfg["comparison_soil"] = "Rock"
    _assert_error_contains(cfg, "comparison_soil")


def test_empty_constituents():
    cfg = _good_config()
    cfg["constituents"] = []
    _assert_error_contains(cfg, "constituents")


def test_duplicate_constituent():
    cfg = _good_config()
    cfg["constituents"] = ["Nitrate-N", "Nitrate-N"]
    _assert_error_contains(cfg, "duplicate constituent")


def test_unknown_constituent():
    cfg = _good_config()
    cfg["constituents"] = ["Arsenic"]
    _assert_error_contains(cfg, "not in constituents database")


def test_empty_receptors():
    cfg = _good_config()
    cfg["receptors"] = []
    _assert_error_contains(cfg, "receptors")


def test_receptor_missing_name():
    cfg = _good_config()
    cfg["receptors"] = [{"distance_m": 100.0}]
    _assert_error_contains(cfg, "name")


def test_receptor_nonpositive_distance():
    cfg = _good_config()
    cfg["receptors"] = [{"name": "r", "distance_m": -5.0}]
    _assert_error_contains(cfg, "distance_m")


def test_duplicate_receptor_name():
    cfg = _good_config()
    cfg["receptors"] = [
        {"name": "well", "distance_m": 100.0},
        {"name": "well", "distance_m": 200.0},
    ]
    _assert_error_contains(cfg, "duplicate receptor name")


def test_effluent_unit_mismatch():
    cfg = _good_config()
    cfg["effluent_concentrations"]["Nitrate-N"]["unit"] = "ug/L"
    _assert_error_contains(cfg, "does not match the database unit")


def test_effluent_negative_c0():
    cfg = _good_config()
    cfg["effluent_concentrations"]["Nitrate-N"]["C0"] = -1.0
    _assert_error_contains(cfg, "C0")


def test_effluent_unknown_constituent():
    cfg = _good_config()
    cfg["effluent_concentrations"]["Arsenic"] = {"C0": 1.0}
    _assert_error_contains(cfg, "unknown constituent")


def test_all_errors_collected_together():
    cfg = _good_config()
    del cfg["_schema_version"]
    cfg["hydraulic_gradient"] = -1.0
    cfg["receptors"] = []
    with pytest.raises(ConfigValidationError) as exc:
        validate_config(cfg, SOILS, CONSTITUENTS)
    assert len(exc.value.errors) >= 3
