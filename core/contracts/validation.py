"""
core/contracts/validation.py
============================

Site-level cross-field, database-reference, and engine-compatibility
validation for :class:`~core.contracts.site_case_v1.SiteCaseV1`
(OSSF-GW-002).

Record-level structural validity (types, units, enums, per-field ranges) is
enforced when the records are constructed (``site_case_v1``). This module
owns the checks that need the *whole* case or the databases:

* duplicate stable-ID detection (receptors, constituents, assumptions);
* treatment/disinfection internal consistency;
* explicit-or-visible source-concentration presence;
* soil / constituent database resolution and record plausibility;
* comparison-soil existence;
* physics engine registration and dispersivity-method compatibility.

It does NOT implement any SAD regulatory threshold. Site-appropriateness
remains the preflight's exclusive authority.

Cross-field/value problems accumulate into a single
:class:`CrossFieldValidationError`. Reference problems (unknown soil /
constituent / engine, unsupported option) raise their specific typed
exceptions so callers can distinguish them.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

from . import _primitives as P
from .enums import DisinfectionMethod, DisinfectionStatus
from .errors import (
    ContractValidationError,
    CrossFieldValidationError,
    ErrorCollector,
    FieldValidationError,
    UnknownConstituentError,
    UnknownEngineError,
    UnknownSoilError,
    UnsupportedPhysicsOptionError,
)
from .site_case_v1 import ConstituentSelection, ReceptorDefinition, SiteCaseV1

_MAX_AVAILABLE_LIST = 8


def _fmt_available(keys, *, limit: int = _MAX_AVAILABLE_LIST) -> str:
    """Format a sorted key list for error messages, truncating long DB lists."""
    sorted_keys = sorted(keys)
    if len(sorted_keys) <= limit:
        return ", ".join(sorted_keys)
    head = ", ".join(sorted_keys[:limit])
    return f"{head}, … ({len(sorted_keys) - limit} more)"


def active_receptors(case: SiteCaseV1) -> tuple[ReceptorDefinition, ...]:
    """Receptors with ``active=True``. Preflight and physics operate on this
    subset only; inactive receptors are retained for documentation but do not
    drive setbacks, engine runs, or comparison-scenario nearest-receptor logic."""
    return tuple(r for r in case.receptors if r.active)


# Per-engine supported dispersivity methods live in ``physics_registry`` so
# contract validation and execution share one capability map.
# ---------------------------------------------------------------------------
# Duplicate-ID validator
# ---------------------------------------------------------------------------

def check_unique_ids(
    ids: List[str], *, path_prefix: str, id_field: str, collector: ErrorCollector
) -> None:
    seen: dict = {}
    for i, value in enumerate(ids):
        if value in seen:
            collector.add(
                f"{path_prefix}[{i}].{id_field}",
                "duplicate_id",
                f"duplicate {id_field} {value!r} (first seen at index {seen[value]})",
                invalid_value=value,
            )
        else:
            seen[value] = i


# ---------------------------------------------------------------------------
# Cross-field (value) validation
# ---------------------------------------------------------------------------

def _validate_cross_field(case: SiteCaseV1, ec: ErrorCollector) -> None:
    if not case.receptors:
        ec.add("receptors", "required", "at least one receptor is required")
    elif not active_receptors(case):
        ec.add("receptors", "required", "at least one active receptor is required")
    if not case.constituents:
        ec.add("constituents", "required", "at least one constituent is required")

    check_unique_ids(
        [r.receptor_id for r in case.receptors],
        path_prefix="receptors", id_field="receptor_id", collector=ec,
    )
    check_unique_ids(
        [c.constituent_id for c in case.constituents],
        path_prefix="constituents", id_field="constituent_id", collector=ec,
    )
    check_unique_ids(
        [a.assumption_id for a in case.assumptions],
        path_prefix="assumptions", id_field="assumption_id", collector=ec,
    )

    # Treatment / disinfection internal consistency (structural, not SAD).
    t = case.treatment
    if t.disinfection_status == DisinfectionStatus.NONE and \
            t.disinfection_method != DisinfectionMethod.NONE:
        ec.add(
            "treatment.disinfection_method", "inconsistent",
            "disinfection_method must be 'none' when disinfection_status is 'none'",
            invalid_value=t.disinfection_method.value,
        )
    if t.disinfection_status == DisinfectionStatus.DISINFECTED and \
            t.disinfection_method == DisinfectionMethod.NONE:
        ec.add(
            "treatment.disinfection_method", "inconsistent",
            "a disinfection_method is required when disinfection_status is 'disinfected'",
            invalid_value=t.disinfection_method.value,
        )

    # Source concentration: exactly one of explicit / visible governed default.
    for i, sel in enumerate(case.constituents):
        has_explicit = sel.source_concentration is not None
        if has_explicit and sel.use_governed_default:
            ec.add(
                f"constituents[{i}].source_concentration", "ambiguous_source",
                "specify either an explicit source_concentration OR "
                "use_governed_default=true, not both",
            )
        elif not has_explicit and not sel.use_governed_default:
            ec.add(
                f"constituents[{i}].source_concentration", "missing_source",
                "a source concentration is required: set source_concentration "
                "explicitly or use_governed_default=true to select the "
                "governed database default",
            )


# ---------------------------------------------------------------------------
# Database resolution
# ---------------------------------------------------------------------------

def resolve_soil(soil_id: str, soil_database: Mapping[str, Any]) -> dict:
    """Return the soil record for ``soil_id`` or raise :class:`UnknownSoilError`."""
    if soil_id not in soil_database:
        raise UnknownSoilError([FieldValidationError(
            path="subsurface.soil_id", code="unknown_soil",
            message=f"soil_id {soil_id!r} not found in the soil database; available: {_fmt_available(soil_database)}",
            invalid_value=soil_id,
        )])
    return dict(soil_database[soil_id])


def resolve_constituent(constituent_id: str, constituent_database: Mapping[str, Any]) -> dict:
    """Return the constituent record or raise :class:`UnknownConstituentError`."""
    if constituent_id not in constituent_database:
        raise UnknownConstituentError([FieldValidationError(
            path="constituents[].constituent_id", code="unknown_constituent",
            message=f"constituent_id {constituent_id!r} not found in the "
                    f"constituent database; available: {_fmt_available(constituent_database)}",
            invalid_value=constituent_id,
        )])
    return dict(constituent_database[constituent_id])


def _validate_soil_record(soil: Mapping[str, Any], soil_id: str) -> None:
    ec = ErrorCollector()
    P.check_positive(soil.get("K_sat_m_per_s"),
                     path=f"soil_database[{soil_id}].K_sat_m_per_s", collector=ec)
    P.check_fraction_0_1(soil.get("effective_porosity"),
                         path=f"soil_database[{soil_id}].effective_porosity", collector=ec)
    P.check_positive(soil.get("bulk_density_kg_per_m3"),
                     path=f"soil_database[{soil_id}].bulk_density_kg_per_m3", collector=ec)
    ec.raise_if_any(CrossFieldValidationError,
                    f"soil database record {soil_id!r} is malformed")


def _validate_constituent_record(
    cprops: Mapping[str, Any], sel: ConstituentSelection, index: int
) -> None:
    ec = ErrorCollector()
    base = f"constituent_database[{sel.constituent_id}]"
    P.check_nonnegative(cprops.get("lambda_per_day"), path=f"{base}.lambda_per_day", collector=ec)
    P.check_nonnegative(cprops.get("Kd_L_per_kg"), path=f"{base}.Kd_L_per_kg", collector=ec)
    P.check_finite_number(cprops.get("regulatory_limit"), path=f"{base}.regulatory_limit", collector=ec)
    if sel.source_concentration is None and sel.use_governed_default:
        P.check_nonnegative(cprops.get("typical_C0_post_disinfection"),
                            path=f"{base}.typical_C0_post_disinfection", collector=ec)
    ec.raise_if_any(CrossFieldValidationError,
                    f"constituent database record {sel.constituent_id!r} is "
                    f"missing properties required by constituents[{index}]")


def effective_source_concentration(
    sel: ConstituentSelection, cprops: Mapping[str, Any]
) -> float:
    """Resolve the effective source concentration: explicit value if set,
    else the governed database default (only reached when
    ``use_governed_default`` is true and validation has passed)."""
    if sel.source_concentration is not None:
        return float(sel.source_concentration)
    if not sel.use_governed_default:
        raise CrossFieldValidationError([FieldValidationError(
            path="constituents[].source_concentration", code="missing_source",
            message="source concentration is not set and use_governed_default is false",
        )])
    default = cprops.get("typical_C0_post_disinfection")
    if default is None:
        raise CrossFieldValidationError([FieldValidationError(
            path="constituents[].source_concentration", code="missing_source",
            message="constituent database record has no typical_C0_post_disinfection default",
        )])
    return float(default)


# ---------------------------------------------------------------------------
# Physics-selection compatibility
# ---------------------------------------------------------------------------

def validate_physics_selection(case: SiteCaseV1) -> None:
    """Validate that the selected engine is registered and the dispersivity
    method is supported by it. Compatibility only — runs no physics."""
    from ..physics_registry import ENGINES, supported_dispersivity_methods

    engine = case.physics.engine
    if engine not in ENGINES:
        raise UnknownEngineError([FieldValidationError(
            path="physics.engine", code="unknown_engine",
            message=f"engine {engine!r} is not registered; available: {_fmt_available(ENGINES)}",
            invalid_value=engine,
        )])
    supported_values = supported_dispersivity_methods(engine)
    if supported_values and case.physics.dispersivity_method.value not in supported_values:
        allowed = ", ".join(sorted(supported_values))
        raise UnsupportedPhysicsOptionError([FieldValidationError(
            path="physics.dispersivity_method", code="unsupported_option",
            message=f"dispersivity method {case.physics.dispersivity_method.value!r} "
                    f"is not supported by engine {engine!r}; supported: {allowed}",
            invalid_value=case.physics.dispersivity_method.value,
        )])


# ---------------------------------------------------------------------------
# Master validator
# ---------------------------------------------------------------------------

def validate_site_case(
    case: SiteCaseV1,
    *,
    soil_database: Mapping[str, Any],
    constituent_database: Mapping[str, Any],
) -> SiteCaseV1:
    """Run every cross-field, database-reference, and engine-compatibility
    check. Returns ``case`` unchanged on success; raises a typed exception on
    failure. This is the last gate before normalization / hashing / preflight.
    """
    # 1. Cross-field / value checks (accumulated).
    ec = ErrorCollector()
    _validate_cross_field(case, ec)
    ec.raise_if_any(CrossFieldValidationError, "Site case failed cross-field validation")

    # 2. Database resolution + record plausibility (typed, fail-fast).
    soil = resolve_soil(case.subsurface.soil_id, soil_database)
    _validate_soil_record(soil, case.subsurface.soil_id)

    for i, sel in enumerate(case.constituents):
        cprops = resolve_constituent(sel.constituent_id, constituent_database)
        _validate_constituent_record(cprops, sel, i)

    for j, sid in enumerate(case.reporting.comparison_soil_ids):
        if sid not in soil_database:
            raise UnknownSoilError([FieldValidationError(
                path=f"reporting.comparison_soil_ids[{j}]", code="unknown_soil",
                message=f"comparison soil_id {sid!r} not found; available: {_fmt_available(soil_database)}",
                invalid_value=sid,
            )])

    # 3. Engine-option compatibility (typed, fail-fast).
    validate_physics_selection(case)
    return case


__all__ = [
    "active_receptors",
    "check_unique_ids",
    "resolve_soil",
    "resolve_constituent",
    "effective_source_concentration",
    "validate_physics_selection",
    "validate_site_case",
]
