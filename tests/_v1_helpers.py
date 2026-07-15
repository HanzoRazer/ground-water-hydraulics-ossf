"""
tests/_v1_helpers.py
====================

Shared builders for SiteCaseV1-based tests (OSSF-GW-002). Not a test module
(no ``test_`` prefix), so pytest does not collect it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.contracts import (
    SCHEMA_VERSION,
    ConstituentRole,
    ConstituentSelection,
    DisinfectionMethod,
    DisinfectionStatus,
    DispersivityMethod,
    GroundwaterConfiguration,
    PhysicsSelection,
    ProjectMetadata,
    ReceptorDefinition,
    RegulatoryLocation,
    ReportingMetadata,
    SiteCaseV1,
    SourceConfiguration,
    SubsurfaceConfiguration,
    TreatmentConfiguration,
    TreatmentLevel,
    load_site_case_json,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures"
DATA = REPO_ROOT / "data"


def load_dbs():
    soils = json.loads((DATA / "soil_database.json").read_text(encoding="utf-8"))["soils"]
    cons = json.loads((DATA / "pathogens.json").read_text(encoding="utf-8"))["constituents"]
    return soils, cons


def load_fixture_case(name: str) -> SiteCaseV1:
    soils, cons = load_dbs()
    return load_site_case_json(
        FIXTURES / f"site_case_v1_{name}.json",
        soil_database=soils, constituent_database=cons,
    )


def receptor(rid, rtype="private_well", dist=30.5, name=None, active=True):
    return ReceptorDefinition(
        receptor_id=rid, receptor_type=rtype, distance_m=dist,
        display_name=name or rid, active=active,
    )


def constituent(cid, role="gating", conc=None, use_default=None):
    if conc is None and use_default is None:
        use_default = True
    return ConstituentSelection(
        constituent_id=cid, role=role,
        source_concentration=conc,
        use_governed_default=bool(use_default) if conc is None else False,
    )


def make_case(
    *,
    site_id="TEST-1",
    soil_id="clay_loam",
    soil_thickness_m=3.0,
    depth=4.5,
    gradient=0.01,
    treatment_level=TreatmentLevel.SECONDARY,
    disinfection_status=DisinfectionStatus.DISINFECTED,
    disinfection_method=DisinfectionMethod.CHLORINE,
    receptors=None,
    constituents=None,
    comparison_soil_ids=(),
    dispersivity_method=DispersivityMethod.EPA_SSG,
    engine="ogata_banks_1d",
    regulatory_location=None,
) -> SiteCaseV1:
    """Build a locally-valid SiteCaseV1 from records (no DB/cross-field
    validation — use ``load_fixture_case`` for a fully validated case)."""
    if receptors is None:
        receptors = (receptor("well", "private_well", 30.5, "Private well"),)
    if constituents is None:
        constituents = (constituent("e_coli", "gating"),)
    return SiteCaseV1(
        schema_version=SCHEMA_VERSION,
        site_id=site_id,
        project=ProjectMetadata(
            name="Test Site", engineer="EOR, P.E.", county="County, State",
            regulatory_authority="30 TAC Ch. 285",
        ),
        regulatory_location=RegulatoryLocation(**(regulatory_location or {})),
        treatment=TreatmentConfiguration(
            treatment_level=treatment_level,
            disinfection_status=disinfection_status,
            disinfection_method=disinfection_method,
        ),
        source=SourceConfiguration(design_flow_gpd=360.0),
        subsurface=SubsurfaceConfiguration(soil_id=soil_id, soil_thickness_m=soil_thickness_m),
        groundwater=GroundwaterConfiguration(depth_to_groundwater_m=depth, hydraulic_gradient=gradient),
        receptors=tuple(receptors),
        constituents=tuple(constituents),
        physics=PhysicsSelection(engine=engine, dispersivity_method=dispersivity_method),
        reporting=ReportingMetadata(comparison_soil_ids=tuple(comparison_soil_ids)),
    )


def v1_dict(**overrides) -> dict:
    """A raw V1 config dict (schema_version present) for driver tests."""
    base = {
        "schema_version": SCHEMA_VERSION,
        "site_id": "T-1",
        "project": {
            "name": "Test Site", "engineer": "EOR, P.E.",
            "county": "County, State", "regulatory_authority": "30 TAC Ch. 285",
        },
        "regulatory_location": {},
        "treatment": {
            "treatment_level": "secondary", "disinfection_status": "disinfected",
            "disinfection_method": "chlorine",
        },
        "source": {"design_flow_gpd": 360},
        "subsurface": {"soil_id": "clay_loam", "soil_thickness_m": 3.0},
        "groundwater": {"depth_to_groundwater_m": 4.5, "hydraulic_gradient": 0.01},
        "receptors": [
            {"receptor_id": "well", "receptor_type": "private_well",
             "distance_m": 30.5, "display_name": "Private well"},
            {"receptor_id": "prop", "receptor_type": "property_boundary",
             "distance_m": 20.0, "display_name": "Property line"},
        ],
        "constituents": [
            {"constituent_id": "e_coli", "role": "gating", "use_governed_default": True},
            {"constituent_id": "nitrate_as_N", "role": "reference_only", "use_governed_default": True},
        ],
        "physics": {"engine": "ogata_banks_1d", "dispersivity_method": "epa_ssg"},
        "reporting": {"comparison_soil_ids": ["sandy_loam"]},
    }
    base.update(overrides)
    return base
