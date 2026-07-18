"""
core/contracts/site_case_v1.py
==============================

The canonical, versioned, immutable OSSF site-case input contract
(OSSF-GW-002), plus its nested typed records.

These records own *data shape*: field presence, types, canonical units
(explicit in every dimensional field name), enum values, and record-level
local validity. They do NOT perform database I/O, cross-record consistency,
or regulatory interpretation — those live in ``validation.py`` and
``preflight.py`` respectively.

Every record is a frozen dataclass and validates itself in ``__post_init__``:

* enum fields accept either the enum member or its canonical string value
  and are coerced to the member;
* dimensional numeric fields are validated (finite, in-range) and normalized
  to ``float`` so canonical serialization is deterministic;
* collection fields are coerced ``list`` -> ``tuple`` so instances are
  immutable and hashable-in-spirit.

Local validation is fail-fast (one error). Multi-error accumulation with full
field paths is the parser's job (``serialization.parse_site_case_dict``),
which validates every field into a single ``ContractValidationError`` before
any record is constructed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from . import _primitives as P
from .enums import (
    AssumptionStatus,
    ConstituentRole,
    DisinfectionMethod,
    DisinfectionStatus,
    DispersivityMethod,
    EvidenceBasis,
    ProvenanceClass,
    ReceptorType,
    TreatmentLevel,
    parse_enum,
    parse_provenance_class,
)
from .errors import UnsupportedSchemaVersionError
from .evidence_records import EvidenceRecord, FieldEvidenceBinding

# ---------------------------------------------------------------------------
# Version anchor
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "ossf-site-case-1.1.0"


def _set(obj, name, value) -> None:
    object.__setattr__(obj, name, value)


# ---------------------------------------------------------------------------
# Nested records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectMetadata:
    """Non-interpretive project identification. All free-form; no operational
    branch depends on these values."""

    name: str
    engineer: str
    county: str
    regulatory_authority: str
    description: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "name", P.check_nonempty_str(self.name, path="project.name"))
        _set(self, "engineer", P.check_nonempty_str(self.engineer, path="project.engineer"))
        _set(self, "county", P.check_nonempty_str(self.county, path="project.county"))
        _set(self, "regulatory_authority",
             P.check_nonempty_str(self.regulatory_authority, path="project.regulatory_authority"))
        _set(self, "description", P.check_optional_str(self.description, path="project.description"))


@dataclass(frozen=True)
class RegulatoryLocation:
    """Structured regulatory-zone facts. Booleans, not narrative. SAD-001 /
    SAD-002 (EARZ / karst) key off these."""

    edwards_aquifer_recharge_zone: bool = False
    edwards_aquifer_transition_zone: bool = False
    edwards_aquifer_contributing_zone: bool = False
    karst_terrain: bool = False
    coastal_zone: bool = False
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        for name in (
            "edwards_aquifer_recharge_zone",
            "edwards_aquifer_transition_zone",
            "edwards_aquifer_contributing_zone",
            "karst_terrain",
            "coastal_zone",
        ):
            _set(self, name, P.check_bool(getattr(self, name), path=f"regulatory_location.{name}"))
        _set(self, "notes", P.check_optional_str(self.notes, path="regulatory_location.notes"))


@dataclass(frozen=True)
class TreatmentConfiguration:
    """Structured treatment + disinfection. Replaces the free-form
    ``source.treatment_class`` string. SAD-007 keys off ``treatment_level``
    and ``disinfection_status`` — never off substring searches."""

    treatment_level: TreatmentLevel
    disinfection_status: DisinfectionStatus
    disinfection_method: DisinfectionMethod = DisinfectionMethod.NONE
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "treatment_level",
             parse_enum(TreatmentLevel, self.treatment_level, path="treatment.treatment_level"))
        _set(self, "disinfection_status",
             parse_enum(DisinfectionStatus, self.disinfection_status, path="treatment.disinfection_status"))
        _set(self, "disinfection_method",
             parse_enum(DisinfectionMethod, self.disinfection_method, path="treatment.disinfection_method"))
        _set(self, "notes", P.check_optional_str(self.notes, path="treatment.notes"))


@dataclass(frozen=True)
class SourceConfiguration:
    """Effluent source term (excluding per-constituent concentrations, which
    live on each ``ConstituentSelection``)."""

    design_flow_gpd: float
    description: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "design_flow_gpd",
             P.check_positive(self.design_flow_gpd, path="source.design_flow_gpd"))
        _set(self, "description", P.check_optional_str(self.description, path="source.description"))


@dataclass(frozen=True)
class SubsurfaceConfiguration:
    """Soil reference (by stable ID) and unsaturated-zone thickness. Soil
    physical properties (K_sat, porosity, bulk density) are resolved from the
    soil database, never duplicated here."""

    soil_id: str
    soil_thickness_m: float

    def __post_init__(self) -> None:
        _set(self, "soil_id", P.check_stable_id(self.soil_id, path="subsurface.soil_id"))
        _set(self, "soil_thickness_m",
             P.check_positive(self.soil_thickness_m, path="subsurface.soil_thickness_m"))


@dataclass(frozen=True)
class GroundwaterConfiguration:
    """Groundwater depth and hydraulic gradient (both canonical-unit fields)."""

    depth_to_groundwater_m: float
    hydraulic_gradient: float

    def __post_init__(self) -> None:
        _set(self, "depth_to_groundwater_m",
             P.check_positive(self.depth_to_groundwater_m, path="groundwater.depth_to_groundwater_m"))
        # Gradient must be finite and non-negative. A negative gradient is a
        # sign-convention/input error (flow away from receptor); it is rejected
        # by the contract before it can reach preflight (SAD-006 still refuses
        # it defensively). Zero is permitted (SAD-006 will warn).
        _set(self, "hydraulic_gradient",
             P.check_nonnegative(self.hydraulic_gradient, path="groundwater.hydraulic_gradient"))


@dataclass(frozen=True)
class ReceptorDefinition:
    """A single receptor with a stable ID, type, and canonical distance."""

    receptor_id: str
    receptor_type: ReceptorType
    distance_m: float
    display_name: str
    active: bool = True
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "receptor_id", P.check_stable_id(self.receptor_id, path="receptors[].receptor_id"))
        _set(self, "receptor_type",
             parse_enum(ReceptorType, self.receptor_type, path="receptors[].receptor_type"))
        _set(self, "distance_m", P.check_positive(self.distance_m, path="receptors[].distance_m"))
        _set(self, "display_name",
             P.check_nonempty_str(self.display_name, path="receptors[].display_name"))
        _set(self, "active", P.check_bool(self.active, path="receptors[].active"))
        _set(self, "notes", P.check_optional_str(self.notes, path="receptors[].notes"))


@dataclass(frozen=True)
class ConstituentSelection:
    """A constituent to evaluate, referenced by stable database ID.

    Source concentration is either explicit (``source_concentration`` set) or
    a *visibly selected* governed default (``use_governed_default=True``,
    resolved from the constituent database at validation time). Exactly one of
    the two must hold — silent inference from the constituent name is
    prohibited (OSSF-GW-002 §4.9).
    """

    constituent_id: str
    role: ConstituentRole
    source_concentration: Optional[float] = None
    use_governed_default: bool = False
    source_basis: EvidenceBasis = EvidenceBasis.REGULATORY_DEFAULT
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        _set(self, "constituent_id",
             P.check_stable_id(self.constituent_id, path="constituents[].constituent_id"))
        _set(self, "role", parse_enum(ConstituentRole, self.role, path="constituents[].role"))
        if self.source_concentration is not None:
            _set(self, "source_concentration",
                 P.check_nonnegative(self.source_concentration,
                                     path="constituents[].source_concentration"))
        _set(self, "use_governed_default",
             P.check_bool(self.use_governed_default, path="constituents[].use_governed_default"))
        _set(self, "source_basis",
             parse_enum(EvidenceBasis, self.source_basis, path="constituents[].source_basis"))
        _set(self, "notes", P.check_optional_str(self.notes, path="constituents[].notes"))


@dataclass(frozen=True)
class PhysicsSelection:
    """Engine and method selection. Engine registration and method/engine
    compatibility are checked by ``validation.py`` (not at physics time)."""

    engine: str
    dispersivity_method: DispersivityMethod

    def __post_init__(self) -> None:
        _set(self, "engine", P.check_nonempty_str(self.engine, path="physics.engine"))
        _set(self, "dispersivity_method",
             parse_enum(DispersivityMethod, self.dispersivity_method, path="physics.dispersivity_method"))


@dataclass(frozen=True)
class ReportingMetadata:
    """Reporting configuration. ``comparison_soil_ids`` drives the governed
    comparison-soil report section (existence checked against the soil DB)."""

    comparison_soil_ids: Tuple[str, ...] = ()
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        ids = self.comparison_soil_ids
        if isinstance(ids, list):
            ids = tuple(ids)
        if not isinstance(ids, tuple):
            from .errors import ContractValidationError, FieldValidationError
            raise ContractValidationError([FieldValidationError(
                path="reporting.comparison_soil_ids", code="type",
                message="must be a list/tuple of soil IDs", invalid_value=ids)])
        _set(self, "comparison_soil_ids",
             tuple(P.check_stable_id(x, path=f"reporting.comparison_soil_ids[{i}]")
                   for i, x in enumerate(ids)))
        _set(self, "notes", P.check_optional_str(self.notes, path="reporting.notes"))


@dataclass(frozen=True)
class DeclaredAssumption:
    """A declared engineering assumption. Rationale is free-form; no
    operational branch depends on it."""

    assumption_id: str
    description: str
    basis: EvidenceBasis
    status: AssumptionStatus

    def __post_init__(self) -> None:
        _set(self, "assumption_id",
             P.check_stable_id(self.assumption_id, path="assumptions[].assumption_id"))
        _set(self, "description",
             P.check_nonempty_str(self.description, path="assumptions[].description"))
        _set(self, "basis", parse_enum(EvidenceBasis, self.basis, path="assumptions[].basis"))
        _set(self, "status", parse_enum(AssumptionStatus, self.status, path="assumptions[].status"))


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SiteCaseV1:
    """The canonical, immutable, unit-explicit governed OSSF site-case
    contract. Only a fully validated instance may be hashed, authorized, or
    simulated."""

    site_id: str
    project: ProjectMetadata
    regulatory_location: RegulatoryLocation
    treatment: TreatmentConfiguration
    source: SourceConfiguration
    subsurface: SubsurfaceConfiguration
    groundwater: GroundwaterConfiguration
    receptors: Tuple[ReceptorDefinition, ...]
    constituents: Tuple[ConstituentSelection, ...]
    physics: PhysicsSelection
    reporting: ReportingMetadata = field(default_factory=ReportingMetadata)
    assumptions: Tuple[DeclaredAssumption, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"SiteCaseV1 requires schema_version '{SCHEMA_VERSION}'; "
                f"got {self.schema_version!r}."
            )
        _set(self, "site_id", P.check_stable_id(self.site_id, path="site_id"))
        _set(self, "receptors", tuple(self.receptors))
        _set(self, "constituents", tuple(self.constituents))
        _set(self, "assumptions", tuple(self.assumptions))


__all__ = [
    "SCHEMA_VERSION",
    "ProjectMetadata",
    "RegulatoryLocation",
    "TreatmentConfiguration",
    "SourceConfiguration",
    "SubsurfaceConfiguration",
    "GroundwaterConfiguration",
    "ReceptorDefinition",
    "ConstituentSelection",
    "PhysicsSelection",
    "ReportingMetadata",
    "DeclaredAssumption",
    "SiteCaseV1",
]
