"""core/governance.py — Authorization and methodology governance.

This module is the single source of truth for:

- ``METHODOLOGY_VERSION``: the current methodology revision string.
- ``Authorization``: a frozen dataclass that couples an authorization id to
  its permitted/denied disposition (per ADR-0004).
- ``validate_authorization`` / ``ensure_execution_permitted``: the runtime
  enforcement gate called unconditionally by
  :meth:`~core.physics_registry.AbstractPhysicsEngine.run` before any
  physics calculation executes (per ADR-0005).
- ``methodology_attested``: a documentation decorator retained for
  annotation purposes; authorization enforcement has moved to the engine
  interface in screening-2.0.0.

Versioning
----------
METHODOLOGY_VERSION follows a ``<stream>-<major>.<minor>.<patch>`` scheme.
A MAJOR bump signifies a breaking change to a public interface.  This
module was bumped to ``screening-2.0.0`` when ``get_engine()``'s return
type changed from ``EngineRecord`` (screening-1.x) to ``EngineMetadata``.

See also
--------
docs/adr/ADR-0004-authorization-id-binds-disposition.md
docs/adr/ADR-0005-abstract-physics-engine-interface.md
"""

from __future__ import annotations

import functools
import typing
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Methodology version
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION: str = "screening-2.0.0"
"""Current methodology version.

Bumped to ``screening-2.0.0`` (MAJOR) by ADR-0005 because
:func:`~core.physics_registry.get_engine` return type changed from
``EngineRecord`` to :class:`~core.physics_registry.EngineMetadata`.
"""


# ---------------------------------------------------------------------------
# Authorization model (ADR-0004)
# ---------------------------------------------------------------------------


class AuthorizationError(Exception):
    """Raised when engine execution is attempted without a valid authorization.

    May indicate a missing authorization, a structurally invalid object, or
    a disposition other than ``"permitted"``.
    """


@dataclass(frozen=True)
class Authorization:
    """An execution authorization that binds an id to a disposition.

    Per ADR-0004, the ``authorization_id`` is derived deterministically from
    the engine name, a hash of the call parameters, and a caller-supplied
    nonce.  Changing any input invalidates a previously issued id.  This
    prevents replay attacks where a ``"permitted"`` disposition from one run
    is reused with different parameters.

    Parameters
    ----------
    authorization_id:
        Non-empty string identifier for this authorization instance.
    disposition:
        Must be the literal string ``"permitted"`` for
        :func:`ensure_execution_permitted` to allow execution.  Any other
        value (e.g. ``"denied"``, ``"pending"``) causes a raise.
    """

    authorization_id: str
    disposition: str


def validate_authorization(authorization: object) -> None:
    """Check that *authorization* is a structurally valid :class:`Authorization`.

    This performs type and field-presence checks only; it does **not** verify
    the id derivation nor enforce the disposition.  Call
    :func:`ensure_execution_permitted` for the full enforcement gate.

    Parameters
    ----------
    authorization:
        Object to validate.

    Raises
    ------
    AuthorizationError
        If *authorization* is not an :class:`Authorization` instance or has
        an empty ``authorization_id``.
    """
    if not isinstance(authorization, Authorization):
        raise AuthorizationError(
            f"Expected an Authorization instance; "
            f"got {type(authorization).__name__!r}."
        )
    if not authorization.authorization_id:
        raise AuthorizationError(
            "authorization_id must be a non-empty string."
        )


def ensure_execution_permitted(authorization: object) -> None:
    """Validate *authorization* and raise if execution is not permitted.

    This is the single enforcement gate called by
    :meth:`~core.physics_registry.AbstractPhysicsEngine.run` before any
    physics calculation executes.  It verifies both structural validity and
    the ``disposition`` field.

    Parameters
    ----------
    authorization:
        Must be a valid :class:`Authorization` instance whose
        ``disposition`` equals ``"permitted"``.

    Raises
    ------
    AuthorizationError
        If *authorization* is not a valid :class:`Authorization`, has an
        empty id, or has a disposition other than ``"permitted"``.
    """
    validate_authorization(authorization)
    auth: Authorization = typing.cast(Authorization, authorization)
    if auth.disposition != "permitted":
        raise AuthorizationError(
            f"Execution not permitted: disposition is {auth.disposition!r}, "
            "expected 'permitted'."
        )


# ---------------------------------------------------------------------------
# Methodology-attestation decorator
# ---------------------------------------------------------------------------


def methodology_attested(fn: typing.Callable) -> typing.Callable:
    """Mark a function as methodology-attested (documentation decorator).

    In screening-2.0.0 authorization is enforced at the engine interface
    (:meth:`~core.physics_registry.AbstractPhysicsEngine.run`) rather than
    on individual implementation functions.  This decorator is retained for
    documentation and static analysis purposes; it adds no runtime checks.

    The attribute ``__methodology_attested__ = True`` is set on the wrapper
    so callers can introspect attestation status if needed.

    Note
    ----
    Applying this decorator to ``_evaluate_impl`` overrides is **not
    required** — :meth:`AbstractPhysicsEngine.run` unconditionally calls
    :func:`ensure_execution_permitted` before dispatching to
    ``_evaluate_impl``.  See ADR-0005 § Decision for the rationale.
    """

    @functools.wraps(fn)
    def wrapper(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        return fn(*args, **kwargs)

    wrapper.__methodology_attested__ = True  # type: ignore[attr-defined]
    return wrapper
