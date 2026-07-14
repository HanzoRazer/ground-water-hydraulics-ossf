"""
core.contracts
==============

Versioned, immutable, unit-explicit governed input contract for OSSF
groundwater screening (OSSF-GW-002).

Public surface grows across commits; see ADR-0005.
"""

from __future__ import annotations

from .enums import (
    AssumptionStatus,
    ConstituentRole,
    DisinfectionMethod,
    DisinfectionStatus,
    DispersivityMethod,
    EvidenceBasis,
    ReceptorType,
    TreatmentLevel,
)
from .errors import (
    ContractError,
    ContractValidationError,
    CrossFieldValidationError,
    FieldValidationError,
    LegacyConfigError,
    UnknownConstituentError,
    UnknownEngineError,
    UnknownSoilError,
    UnsupportedPhysicsOptionError,
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
from .validation import (
    effective_source_concentration,
    resolve_constituent,
    resolve_soil,
    validate_site_case,
)
from .serialization import (
    detect_schema_version,
    load_site_case_json,
    parse_site_case_dict,
    site_case_hash,
    site_case_to_canonical_json,
    site_case_to_dict,
    validate_site_case_schema,
    write_site_case_json,
)

__all__ = [
    "SCHEMA_VERSION",
    "SiteCaseV1",
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
    "validate_site_case",
    "resolve_soil",
    "resolve_constituent",
    "effective_source_concentration",
    "parse_site_case_dict",
    "load_site_case_json",
    "detect_schema_version",
    "site_case_to_dict",
    "site_case_to_canonical_json",
    "site_case_hash",
    "write_site_case_json",
    "validate_site_case_schema",
    "TreatmentLevel",
    "DisinfectionStatus",
    "DisinfectionMethod",
    "ReceptorType",
    "DispersivityMethod",
    "ConstituentRole",
    "EvidenceBasis",
    "AssumptionStatus",
    "ContractError",
    "ContractValidationError",
    "CrossFieldValidationError",
    "FieldValidationError",
    "UnsupportedSchemaVersionError",
    "UnknownSoilError",
    "UnknownConstituentError",
    "UnknownEngineError",
    "UnsupportedPhysicsOptionError",
    "LegacyConfigError",
]
