"""
core/contracts/enums.py
=======================

Canonical enumerated operational values for the ``SiteCaseV1`` contract
(OSSF-GW-002).

Operational behavior must NEVER depend on substring searches of free-form
text. Every operational value that a rule, authorization, or engine-selection
step depends on is a closed enum here. Free-form notes remain allowed (see
``site_case_v1``) but carry no operational meaning.

All enums are ``str``-valued so canonical serialization emits their ``.value``
directly and JSON Schema can enumerate them. Parsing is strict:
:func:`parse_enum` rejects unknown values with a readable list of accepted
options and never silently normalizes.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Type, TypeVar


class TreatmentLevel(str, Enum):
    """Effluent treatment classification (structured replacement for the
    free-form ``source.treatment_class`` string)."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    ADVANCED_SECONDARY = "advanced_secondary"


class DisinfectionStatus(str, Enum):
    """Whether the effluent is disinfected. Separated from treatment level so
    no rule needs to parse a combined narrative string."""

    NONE = "none"
    DISINFECTED = "disinfected"


class DisinfectionMethod(str, Enum):
    """Disinfection method. ``NONE`` is required iff status is ``none``."""

    NONE = "none"
    CHLORINE = "chlorine"
    UV = "uv"
    OZONE = "ozone"
    OTHER = "other"


class ReceptorType(str, Enum):
    """Receptor classification. Type-specific setback minimums in the
    preflight (SAD-005) key off this enum, not off a display name."""

    PRIVATE_WELL = "private_well"
    PUBLIC_WELL = "public_well"
    PROPERTY_BOUNDARY = "property_boundary"
    SURFACE_WATER = "surface_water"


class DispersivityMethod(str, Enum):
    """Longitudinal-dispersivity estimation method. Compatibility with the
    selected engine is checked by contract validation, not at physics time."""

    EPA_SSG = "epa_ssg"
    XU_ECKSTEIN = "xu_eckstein"


class ConstituentRole(str, Enum):
    """How a constituent participates in the screening outcome.

    ``GATING`` constituents drive pass/fail. ``REFERENCE_ONLY`` constituents
    (e.g. nitrate under advective-reference reporting) are reported but never
    gate the result. Replaces the free-form ``reporting.nitrate_reporting_mode``
    branch as an operational input."""

    GATING = "gating"
    REFERENCE_ONLY = "reference_only"


class EvidenceBasis(str, Enum):
    """Provenance basis for a declared value or assumption."""

    MEASURED = "measured"
    ESTIMATED = "estimated"
    LITERATURE = "literature"
    REGULATORY_DEFAULT = "regulatory_default"
    ASSUMED = "assumed"


class AssumptionStatus(str, Enum):
    """Lifecycle status of a declared engineering assumption."""

    ASSUMED = "assumed"
    VERIFIED = "verified"
    PENDING_VERIFICATION = "pending_verification"


class ProvenanceClass(str, Enum):
    """Canonical provenance authority for load-bearing evidence (OSSF-GW-003).

  Replaces ad-hoc ``EvidenceBasis`` on 1.1.0 contracts. Legacy ``EvidenceBasis``
  values map into this enum at parse/migration time.
    """

    MEASURED = "measured"
    DOCUMENTED = "documented"
    DATABASE_DERIVED = "database_derived"
    ASSUMED = "assumed"
    REGULATORY_DEFAULT = "regulatory_default"


class EvidenceConfidence(str, Enum):
    """Practitioner-declared confidence in an evidence record."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class EvidenceReviewStatus(str, Enum):
    """Practitioner review status for evidence records and bindings."""

    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class FieldTier(str, Enum):
    """Load-bearing field tier for evidence gating policy."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    INFORMATIONAL = "informational"


_EVIDENCE_BASIS_TO_PROVENANCE: dict[EvidenceBasis, ProvenanceClass] = {
    EvidenceBasis.MEASURED: ProvenanceClass.MEASURED,
    EvidenceBasis.ESTIMATED: ProvenanceClass.ASSUMED,
    EvidenceBasis.LITERATURE: ProvenanceClass.DOCUMENTED,
    EvidenceBasis.REGULATORY_DEFAULT: ProvenanceClass.REGULATORY_DEFAULT,
    EvidenceBasis.ASSUMED: ProvenanceClass.ASSUMED,
}


def evidence_basis_to_provenance_class(basis: EvidenceBasis) -> ProvenanceClass:
    """Map a legacy ``EvidenceBasis`` value to ``ProvenanceClass``."""
    return _EVIDENCE_BASIS_TO_PROVENANCE[basis]


E = TypeVar("E", bound=Enum)


def accepted_values(enum_cls: Type[Enum]) -> str:
    """Readable, comma-separated list of an enum's accepted string values."""
    return ", ".join(repr(m.value) for m in enum_cls)


def parse_enum(
    enum_cls: Type[E],
    value: object,
    *,
    path: str,
    collector: Optional["object"] = None,
    case_insensitive: bool = False,
) -> Optional[E]:
    """Strictly parse ``value`` into a member of ``enum_cls``.

    On success returns the member. On failure, if ``collector`` is provided
    (an :class:`~core.contracts.errors.ErrorCollector`), records a structured
    error at ``path`` and returns ``None``; otherwise raises
    :class:`~core.contracts.errors.ContractValidationError`.

    ``case_insensitive`` is opt-in and deterministic (lower-cased match). By
    default matching is exact; unknown values are never silently coerced.
    """
    from .errors import ContractValidationError, FieldValidationError

    if isinstance(value, enum_cls):
        return value

    matched: Optional[E] = None
    if isinstance(value, str):
        if case_insensitive:
            lowered = value.lower()
            for member in enum_cls:
                if member.value.lower() == lowered:
                    matched = member
                    break
        else:
            for member in enum_cls:
                if member.value == value:
                    matched = member
                    break

    if matched is not None:
        return matched

    message = (
        f"{value!r} is not a valid {enum_cls.__name__}; "
        f"accepted values are {accepted_values(enum_cls)}"
    )
    if collector is not None:
        collector.add(path, "enum", message, invalid_value=value)
        return None
    raise ContractValidationError(
        [FieldValidationError(path=path, code="enum", message=message, invalid_value=value)]
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
    "ProvenanceClass",
    "EvidenceConfidence",
    "EvidenceReviewStatus",
    "FieldTier",
    "evidence_basis_to_provenance_class",
    "accepted_values",
    "parse_enum",
]
