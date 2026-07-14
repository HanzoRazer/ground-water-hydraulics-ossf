"""
core/contracts/serialization.py
===============================

Canonical parsing and serialization for :class:`~core.contracts.site_case_v1.SiteCaseV1`
(OSSF-GW-002).

This module is the single canonical path for turning raw JSON into a validated
contract and back:

* :func:`parse_site_case_dict` — schema-version selection, structural parsing
  (multi-error accumulation with full field paths), record construction, then
  cross-field / database / engine-compatibility validation.
* :func:`load_site_case_json` — file loader wrapper.
* :func:`site_case_to_dict` / :func:`site_case_to_canonical_json` — deterministic
  serialization (enums -> string values, tuples -> arrays, ints normalized to
  floats during construction).
* :func:`site_case_hash` — the one and only governed hashing route. The hash is
  computed from the normalized serialized contract, never from a raw dict.
* :func:`validate_site_case_schema` — validate a dict/contract against the
  checked-in JSON Schema.

Raw input dictionaries are never hashed for governed execution (§4.12).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Set

from . import _primitives as P
from .enums import (
    AssumptionStatus,
    ConstituentRole,
    DisinfectionMethod,
    DisinfectionStatus,
    DispersivityMethod,
    EvidenceBasis,
    ReceptorType,
    TreatmentLevel,
    parse_enum,
)
from .errors import (
    ContractValidationError,
    ErrorCollector,
    UnsupportedSchemaVersionError,
)
from .site_case_v1 import (
    SCHEMA_VERSION,
    ConstituentSelection,
    DeclaredAssumption,
    GroundwaterConfiguration,
    PhysicsSelection,
    ProjectMetadata,
    ReceptorDefinition,
    RegulatoryLocation,
    ReportingMetadata,
    SiteCaseV1,
    SourceConfiguration,
    SubsurfaceConfiguration,
    TreatmentConfiguration,
)

_SCHEMA_FILENAME = "ossf-site-case-1.0.0.schema.json"

_TOP_LEVEL_KEYS = {
    "schema_version", "site_id", "project", "regulatory_location", "treatment",
    "source", "subsurface", "groundwater", "receptors", "constituents",
    "physics", "reporting", "assumptions",
}


# ---------------------------------------------------------------------------
# Schema-version detection / selection
# ---------------------------------------------------------------------------

def detect_schema_version(raw: Mapping[str, Any]) -> Optional[str]:
    """Return the declared ``schema_version`` string, or ``None`` if absent."""
    if not isinstance(raw, Mapping):
        return None
    value = raw.get("schema_version")
    return value if isinstance(value, str) else None


def _select_schema_version(raw: Mapping[str, Any]) -> None:
    if "schema_version" not in raw:
        raise UnsupportedSchemaVersionError(
            "Site case is missing 'schema_version'. Governed input must "
            f"declare '{SCHEMA_VERSION}'. Unversioned legacy configs must be "
            "converted with the explicit legacy converter."
        )
    version = raw.get("schema_version")
    if not isinstance(version, str) or not version.strip():
        raise UnsupportedSchemaVersionError(
            f"'schema_version' must be a non-empty string; got {version!r}."
        )
    if version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"Unsupported input schema_version {version!r}; this tool accepts "
            f"'{SCHEMA_VERSION}'. (A result-schema identifier is not a valid "
            "input schema.)"
        )


# ---------------------------------------------------------------------------
# Structural parsing helpers
# ---------------------------------------------------------------------------

def _require_obj(
    parent: Mapping[str, Any], key: str, path: str, ec: ErrorCollector
) -> Optional[Mapping[str, Any]]:
    if key not in parent:
        ec.add(path, "required", f"required section '{key}' is missing")
        return None
    value = parent[key]
    if not isinstance(value, Mapping):
        ec.add(path, "type", f"'{key}' must be an object", invalid_value=type(value).__name__)
        return None
    return value


def _reject_unknown_keys(
    obj: Mapping[str, Any], allowed: Set[str], path: str, ec: ErrorCollector
) -> None:
    for k in obj:
        if k not in allowed:
            ec.add(f"{path}.{k}", "unknown_field",
                   f"unknown field '{k}' (schema forbids additional properties)")


def _require_list(
    parent: Mapping[str, Any], key: str, path: str, ec: ErrorCollector
) -> Optional[list]:
    if key not in parent:
        ec.add(path, "required", f"required section '{key}' is missing")
        return None
    value = parent[key]
    if not isinstance(value, list):
        ec.add(path, "type", f"'{key}' must be an array", invalid_value=type(value).__name__)
        return None
    return value


# ---------------------------------------------------------------------------
# Section parsers (each returns a record or None, accumulating into ec)
# ---------------------------------------------------------------------------

def _parse_project(raw, ec) -> Optional[ProjectMetadata]:
    m = _require_obj(raw, "project", "project", ec)
    if m is None:
        return None
    _reject_unknown_keys(m, {"name", "engineer", "county", "regulatory_authority", "description"}, "project", ec)
    name = P.check_nonempty_str(m.get("name"), path="project.name", collector=ec)
    engineer = P.check_nonempty_str(m.get("engineer"), path="project.engineer", collector=ec)
    county = P.check_nonempty_str(m.get("county"), path="project.county", collector=ec)
    authority = P.check_nonempty_str(m.get("regulatory_authority"), path="project.regulatory_authority", collector=ec)
    description = P.check_optional_str(m.get("description"), path="project.description", collector=ec)
    if None in (name, engineer, county, authority):
        return None
    return ProjectMetadata(name=name, engineer=engineer, county=county,
                           regulatory_authority=authority, description=description)


def _parse_regulatory_location(raw, ec) -> Optional[RegulatoryLocation]:
    m = _require_obj(raw, "regulatory_location", "regulatory_location", ec)
    if m is None:
        return None
    bool_keys = ("edwards_aquifer_recharge_zone", "edwards_aquifer_transition_zone",
                 "edwards_aquifer_contributing_zone", "karst_terrain", "coastal_zone")
    _reject_unknown_keys(m, set(bool_keys) | {"notes"}, "regulatory_location", ec)
    values = {}
    ok = True
    for k in bool_keys:
        v = P.check_bool(m.get(k, False), path=f"regulatory_location.{k}", collector=ec)
        if v is None:
            ok = False
        values[k] = v
    notes = P.check_optional_str(m.get("notes"), path="regulatory_location.notes", collector=ec)
    if not ok:
        return None
    return RegulatoryLocation(notes=notes, **values)


def _parse_treatment(raw, ec) -> Optional[TreatmentConfiguration]:
    m = _require_obj(raw, "treatment", "treatment", ec)
    if m is None:
        return None
    _reject_unknown_keys(m, {"treatment_level", "disinfection_status", "disinfection_method", "notes"}, "treatment", ec)
    level = parse_enum(TreatmentLevel, m.get("treatment_level"), path="treatment.treatment_level", collector=ec)
    status = parse_enum(DisinfectionStatus, m.get("disinfection_status"), path="treatment.disinfection_status", collector=ec)
    method = parse_enum(DisinfectionMethod, m.get("disinfection_method", "none"), path="treatment.disinfection_method", collector=ec)
    notes = P.check_optional_str(m.get("notes"), path="treatment.notes", collector=ec)
    if None in (level, status, method):
        return None
    return TreatmentConfiguration(treatment_level=level, disinfection_status=status,
                                  disinfection_method=method, notes=notes)


def _parse_source(raw, ec) -> Optional[SourceConfiguration]:
    m = _require_obj(raw, "source", "source", ec)
    if m is None:
        return None
    _reject_unknown_keys(m, {"design_flow_gpd", "description"}, "source", ec)
    flow = P.check_nonnegative(m.get("design_flow_gpd"), path="source.design_flow_gpd", collector=ec)
    description = P.check_optional_str(m.get("description"), path="source.description", collector=ec)
    if flow is None:
        return None
    return SourceConfiguration(design_flow_gpd=flow, description=description)


def _parse_subsurface(raw, ec) -> Optional[SubsurfaceConfiguration]:
    m = _require_obj(raw, "subsurface", "subsurface", ec)
    if m is None:
        return None
    _reject_unknown_keys(m, {"soil_id", "soil_thickness_m"}, "subsurface", ec)
    soil_id = P.check_stable_id(m.get("soil_id"), path="subsurface.soil_id", collector=ec)
    thickness = P.check_positive(m.get("soil_thickness_m"), path="subsurface.soil_thickness_m", collector=ec)
    if None in (soil_id, thickness):
        return None
    return SubsurfaceConfiguration(soil_id=soil_id, soil_thickness_m=thickness)


def _parse_groundwater(raw, ec) -> Optional[GroundwaterConfiguration]:
    m = _require_obj(raw, "groundwater", "groundwater", ec)
    if m is None:
        return None
    _reject_unknown_keys(m, {"depth_to_groundwater_m", "hydraulic_gradient"}, "groundwater", ec)
    depth = P.check_positive(m.get("depth_to_groundwater_m"), path="groundwater.depth_to_groundwater_m", collector=ec)
    gradient = P.check_nonnegative(m.get("hydraulic_gradient"), path="groundwater.hydraulic_gradient", collector=ec)
    if None in (depth, gradient):
        return None
    return GroundwaterConfiguration(depth_to_groundwater_m=depth, hydraulic_gradient=gradient)


def _parse_receptors(raw, ec) -> tuple:
    items = _require_list(raw, "receptors", "receptors", ec)
    if items is None:
        return ()
    out: List[ReceptorDefinition] = []
    allowed = {"receptor_id", "receptor_type", "distance_m", "display_name", "active", "notes"}
    for i, item in enumerate(items):
        base = f"receptors[{i}]"
        if not isinstance(item, Mapping):
            ec.add(base, "type", "receptor must be an object")
            continue
        _reject_unknown_keys(item, allowed, base, ec)
        rid = P.check_stable_id(item.get("receptor_id"), path=f"{base}.receptor_id", collector=ec)
        rtype = parse_enum(ReceptorType, item.get("receptor_type"), path=f"{base}.receptor_type", collector=ec)
        dist = P.check_positive(item.get("distance_m"), path=f"{base}.distance_m", collector=ec)
        name = P.check_nonempty_str(item.get("display_name"), path=f"{base}.display_name", collector=ec)
        active = P.check_bool(item.get("active", True), path=f"{base}.active", collector=ec)
        notes = P.check_optional_str(item.get("notes"), path=f"{base}.notes", collector=ec)
        if None in (rid, rtype, dist, name) or active is None:
            continue
        out.append(ReceptorDefinition(receptor_id=rid, receptor_type=rtype, distance_m=dist,
                                      display_name=name, active=active, notes=notes))
    return tuple(out)


def _parse_constituents(raw, ec) -> tuple:
    items = _require_list(raw, "constituents", "constituents", ec)
    if items is None:
        return ()
    out: List[ConstituentSelection] = []
    allowed = {"constituent_id", "role", "source_concentration", "use_governed_default",
               "source_basis", "notes"}
    for i, item in enumerate(items):
        base = f"constituents[{i}]"
        if not isinstance(item, Mapping):
            ec.add(base, "type", "constituent must be an object")
            continue
        _reject_unknown_keys(item, allowed, base, ec)
        cid = P.check_stable_id(item.get("constituent_id"), path=f"{base}.constituent_id", collector=ec)
        role = parse_enum(ConstituentRole, item.get("role"), path=f"{base}.role", collector=ec)
        conc_raw = item.get("source_concentration")
        conc: Optional[float] = None
        if conc_raw is not None:
            conc = P.check_nonnegative(conc_raw, path=f"{base}.source_concentration", collector=ec)
        use_default = P.check_bool(item.get("use_governed_default", False),
                                   path=f"{base}.use_governed_default", collector=ec)
        basis = parse_enum(EvidenceBasis, item.get("source_basis", "regulatory_default"),
                           path=f"{base}.source_basis", collector=ec)
        notes = P.check_optional_str(item.get("notes"), path=f"{base}.notes", collector=ec)
        if None in (cid, role, basis) or use_default is None:
            continue
        if conc_raw is not None and conc is None:
            continue
        out.append(ConstituentSelection(constituent_id=cid, role=role, source_concentration=conc,
                                        use_governed_default=use_default, source_basis=basis, notes=notes))
    return tuple(out)


def _parse_physics(raw, ec) -> Optional[PhysicsSelection]:
    m = _require_obj(raw, "physics", "physics", ec)
    if m is None:
        return None
    _reject_unknown_keys(m, {"engine", "dispersivity_method"}, "physics", ec)
    engine = P.check_nonempty_str(m.get("engine"), path="physics.engine", collector=ec)
    method = parse_enum(DispersivityMethod, m.get("dispersivity_method"), path="physics.dispersivity_method", collector=ec)
    if None in (engine, method):
        return None
    return PhysicsSelection(engine=engine, dispersivity_method=method)


def _parse_reporting(raw, ec) -> ReportingMetadata:
    if "reporting" not in raw:
        return ReportingMetadata()
    m = _require_obj(raw, "reporting", "reporting", ec)
    if m is None:
        return ReportingMetadata()
    _reject_unknown_keys(m, {"comparison_soil_ids", "notes"}, "reporting", ec)
    ids_raw = m.get("comparison_soil_ids", [])
    ids: List[str] = []
    if not isinstance(ids_raw, list):
        ec.add("reporting.comparison_soil_ids", "type", "must be an array of soil IDs")
    else:
        for j, sid in enumerate(ids_raw):
            v = P.check_stable_id(sid, path=f"reporting.comparison_soil_ids[{j}]", collector=ec)
            if v is not None:
                ids.append(v)
    notes = P.check_optional_str(m.get("notes"), path="reporting.notes", collector=ec)
    return ReportingMetadata(comparison_soil_ids=tuple(ids), notes=notes)


def _parse_assumptions(raw, ec) -> tuple:
    if "assumptions" not in raw:
        return ()
    items = _require_list(raw, "assumptions", "assumptions", ec)
    if items is None:
        return ()
    out: List[DeclaredAssumption] = []
    allowed = {"assumption_id", "description", "basis", "status"}
    for i, item in enumerate(items):
        base = f"assumptions[{i}]"
        if not isinstance(item, Mapping):
            ec.add(base, "type", "assumption must be an object")
            continue
        _reject_unknown_keys(item, allowed, base, ec)
        aid = P.check_stable_id(item.get("assumption_id"), path=f"{base}.assumption_id", collector=ec)
        desc = P.check_nonempty_str(item.get("description"), path=f"{base}.description", collector=ec)
        basis = parse_enum(EvidenceBasis, item.get("basis"), path=f"{base}.basis", collector=ec)
        status = parse_enum(AssumptionStatus, item.get("status"), path=f"{base}.status", collector=ec)
        if None in (aid, desc, basis, status):
            continue
        out.append(DeclaredAssumption(assumption_id=aid, description=desc, basis=basis, status=status))
    return tuple(out)


# ---------------------------------------------------------------------------
# Parser (orchestration)
# ---------------------------------------------------------------------------

def parse_site_case_dict(
    raw: Mapping[str, Any],
    *,
    soil_database: Mapping[str, Any],
    constituent_database: Mapping[str, Any],
) -> SiteCaseV1:
    """Parse and fully validate a raw mapping into a :class:`SiteCaseV1`.

    Order (OSSF-GW-002 §4.4): raw shape -> schema-version selection ->
    structural parsing (accumulated) -> record construction -> cross-field ->
    database resolution -> engine compatibility. No hash or preflight
    determination is produced before this sequence succeeds.
    """
    if not isinstance(raw, Mapping):
        from .errors import FieldValidationError
        raise ContractValidationError([FieldValidationError(
            path="(root)", code="type",
            message=f"site case must be a JSON object; got {type(raw).__name__}",
            invalid_value=type(raw).__name__,
        )])
    _select_schema_version(raw)

    ec = ErrorCollector()
    _reject_unknown_keys(raw, _TOP_LEVEL_KEYS, "(root)", ec)
    site_id = P.check_stable_id(raw.get("site_id"), path="site_id", collector=ec)

    project = _parse_project(raw, ec)
    regloc = _parse_regulatory_location(raw, ec)
    treatment = _parse_treatment(raw, ec)
    source = _parse_source(raw, ec)
    subsurface = _parse_subsurface(raw, ec)
    groundwater = _parse_groundwater(raw, ec)
    receptors = _parse_receptors(raw, ec)
    constituents = _parse_constituents(raw, ec)
    physics = _parse_physics(raw, ec)
    reporting = _parse_reporting(raw, ec)
    assumptions = _parse_assumptions(raw, ec)

    ec.raise_if_any(ContractValidationError, "Site case failed structural validation")

    case = SiteCaseV1(
        schema_version=SCHEMA_VERSION,
        site_id=site_id,
        project=project,
        regulatory_location=regloc,
        treatment=treatment,
        source=source,
        subsurface=subsurface,
        groundwater=groundwater,
        receptors=receptors,
        constituents=constituents,
        physics=physics,
        reporting=reporting,
        assumptions=assumptions,
    )

    # Cross-field / database / engine-compatibility validation.
    from .validation import validate_site_case
    return validate_site_case(
        case, soil_database=soil_database, constituent_database=constituent_database
    )


def load_site_case_json(
    path: Path,
    *,
    soil_database: Mapping[str, Any],
    constituent_database: Mapping[str, Any],
) -> SiteCaseV1:
    """Load and validate a V1 site case from a JSON file."""
    with Path(path).open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return parse_site_case_dict(
        raw, soil_database=soil_database, constituent_database=constituent_database
    )


# ---------------------------------------------------------------------------
# Canonical serialization
# ---------------------------------------------------------------------------

def _enum(value) -> str:
    return value.value


def site_case_to_dict(case: SiteCaseV1) -> dict:
    """Serialize a validated contract to a deterministic JSON-compatible dict.

    Enums become their string values; tuples become arrays. This is the single
    representation used for canonical JSON, hashing, schema validation, and
    artifact metadata.
    """
    return {
        "schema_version": case.schema_version,
        "site_id": case.site_id,
        "project": {
            "name": case.project.name,
            "engineer": case.project.engineer,
            "county": case.project.county,
            "regulatory_authority": case.project.regulatory_authority,
            "description": case.project.description,
        },
        "regulatory_location": {
            "edwards_aquifer_recharge_zone": case.regulatory_location.edwards_aquifer_recharge_zone,
            "edwards_aquifer_transition_zone": case.regulatory_location.edwards_aquifer_transition_zone,
            "edwards_aquifer_contributing_zone": case.regulatory_location.edwards_aquifer_contributing_zone,
            "karst_terrain": case.regulatory_location.karst_terrain,
            "coastal_zone": case.regulatory_location.coastal_zone,
            "notes": case.regulatory_location.notes,
        },
        "treatment": {
            "treatment_level": _enum(case.treatment.treatment_level),
            "disinfection_status": _enum(case.treatment.disinfection_status),
            "disinfection_method": _enum(case.treatment.disinfection_method),
            "notes": case.treatment.notes,
        },
        "source": {
            "design_flow_gpd": case.source.design_flow_gpd,
            "description": case.source.description,
        },
        "subsurface": {
            "soil_id": case.subsurface.soil_id,
            "soil_thickness_m": case.subsurface.soil_thickness_m,
        },
        "groundwater": {
            "depth_to_groundwater_m": case.groundwater.depth_to_groundwater_m,
            "hydraulic_gradient": case.groundwater.hydraulic_gradient,
        },
        "receptors": [
            {
                "receptor_id": r.receptor_id,
                "receptor_type": _enum(r.receptor_type),
                "distance_m": r.distance_m,
                "display_name": r.display_name,
                "active": r.active,
                "notes": r.notes,
            }
            for r in case.receptors
        ],
        "constituents": [
            {
                "constituent_id": c.constituent_id,
                "role": _enum(c.role),
                "source_concentration": c.source_concentration,
                "use_governed_default": c.use_governed_default,
                "source_basis": _enum(c.source_basis),
                "notes": c.notes,
            }
            for c in case.constituents
        ],
        "physics": {
            "engine": case.physics.engine,
            "dispersivity_method": _enum(case.physics.dispersivity_method),
        },
        "reporting": {
            "comparison_soil_ids": list(case.reporting.comparison_soil_ids),
            "notes": case.reporting.notes,
        },
        "assumptions": [
            {
                "assumption_id": a.assumption_id,
                "description": a.description,
                "basis": _enum(a.basis),
                "status": _enum(a.status),
            }
            for a in case.assumptions
        ],
    }


def site_case_to_canonical_json(case: SiteCaseV1) -> str:
    """Deterministic canonical JSON (sorted keys, compact separators)."""
    return json.dumps(site_case_to_dict(case), sort_keys=True, separators=(",", ":"))


def site_case_hash(case: SiteCaseV1) -> str:
    """The single governed hashing route: SHA-256 (16 hex) of the normalized,
    serialized contract. Raw dicts are never hashed for governed execution."""
    from ..governance import sha256_of_json_stable
    return sha256_of_json_stable(site_case_to_dict(case))


def write_site_case_json(case: SiteCaseV1, path: Path) -> None:
    """Write a validated contract as human-readable, deterministic JSON."""
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(site_case_to_dict(case), f, indent=2, sort_keys=True)
        f.write("\n")


# ---------------------------------------------------------------------------
# JSON Schema validation
# ---------------------------------------------------------------------------

def schema_path() -> Path:
    """Absolute path to the checked-in V1 JSON Schema."""
    return Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_FILENAME


def load_schema() -> dict:
    with schema_path().open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_site_case_schema(instance: Any) -> None:
    """Validate a dict (or a :class:`SiteCaseV1`, serialized first) against the
    checked-in JSON Schema. Raises ``jsonschema.ValidationError`` on failure.

    ``jsonschema`` is a declared dependency (see requirements). Imported lazily
    so the rest of this module remains importable without it.
    """
    try:
        import jsonschema  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "jsonschema is required for validate_site_case_schema; "
            "install it (see requirements.txt)."
        ) from exc
    if isinstance(instance, SiteCaseV1):
        instance = site_case_to_dict(instance)
    jsonschema.validate(instance=instance, schema=load_schema())


__all__ = [
    "detect_schema_version",
    "parse_site_case_dict",
    "load_site_case_json",
    "site_case_to_dict",
    "site_case_to_canonical_json",
    "site_case_hash",
    "write_site_case_json",
    "schema_path",
    "load_schema",
    "validate_site_case_schema",
]
