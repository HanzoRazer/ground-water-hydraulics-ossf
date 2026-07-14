"""
bench_authorization.py
======================

Micro-benchmark for authorization validation overhead.

The mandatory assertion — validate_authorization called exactly once per
run — is included as a pytest-compatible test. The wall-time numbers are
documentation-only (not asserted).

Run:
    python -m pytest tests/bench_authorization.py -v
    python tests/bench_authorization.py  # for wall-time output
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.preflight import RuleFinding, SiteAppropriatenessDetermination
from core.authorization import authorize_screening
from core.run_session import RunSession
import core.run_session as rs_mod
from core.physics_registry import run_authorized_engine


def _cfg() -> dict:
    return {"project": {"site_id": "BENCH-001"}, "soil_class": "Sand"}


def _proceed_sad() -> SiteAppropriatenessDetermination:
    return SiteAppropriatenessDetermination(
        disposition="proceed",
        findings=[
            RuleFinding("SAD-001", "proceed", "Not in EARZ.", "30 TAC 285.40-42"),
        ],
    )


def _engine_inputs() -> dict:
    return dict(
        C0=100.0,
        lam_per_day=0.5,
        Kd_L_per_kg=1.5,
        bulk_density_kg_m3=1390.0,
        effective_porosity=0.08,
        K_sat_m_per_s=7.22e-7,
        hydraulic_gradient=0.01,
        distance_m=30.5,
    )


N_RECEPTORS = 4
N_CONSTITUENTS = 5


def _run_with_session(auth, cfg, n_receptors, n_constituents):
    """RunSession wrapper: validation called exactly once."""
    with RunSession(auth, cfg, {}, {}) as executor:
        for _ in range(n_receptors * n_constituents):
            run_authorized_engine("ogata_banks_1d", executor, **_engine_inputs())


# ---------------------------------------------------------------------------
# Mandatory assertion: validate_authorization called exactly once
# ---------------------------------------------------------------------------

def test_validate_authorization_called_exactly_once_per_run():
    """validate_authorization must be called exactly once for a full
    N_RECEPTORS x N_CONSTITUENTS run inside a RunSession.

    This is the falsification test for the RunSession performance fix:
    without RunSession, validation would be called N_RECEPTORS x N_CONSTITUENTS
    (= 20 for the default 4x5 configuration) times per run instead of 1.
    """

    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())

    call_count = 0
    original_validate = rs_mod.validate_authorization

    def counting_validate(authorization, site_config):
        nonlocal call_count
        call_count += 1
        return original_validate(authorization, site_config)

    with patch.object(rs_mod, "validate_authorization", side_effect=counting_validate):
        _run_with_session(auth, cfg, N_RECEPTORS, N_CONSTITUENTS)

    total_engine_calls = N_RECEPTORS * N_CONSTITUENTS
    assert call_count == 1, (
        f"validate_authorization was called {call_count} time(s) for "
        f"{total_engine_calls} engine calls ({N_RECEPTORS} receptors × "
        f"{N_CONSTITUENTS} constituents). Expected exactly 1 call per run."
    )


# ---------------------------------------------------------------------------
# Wall-time measurement (documentation only, not asserted in CI)
# ---------------------------------------------------------------------------

def _measure_wall_time(auth, cfg, n_receptors, n_constituents, runs=10):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        _run_with_session(auth, cfg, n_receptors, n_constituents)
        times.append(time.perf_counter() - t0)
    return min(times), sum(times) / len(times)


if __name__ == "__main__":
    cfg = _cfg()
    auth = authorize_screening(cfg, _proceed_sad())

    n_r, n_c = N_RECEPTORS, N_CONSTITUENTS
    total_calls = n_r * n_c

    best, avg = _measure_wall_time(auth, cfg, n_r, n_c)
    print(f"\nRunSession ({n_r} receptors × {n_c} constituents = {total_calls} engine calls)")
    print(f"  Validations per run : 1 (not {total_calls})")
    print(f"  Best wall time      : {best * 1000:.3f} ms")
    print(f"  Avg wall time       : {avg * 1000:.3f} ms")
    print()
    print(
        f"Pre-fix reference (validation on every call would add "
        f"~{total_calls - 1} extra hash computations per run)."
    )
