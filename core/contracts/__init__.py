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

__all__ = [
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
