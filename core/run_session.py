"""
run_session.py — Session lifecycle management for screening runs.

Public surface (Tier 1 via core.__init__):
    RunSession, SessionScopedExecutor, SessionExpiredError

Internal (Tier 3 — import via ``core.run_session`` only):
    _LIVE_SESSIONS
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable


class SessionExpiredError(Exception):
    """Raised when an operation is attempted on an expired :class:`RunSession`.

    Tier 1 — Consumer API.
    """


# ---------------------------------------------------------------------------
# Session registry — Tier 3
# ---------------------------------------------------------------------------

_LIVE_SESSIONS: dict[str, RunSession] = {}
"""Module-level registry of active (non-expired) sessions.

Tier 3 — internal.  Import via ``core.run_session`` only.
"""

_SESSIONS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# RunSession
# ---------------------------------------------------------------------------

class RunSession:
    """Tracks the lifecycle of a single screening run.

    Tier 1 — Consumer API.

    Usage as a context manager is recommended; the session is automatically
    expired on ``__exit__``::

        with RunSession(site_id="SITE-001", methodology_version="screening-3.1.0") as session:
            results = run_authorized_engine(auth, "darcy-1d", config, session=session)

    Attributes
    ----------
    session_id:
        A UUID-4 string uniquely identifying this run.
    site_id:
        The site identifier this session is scoped to.
    methodology_version:
        The methodology version string in force for this session.
    created_utc:
        ISO-8601 UTC timestamp of session creation.
    """

    def __init__(self, site_id: str, methodology_version: str) -> None:
        self.session_id: str = str(uuid.uuid4())
        self.site_id: str = site_id
        self.methodology_version: str = methodology_version
        self.created_utc: str = datetime.now(timezone.utc).isoformat()
        self._expired: bool = False
        with _SESSIONS_LOCK:
            _LIVE_SESSIONS[self.session_id] = self

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def expire(self) -> None:
        """Mark the session as expired and remove it from the live registry.

        Idempotent — calling on an already-expired session is safe.
        """
        self._expired = True
        with _SESSIONS_LOCK:
            _LIVE_SESSIONS.pop(self.session_id, None)

    @property
    def is_expired(self) -> bool:
        """True if this session has been expired."""
        return self._expired

    def _require_active(self) -> None:
        """Raise :exc:`SessionExpiredError` if this session has expired."""
        if self._expired:
            raise SessionExpiredError(
                f"Session {self.session_id!r} for site {self.site_id!r} has expired."
            )

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> RunSession:
        self._require_active()
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        self.expire()
        return False


# ---------------------------------------------------------------------------
# SessionScopedExecutor
# ---------------------------------------------------------------------------

class SessionScopedExecutor:
    """Binds a callable to a :class:`RunSession`; prevents calls after expiry.

    Tier 1 — Consumer API.

    Any call to this executor after the bound session has expired raises
    :exc:`SessionExpiredError`, providing a hard barrier against using
    stale results from a closed session.

    Usage
    -----
    ::

        executor = SessionScopedExecutor(session, my_function)
        result = executor(arg1, arg2)
    """

    def __init__(self, session: RunSession, fn: Callable[..., Any]) -> None:
        self._session = session
        self._fn = fn

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._session._require_active()
        return self._fn(*args, **kwargs)
