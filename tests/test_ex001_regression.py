"""
test_ex001_regression.py
========================

Pinned numerical and disposition regression for the canonical EX-001 case
(``config/site_example.json`` migrated to SiteCaseV1).

Guards against silent scientific drift from input remodeling: the handoff
requires EX-001 outputs remain within established tolerances after V1
normalization. These values were characterized from the clay-loam / 30.5 m
private-well / e_coli path through the governed engine.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _v1_helpers import evidence_result_for, load_dbs
from core.authorization import authorize_screening
from core.contracts import load_site_case_json
from core.physics_registry import run_authorized_engine
from core.preflight import evaluate_site


def _close(a: float, b: float, rel: float = 1e-3) -> bool:
    return math.isclose(a, b, rel_tol=rel)


@pytest.fixture(scope="module")
def ex001_case():
    soils, cons = load_dbs()
    return load_site_case_json(
        REPO_ROOT / "config" / "site_example.json",
        soil_database=soils, constituent_database=cons,
    )


def test_ex001_preflight_disposition_is_warn(ex001_case):
    sad = evaluate_site(ex001_case)
    assert sad.disposition == "warn"
    assert any(f.rule_id == "SAD-005" and f.disposition == "warn" for f in sad.findings)


def test_ex001_e_coli_at_primary_well_matches_hand_calc(ex001_case):
    """Clay loam, 30.5 m, e_coli — same characterization as test_physics_ogata_banks."""
    sad = evaluate_site(ex001_case)
    auth = authorize_screening(ex001_case, sad, evidence_result_for(ex001_case))
    well = next(r for r in ex001_case.receptors if r.receptor_id == "receptor_1")
    cprops = json.loads((REPO_ROOT / "data" / "pathogens.json").read_text())["constituents"]["e_coli"]
    soil = json.loads((REPO_ROOT / "data" / "soil_database.json").read_text())["soils"]["clay_loam"]

    run = run_authorized_engine(
        "ogata_banks_1d",
        ex001_case,
        auth,
        dict(
            C0=cprops["typical_C0_post_disinfection"],
            lam_per_day=cprops["lambda_per_day"],
            Kd_L_per_kg=cprops["Kd_L_per_kg"],
            bulk_density_kg_m3=soil["bulk_density_kg_per_m3"],
            effective_porosity=soil["effective_porosity"],
            K_sat_m_per_s=soil["K_sat_m_per_s"],
            hydraulic_gradient=ex001_case.groundwater.hydraulic_gradient,
            distance_m=well.distance_m,
            dispersivity_method=ex001_case.physics.dispersivity_method.value,
        ),
    )
    r = run.result
    assert _close(r.seepage_velocity_m_per_day, 0.007798, rel=1e-3)
    assert _close(r.retardation_factor, 27.0625, rel=1e-4)
    assert _close(r.dispersivity_m, 3.05, rel=1e-6)
    assert r.C_receptor_steady_state < 1e-10


def test_ex001_nitrate_is_reference_only_at_receptor(ex001_case):
    sad = evaluate_site(ex001_case)
    auth = authorize_screening(ex001_case, sad, evidence_result_for(ex001_case))
    nitrate = next(c for c in ex001_case.constituents if c.constituent_id == "nitrate_as_N")
    assert nitrate.role.value == "reference_only"
