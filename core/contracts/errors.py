"""
core/contracts/errors.py
========================

Typed error hierarchy for the OSSF ``SiteCaseV1`` input contract (OSSF-GW-002).

Validation never returns an ignorable Boolean. It either returns a fully
valid, immutable contract or raises a typed exception. Structural and
cross-field validation accumulate every problem in one pass and raise a
single :class:`ContractValidationError` carrying a tuple of
:class:`FieldValidationError` records, each pinned to an exact field path
(e.g. ``receptors[1].distance_m``) so the caller can fix everything at once.

Hierarchy::

    ContractError
      ├─ UnsupportedSchemaVersionError
      ├─ ContractValidationError            (.errors: tuple[FieldValidationError])
      │    ├─ CrossFieldValidationError
      │    ├─ UnknownSoilError
      │    ├─ UnknownConstituentError
      │    ├─ UnknownEngineError
      │    └─ UnsupportedPhysicsOptionError
      └─ LegacyConfigError

The contract layer owns data shape, types, units, enums, structural validity,
internal consistency, and database-reference validity. It does NOT own
regulatory suitability — that remains the preflight's exclusive authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Structured field error
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldValidationError:
    """One structured validation problem, pinned to a field path.

    ``invalid_value`` is best-effort context; sensitive or excessively large
    values may be omitted (left ``None``) by the producer.
    """

    path: str
    code: str
    message: str
    invalid_value: Optional[object] = None

    def __str__(self) -> str:
        return f"{self.path}: {self.message} [{self.code}]"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ContractError(Exception):
    """Base class for every OSSF site-case contract failure."""


class UnsupportedSchemaVersionError(ContractError):
    """Raised when a case declares a missing, blank, malformed, or unsupported
    ``schema_version`` (or supplies a result-schema identifier as an input
    schema)."""


class ContractValidationError(ContractError):
    """Raised when a case fails structural and/or cross-field validation.

    Carries every problem found in a single pass as a tuple of
    :class:`FieldValidationError`, so callers get an actionable, complete list
    rather than one-error-at-a-time.
    """

    def __init__(
        self,
        errors: Sequence[FieldValidationError],
        message: str = "Invalid OSSF site case",
    ) -> None:
        self.errors: Tuple[FieldValidationError, ...] = tuple(errors)
        detail = "; ".join(str(e) for e in self.errors) or "(no detail)"
        super().__init__(f"{message}: {detail}")


class CrossFieldValidationError(ContractValidationError):
    """Structural fields were individually valid but are mutually
    inconsistent (e.g. a disinfection method supplied while status is
    ``none``)."""


class UnknownSoilError(ContractValidationError):
    """A referenced soil ID does not exist in the soil database."""


class UnknownConstituentError(ContractValidationError):
    """A referenced constituent ID does not exist in the constituent
    database."""


class UnknownEngineError(ContractValidationError):
    """The selected physics engine is not registered."""


class UnsupportedPhysicsOptionError(ContractValidationError):
    """A physics option (e.g. dispersivity method) is not supported by the
    selected engine."""


class LegacyConfigError(ContractError):
    """Raised when an explicit legacy (pre-V1) configuration cannot be
    converted deterministically — most importantly when a value is
    materially ambiguous and must not be guessed."""


# ---------------------------------------------------------------------------
# Evidence layer (OSSF-GW-003)
# ---------------------------------------------------------------------------

class EvidenceContractError(ContractError):
    """Base class for evidence-layer contract failures."""


class MissingEvidenceBindingError(EvidenceContractError):
    """A load-bearing field lacks a required evidence binding."""


class EvidenceContradictionError(EvidenceContractError):
    """Conflicting provenance or bindings for the same field."""


class EvidenceReviewError(EvidenceContractError):
    """Evidence review status blocks authorization."""


class UnknownEvidenceReferenceError(EvidenceContractError):
    """A binding references a missing evidence or assumption record."""


class UnsupportedEvidenceSchemaError(EvidenceContractError):
    """Evidence metadata or schema version is not supported."""


# ---------------------------------------------------------------------------
# Error collector
# ---------------------------------------------------------------------------

class ErrorCollector:
    """Accumulates multiple independent :class:`FieldValidationError` in one
    validation pass, then raises them together.

    Usage::

        ec = ErrorCollector()
        ec.add("subsurface.effective_porosity_fraction", "range",
               "must be in (0, 1]", invalid_value=1.4)
        ...
        ec.raise_if_any()   # raises ContractValidationError if non-empty
    """

    def __init__(self) -> None:
        self._errors: List[FieldValidationError] = []

    def add(
        self,
        path: str,
        code: str,
        message: str,
        invalid_value: Optional[object] = None,
    ) -> None:
        self._errors.append(
            FieldValidationError(
                path=path, code=code, message=message, invalid_value=invalid_value
            )
        )

    def extend(self, errors: Iterable[FieldValidationError]) -> None:
        self._errors.extend(errors)

    def merge(self, other: "ErrorCollector") -> None:
        self._errors.extend(other._errors)

    @property
    def errors(self) -> Tuple[FieldValidationError, ...]:
        return tuple(self._errors)

    def __bool__(self) -> bool:
        return bool(self._errors)

    def __len__(self) -> int:
        return len(self._errors)

    def raise_if_any(
        self,
        exc_type: type = ContractValidationError,
        message: str = "Invalid OSSF site case",
    ) -> None:
        if self._errors:
            raise exc_type(self._errors, message=message)


__all__ = [
    "FieldValidationError",
    "ContractError",
    "UnsupportedSchemaVersionError",
    "ContractValidationError",
    "CrossFieldValidationError",
    "UnknownSoilError",
    "UnknownConstituentError",
    "UnknownEngineError",
    "UnsupportedPhysicsOptionError",
    "LegacyConfigError",
    "EvidenceContractError",
    "MissingEvidenceBindingError",
    "EvidenceContradictionError",
    "EvidenceReviewError",
    "UnknownEvidenceReferenceError",
    "UnsupportedEvidenceSchemaError",
    "ErrorCollector",
]
