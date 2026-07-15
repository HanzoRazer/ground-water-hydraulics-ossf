"""
core/contracts/_primitives.py
=============================

Internal primitive scalar validators shared by record-level local validation
(``site_case_v1``) and site-level cross-field validation (``validation``).

Kept in a dependency-free internal module so both layers can use identical
rules without an import cycle (``validation`` imports ``site_case_v1``; both
import these primitives). Not part of the public contract surface.

Each validator has one shape:

    check_*(value, *, path, collector=None) -> Optional[<typed value>]

* If ``value`` is valid, the typed value is returned.
* If invalid and a ``collector`` (``ErrorCollector``) is supplied, a
  structured error is appended at ``path`` and ``None`` is returned so the
  caller can keep accumulating.
* If invalid and no collector is supplied, a single-error
  :class:`ContractValidationError` is raised (fail-fast — used by record
  ``__post_init__`` local validation).

Booleans are never accepted where a number is required (``bool`` is a subtype
of ``int`` in Python; silently treating ``True`` as ``1`` would hide input
errors).
"""

from __future__ import annotations

import math
import re
from typing import Optional

from .errors import ContractValidationError, ErrorCollector, FieldValidationError

_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _fail(
    path: str,
    code: str,
    message: str,
    invalid_value: object,
    collector: Optional[ErrorCollector],
):
    if collector is not None:
        collector.add(path, code, message, invalid_value=invalid_value)
        return None
    raise ContractValidationError(
        [FieldValidationError(path=path, code=code, message=message, invalid_value=invalid_value)]
    )


def check_finite_number(
    value: object, *, path: str, collector: Optional[ErrorCollector] = None
) -> Optional[float]:
    """Accept a finite ``int``/``float`` (never ``bool``, ``NaN`` or ``inf``)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _fail(path, "type", "must be a finite number", value, collector)
    f = float(value)
    if math.isnan(f) or math.isinf(f):
        return _fail(path, "nonfinite", "must be a finite number (not NaN/inf)", value, collector)
    return f


def check_positive(
    value: object, *, path: str, collector: Optional[ErrorCollector] = None
) -> Optional[float]:
    f = check_finite_number(value, path=path, collector=collector)
    if f is None:
        return None
    if f <= 0.0:
        return _fail(path, "range", "must be a positive number (> 0)", value, collector)
    return f


def check_nonnegative(
    value: object, *, path: str, collector: Optional[ErrorCollector] = None
) -> Optional[float]:
    f = check_finite_number(value, path=path, collector=collector)
    if f is None:
        return None
    if f < 0.0:
        return _fail(path, "range", "must be a non-negative number (>= 0)", value, collector)
    return f


def check_fraction_0_1(
    value: object, *, path: str, collector: Optional[ErrorCollector] = None
) -> Optional[float]:
    """Accept a fraction in the half-open interval ``(0, 1]``."""
    f = check_finite_number(value, path=path, collector=collector)
    if f is None:
        return None
    if not (0.0 < f <= 1.0):
        return _fail(path, "range", "must be a fraction in (0, 1]", value, collector)
    return f


def check_nonempty_str(
    value: object, *, path: str, collector: Optional[ErrorCollector] = None
) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return _fail(path, "required", "must be a non-empty string", value, collector)
    return value


def check_stable_id(
    value: object, *, path: str, collector: Optional[ErrorCollector] = None
) -> Optional[str]:
    """Accept a stable identifier: non-empty, ``[A-Za-z0-9][A-Za-z0-9_.-]*``."""
    if not isinstance(value, str) or not _STABLE_ID_RE.match(value):
        return _fail(
            path,
            "stable_id",
            "must be a stable identifier matching [A-Za-z0-9][A-Za-z0-9_.-]*",
            value,
            collector,
        )
    return value


def check_bool(
    value: object, *, path: str, collector: Optional[ErrorCollector] = None
) -> Optional[bool]:
    if not isinstance(value, bool):
        return _fail(path, "type", "must be a boolean", value, collector)
    return value


def check_optional_str(
    value: object, *, path: str, collector: Optional[ErrorCollector] = None
) -> Optional[str]:
    """Accept ``None`` or a string (free-form notes fields)."""
    if value is None:
        return None
    if not isinstance(value, str):
        _fail(path, "type", "must be a string or null", value, collector)
        return None
    return value
