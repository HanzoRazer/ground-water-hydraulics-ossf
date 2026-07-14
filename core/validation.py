"""
validation.py — Structural and cross-field validation for site configs.

This module is the single gate that a site configuration must pass before any
Darcy / transport calculation runs. Its job is deliberately narrow:

  * confirm required fields are present, correctly typed, and finite;
  * confirm enumerated references (soil class, constituents) exist in the
    active databases;
  * confirm receptors and constituents are well-formed and unique;
  * confirm effluent-concentration overrides are structurally valid and are
    supplied in the same unit the constituent database uses.

It does NOT make regulatory or scientific judgments (whether a site is
appropriate, whether a constituent passes) — those belong to the screening
calculation and the engineer of record.

All problems are collected in a single pass and reported together with a
field path (e.g. ``receptors[1].distance_m``) so a user can fix a config in
one edit cycle rather than one error at a time.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


class ConfigValidationError(ValueError):
    """Raised when a site configuration fails validation.

    Carries the full list of field-path error messages in ``errors`` so a
    caller (CLI, API, test) can present them all at once.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        body = "\n".join(f"  - {e}" for e in self.errors)
        super().__init__(f"Invalid site configuration ({len(self.errors)} problem(s)):\n{body}")


def _is_finite_number(x: Any) -> bool:
    """True only for real, finite ints/floats (bool and NaN/inf excluded)."""
    if isinstance(x, bool):
        return False
    if not isinstance(x, (int, float)):
        return False
    return math.isfinite(x)


def _available(db: Mapping[str, Any]) -> list[str]:
    return sorted(k for k in db if not k.startswith("_"))


def validate_config(
    config: Mapping[str, Any],
    soils_db: Mapping[str, Any],
    constituents_db: Mapping[str, Any],
) -> None:
    """Validate a parsed site configuration against the active databases.

    Raises
    ------
    ConfigValidationError
        If one or more problems are found (all are reported together).
    """
    errors: list[str] = []

    # --- schema version -----------------------------------------------------
    version = config.get("_schema_version")
    supported = sorted(SUPPORTED_SCHEMA_VERSIONS)
    if version is None:
        errors.append(f"_schema_version: missing (supported: {supported})")
    elif str(version) not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"_schema_version: unsupported '{version}' (supported: {supported})")

    # --- site identity ------------------------------------------------------
    site_id = config.get("site_id")
    if not isinstance(site_id, str) or not site_id.strip():
        errors.append("site_id: required non-empty string")

    # --- soil class ---------------------------------------------------------
    soil_class = config.get("soil_class")
    if not isinstance(soil_class, str) or not soil_class.strip():
        errors.append("soil_class: required non-empty string")
    elif soil_class not in soils_db:
        errors.append(f"soil_class: '{soil_class}' not in soils database (available: {_available(soils_db)})")

    # --- hydraulic gradient -------------------------------------------------
    gradient = config.get("hydraulic_gradient")
    if not _is_finite_number(gradient):
        errors.append(f"hydraulic_gradient: required finite number, got {gradient!r}")
    elif gradient <= 0:
        errors.append(f"hydraulic_gradient: must be > 0, got {gradient}")

    # --- comparison soil (optional) -----------------------------------------
    comparison_soil = config.get("comparison_soil")
    if comparison_soil is not None:
        if not isinstance(comparison_soil, str) or comparison_soil not in soils_db:
            errors.append(
                f"comparison_soil: '{comparison_soil}' not in soils database "
                f"(available: {_available(soils_db)})"
            )

    # --- constituents -------------------------------------------------------
    constituents = config.get("constituents")
    if not isinstance(constituents, list) or not constituents:
        errors.append("constituents: required non-empty list")
    else:
        seen: set[str] = set()
        for i, cname in enumerate(constituents):
            if not isinstance(cname, str) or not cname.strip():
                errors.append(f"constituents[{i}]: must be a non-empty string, got {cname!r}")
                continue
            if cname in seen:
                errors.append(f"constituents[{i}]: duplicate constituent '{cname}'")
            seen.add(cname)
            if cname not in constituents_db:
                errors.append(
                    f"constituents[{i}]: '{cname}' not in constituents database "
                    f"(available: {_available(constituents_db)})"
                )

    # --- receptors ----------------------------------------------------------
    receptors = config.get("receptors")
    if not isinstance(receptors, list) or not receptors:
        errors.append("receptors: required non-empty list")
    else:
        seen_names: set[str] = set()
        for i, rec in enumerate(receptors):
            if not isinstance(rec, Mapping):
                errors.append(f"receptors[{i}]: must be an object with 'name' and 'distance_m'")
                continue
            name = rec.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"receptors[{i}].name: required non-empty string")
            else:
                if name in seen_names:
                    errors.append(f"receptors[{i}].name: duplicate receptor name '{name}'")
                seen_names.add(name)
            dist = rec.get("distance_m")
            if not _is_finite_number(dist):
                errors.append(f"receptors[{i}].distance_m: required finite number, got {dist!r}")
            elif dist <= 0:
                errors.append(f"receptors[{i}].distance_m: must be > 0, got {dist}")

    # --- effluent concentration overrides -----------------------------------
    effluent = config.get("effluent_concentrations", {})
    if not isinstance(effluent, Mapping):
        errors.append("effluent_concentrations: must be an object mapping constituent -> {C0, unit}")
    else:
        for cname, entry in effluent.items():
            path = f"effluent_concentrations.{cname}"
            if cname not in constituents_db:
                errors.append(f"{path}: unknown constituent '{cname}'")
                continue
            if not isinstance(entry, Mapping):
                errors.append(f"{path}: must be an object with 'C0' (and optional 'unit')")
                continue
            c0 = entry.get("C0")
            if not _is_finite_number(c0):
                errors.append(f"{path}.C0: required finite number, got {c0!r}")
            elif c0 < 0:
                errors.append(f"{path}.C0: must be >= 0, got {c0}")
            unit = entry.get("unit")
            db_unit = constituents_db[cname].get("limit_unit")
            if unit is not None and db_unit is not None and unit != db_unit:
                errors.append(
                    f"{path}.unit: '{unit}' does not match the database unit "
                    f"'{db_unit}' for '{cname}'. Supply the value in '{db_unit}' "
                    f"or correct the label; this tool performs no unit conversion."
                )

    if errors:
        raise ConfigValidationError(errors)
