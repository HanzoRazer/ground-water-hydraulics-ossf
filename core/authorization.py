"""
authorization.py — Authorization construction, derivation, and validation.

Public surface (Tier 1 via core.__init__):
    build_authorization, AuthorizationError

Internal (Tier 3 — import via ``core.authorization`` only):
    _derive_authorization_id
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


class AuthorizationError(Exception):
    """Raised when an authorization cannot be constructed or is invalid.

    Tier 1 — Consumer API.
    """


def _derive_authorization_id(
    site_id: str,
    methodology_version: str,
    issued_utc: str,
) -> str:
    """Derive a deterministic authorization ID from its key fields.

    The ID is a 16-character prefix of the SHA-256 of the canonical JSON
    representation of the three fields, with keys sorted.

    Tier 3 — internal helper.  Import via ``core.authorization`` only.

    Parameters
    ----------
    site_id:
        Unique site identifier.
    methodology_version:
        Methodology version string at time of authorization.
    issued_utc:
        ISO-8601 UTC timestamp of authorization issuance.

    Returns
    -------
    str
        16-character lowercase hex token.
    """
    payload = json.dumps(
        {
            "site_id": site_id,
            "methodology_version": methodology_version,
            "issued_utc": issued_utc,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class Authorization:
    """An authorization record for a screening run.

    Consumers receive this via :func:`build_authorization`.  The
    ``authorization_id`` field is derived deterministically from the
    other three fields; it is not accepted as input.
    """

    site_id: str
    methodology_version: str
    issued_utc: str
    authorization_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.authorization_id = _derive_authorization_id(
            self.site_id, self.methodology_version, self.issued_utc
        )


def build_authorization(
    site_id: str,
    methodology_version: str,
    issued_utc: str,
) -> Authorization:
    """Construct a validated :class:`Authorization` record.

    Tier 1 — Consumer API.

    Parameters
    ----------
    site_id:
        Non-empty unique site identifier.
    methodology_version:
        Non-empty methodology version string (e.g. ``"screening-3.1.0"``).
    issued_utc:
        Non-empty ISO-8601 UTC timestamp of authorization issuance.

    Returns
    -------
    Authorization
        A new Authorization with a derived ``authorization_id``.

    Raises
    ------
    AuthorizationError
        If any required field is empty or not a string.
    """
    if not isinstance(site_id, str) or not site_id:
        raise AuthorizationError("site_id must be a non-empty string.")
    if not isinstance(methodology_version, str) or not methodology_version:
        raise AuthorizationError("methodology_version must be a non-empty string.")
    if not isinstance(issued_utc, str) or not issued_utc:
        raise AuthorizationError("issued_utc must be a non-empty string.")
    return Authorization(
        site_id=site_id,
        methodology_version=methodology_version,
        issued_utc=issued_utc,
    )
