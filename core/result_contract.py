"""
result_contract.py
==================

Single source of truth for the screening **output artifact contract**: the
schema version, the top-level ``status`` vocabulary, and the CLI exit-code
taxonomy. The governed driver (``simulate.py``) is the sole production
entrypoint and imports from here (ADR-0004). The former flat toolkit driver
was retired during the GW-001/GW-002 reconciliation onto ``main``.

Two orthogonal facts about a run — *was it authorized to run?* and *did the
results meet the criteria?* — are collapsed into one mutually-exclusive,
non-colliding ``status`` value at the artifact level:

    ``pass``     authorized run; every screening criterion met.
    ``fail``     authorized run; one or more criteria not met (outputs written).
    ``refused``  authorization/preflight denied; physics never ran.

An errored run (bad input, validation failure, unexpected exception) writes no
artifact, so it has no ``status`` — it is represented only by the ``error``
exit code.

The word ``authorized`` is deliberately NOT a ``status`` value: it remains
decision metadata in the governed pipeline's ``authorization`` block. This is
what keeps ``refused`` (and exit code 2) meaning exactly one thing repo-wide.

Exit-code taxonomy
------------------
    0  pass     authorized; all criteria met.
    1  error    input/validation/unexpected failure; no usable artifact.
    2  refused  authorization/preflight denied; physics did not run.
    3  fail     authorized; screening ran but one or more criteria not met.

See ADR-0004 for the rationale and migration notes.
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

RESULT_SCHEMA_VERSION = "screening-result-2.0"

# ---------------------------------------------------------------------------
# Status vocabulary (artifact-level, mutually exclusive)
# ---------------------------------------------------------------------------

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_REFUSED = "refused"

STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_REFUSED)

# ---------------------------------------------------------------------------
# Exit-code taxonomy
# ---------------------------------------------------------------------------

EXIT_PASS = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2
EXIT_FAIL = 3

_EXIT_BY_STATUS = {
    STATUS_PASS: EXIT_PASS,
    STATUS_FAIL: EXIT_FAIL,
    STATUS_REFUSED: EXIT_REFUSED,
}


# ---------------------------------------------------------------------------
# Derivation helpers
# ---------------------------------------------------------------------------

def resolve_status(*, authorized: bool, all_criteria_met: Optional[bool]) -> str:
    """Resolve the canonical artifact ``status`` from the two orthogonal facts.

    Parameters
    ----------
    authorized:
        Whether the run was permitted (True for a toolkit run with no preflight;
        True for a governed ``proceed``/``warn``; False for a governed
        ``refuse``).
    all_criteria_met:
        Whether every gating constituent met its criterion. Ignored when
        ``authorized`` is False. Required (non-None) when ``authorized`` is
        True — an authorized run must have a determinate pass/fail.

    Returns
    -------
    One of ``STATUS_PASS`` / ``STATUS_FAIL`` / ``STATUS_REFUSED``.
    """
    if not authorized:
        return STATUS_REFUSED
    if all_criteria_met is None:
        raise ValueError(
            "all_criteria_met must be True or False for an authorized run; "
            "got None."
        )
    return STATUS_PASS if all_criteria_met else STATUS_FAIL


def exit_code_for(status: str) -> int:
    """Map a canonical ``status`` to its CLI exit code.

    ``error`` has no ``status`` (an errored run writes no artifact); callers
    handle that path separately and return ``EXIT_ERROR`` directly.
    """
    try:
        return _EXIT_BY_STATUS[status]
    except KeyError:
        raise ValueError(
            f"Unknown screening status {status!r}; expected one of {STATUSES}."
        ) from None


__all__ = [
    "RESULT_SCHEMA_VERSION",
    "STATUS_PASS",
    "STATUS_FAIL",
    "STATUS_REFUSED",
    "STATUSES",
    "EXIT_PASS",
    "EXIT_ERROR",
    "EXIT_REFUSED",
    "EXIT_FAIL",
    "resolve_status",
    "exit_code_for",
]
