"""
core.contracts
==============

Versioned, immutable, unit-explicit governed input contract for OSSF
groundwater screening (OSSF-GW-002 / OSSF-GW-003).

This package owns the *input boundary*: it turns raw JSON into a validated,
immutable :class:`SiteCaseV1` before anything downstream (evidence gate,
preflight, authorization, physics, attestation) runs. Malformed, ambiguous,
contradictory, or physically implausible inputs are rejected here — before
authorization or physics — with actionable, field-pathed errors.

It does NOT own regulatory suitability (preflight), execution permission
(authorization), or numerical evaluation (physics).
"""

from __future__ import annotations

from .enums import (
    AssumptionStatus,
    ConstituentRole,
    DisinfectionMethod,
    DisinfectionStatus,
    DispersivityMethod,
    EvidenceBasis,
    EvidenceConfidence,
    EvidenceReviewStatus,
    FieldTier,
    ProvenanceClass,
    ReceptorType,
    TreatmentLevel,
    parse_provenance_class,
    provenance_from_evidence_basis,
)
from .errors import (
    ContractError,
    ContractValidationError,
    CrossFieldValidationError,
    EvidenceCompletenessError,
    EvidenceContradictionError,
    EvidenceContractError,
    EvidenceReviewGateError,
    EvidenceValidationError,
    FieldValidationError,
    LegacyConfigError,
    UnknownConstituentError,
    UnknownEngineError,
    UnknownSoilError,
    UnsupportedPhysicsOptionError,
    UnsupportedSchemaVersionError,
)
from .evidence_records import EvidenceRecord, FieldEvidenceBinding
from .evidence_registry import RequiredBinding, required_bindings_for_case
from .evidence_validation import (
    CriticalBindingIssue,
    EvidenceValidationResult,
    EvidenceWarning,
    compute_evidence_digest,
    effective_review_status,
    evidence_failure_artifact,
    evidence_result_summary_dict,
    iter_critical_binding_acceptance_issues,
    validate_evidence_layer,
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
    active_receptors,
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
from .legacy import convert_legacy_site_config_to_v1

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
    "EvidenceRecord",
    "FieldEvidenceBinding",
    "RequiredBinding",
    "required_bindings_for_case",
    "EvidenceValidationResult",
    "EvidenceWarning",
    "validate_evidence_layer",
    "compute_evidence_digest",
    "effective_review_status",
    "iter_critical_binding_acceptance_issues",
    "CriticalBindingIssue",
    "evidence_result_summary_dict",
    "evidence_failure_artifact",
    "validate_site_case",
    "active_receptors",
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
    "convert_legacy_site_config_to_v1",
    "TreatmentLevel",
    "DisinfectionStatus",
    "DisinfectionMethod",
    "ReceptorType",
    "DispersivityMethod",
    "ConstituentRole",
    "EvidenceBasis",
    "ProvenanceClass",
    "EvidenceReviewStatus",
    "EvidenceConfidence",
    "FieldTier",
    "AssumptionStatus",
    "parse_provenance_class",
    "provenance_from_evidence_basis",
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
    "EvidenceContractError",
    "EvidenceValidationError",
    "EvidenceCompletenessError",
    "EvidenceContradictionError",
    "EvidenceReviewGateError",
]
