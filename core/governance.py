"""
governance.py — Version constants, attestation decorators, and hash utilities.

Public surface (Tier 2 via core.__init__):
    methodology_attested, screening_boundary

Version constants (Tier 1 via core.__init__):
    METHODOLOGY_VERSION, PREFLIGHT_RULESET_VERSION,
    AUTHORIZATION_SCHEMA_VERSION, OUTPUT_CONTRACT_VERSION

Tier 3 — import via ``core.governance`` only:
    sha256_of_file, sha256_of_json_stable
"""
from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Version constants — bumped per ADR-0007 policy
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION: str = "screening-3.1.0"
"""Screening methodology version string.

Follows ``screening-<MAJOR>.<MINOR>.<PATCH>`` versioning.  Any removal of a
Tier 1 or Tier 2 symbol from ``core.__init__`` constitutes a MAJOR bump.
"""

PREFLIGHT_RULESET_VERSION: str = "preflight-1.0.0"
"""Version of the preflight rule set applied in ``core.preflight``."""

AUTHORIZATION_SCHEMA_VERSION: str = "auth-schema-1.0.0"
"""Version of the authorization schema used in ``core.authorization``."""

OUTPUT_CONTRACT_VERSION: str = "output-1.0.0"
"""Version of the output-contract schema (see docs/OUTPUT_CONTRACT.md)."""


# ---------------------------------------------------------------------------
# Hash helpers — Tier 3 (not re-exported from core.__init__)
# ---------------------------------------------------------------------------

def sha256_of_file(path: Path | str) -> str:
    """Return the full hex SHA-256 digest of a file's bytes.

    Tier 3 — internal helper.  Import via ``core.governance`` only.

    Parameters
    ----------
    path:
        Path to the file to hash.

    Returns
    -------
    str
        64-character lowercase hex digest.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_json_stable(data: Any) -> str:
    """Return the full hex SHA-256 of a JSON-serialised value (keys sorted).

    Tier 3 — internal helper.  Import via ``core.governance`` only.

    Parameters
    ----------
    data:
        A JSON-serialisable Python object.

    Returns
    -------
    str
        64-character lowercase hex digest.
    """
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Attestation decorators — Tier 2
# ---------------------------------------------------------------------------

def methodology_attested(fn: Callable) -> Callable:
    """Mark a function as attested under the current ``METHODOLOGY_VERSION``.

    Tier 2 — Extension API.

    Stores ``__methodology_version__`` and ``__attested__ = True`` on the
    wrapped function so auditing tools can enumerate attested entry points.

    Usage
    -----
    ::

        @methodology_attested
        def my_engine_run(config): ...
    """
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    wrapper.__methodology_version__ = METHODOLOGY_VERSION  # type: ignore[attr-defined]
    wrapper.__attested__ = True  # type: ignore[attr-defined]
    return wrapper


def screening_boundary(fn: Callable) -> Callable:
    """Mark a function as a screening boundary (entry/exit point).

    Tier 2 — Extension API.

    Stores ``__screening_boundary__ = True`` on the wrapped function so static
    analysis can identify the module boundaries that must not be inlined.

    Usage
    -----
    ::

        @screening_boundary
        def evaluate_site(config, soils_db): ...
    """
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    wrapper.__screening_boundary__ = True  # type: ignore[attr-defined]
    return wrapper
