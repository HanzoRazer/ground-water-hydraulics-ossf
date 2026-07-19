"""
tests/_v1_helpers.py
====================

Shared builders for SiteCaseV1-based tests (OSSF-GW-002 / OSSF-GW-003). Not a
test module (no ``test_`` prefix), so pytest does not collect it.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
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
    EvidenceValidationResult,
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
    compute_evidence_digest,
    load_site_case_json,
    validate_evidence_layer,
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
    validation — use ``load_fixture_case`` for a fully validated case).

    Evidence arrays default to empty; authorization unit tests use
    :func:`evidence_result_for` which digests whatever is present.
    """
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


def evidence_result_for(case: SiteCaseV1) -> EvidenceValidationResult:
    """Minimal proceed evidence result bound to ``case``'s digest.

    Used by narrow authorization/physics unit tests that construct bare
    ``make_case`` instances without full load-bearing bindings. Does **not**
    run the completeness/review gate — only supplies a digest for auth
    binding. Prefer :func:`validated_evidence_result_for` (or calling
    :func:`validate_evidence_layer` directly) whenever the case is fully
    bound and the test asserts governed pipeline realism.
    """
    return EvidenceValidationResult(
        disposition="proceed",
        evidence_digest=compute_evidence_digest(case),
        warnings=(),
        review_summary={
            "accepted": 0,
            "pending_review": 0,
            "rejected": 0,
            "superseded": 0,
            "evidence_records": len(case.evidence),
            "field_bindings": len(case.field_bindings),
        },
        bound_fields=tuple(sorted({b.field_path for b in case.field_bindings})),
    )


def validated_evidence_result_for(case: SiteCaseV1) -> EvidenceValidationResult:
    """Run the real evidence gate; for fully bound cases only."""
    return validate_evidence_layer(case)


def attach_complete_evidence(cfg: dict) -> dict:
    """Return a deep copy of ``cfg`` with complete accepted evidence bindings.

    Suitable for driver / parse fixtures that must pass
    :func:`validate_evidence_layer`. Does not alter ``schema_version``.
    """
    cfg = deepcopy(cfg)
    auth = cfg["project"]["regulatory_authority"]
    soil_id = cfg["subsurface"]["soil_id"]
    evidence = [
        {
            "evidence_id": "ev_site_assumed",
            "provenance_class": "assumed",
            "confidence": "medium",
            "review_status": "accepted",
            "source_description": "Site hydraulics and geometry (engineering assumption)",
            "captured_date": None,
            "notes": None,
            "database_id": None,
            "regulatory_authority": None,
        },
        {
            "evidence_id": "ev_soil_db",
            "provenance_class": "database_derived",
            "confidence": "high",
            "review_status": "accepted",
            "source_description": f"Soil database entry {soil_id}",
            "captured_date": None,
            "notes": None,
            "database_id": soil_id,
            "regulatory_authority": None,
        },
        {
            "evidence_id": "ev_regulatory",
            "provenance_class": "regulatory_default",
            "confidence": "medium",
            "review_status": "accepted",
            "source_description": f"Governed defaults / {auth}",
            "captured_date": None,
            "notes": None,
            "database_id": None,
            "regulatory_authority": auth,
        },
        {
            "evidence_id": "ev_treatment_docs",
            "provenance_class": "documented",
            "confidence": "high",
            "review_status": "accepted",
            "source_description": "Treatment and disinfection from design documents",
            "captured_date": None,
            "notes": None,
            "database_id": None,
            "regulatory_authority": None,
        },
    ]
    # Exactly one resolution route per binding: when evidence_id is set,
    # citation fields (database_id / regulatory_authority) live only on the
    # evidence record — not on the binding.
    bindings = [
        _b("groundwater.hydraulic_gradient", "assumed", "ev_site_assumed"),
        _b("groundwater.depth_to_groundwater_m", "assumed", "ev_site_assumed"),
        _b("subsurface.soil_id", "database_derived", "ev_soil_db"),
        _b("treatment.treatment_level", "documented", "ev_treatment_docs"),
        _b("treatment.disinfection_status", "documented", "ev_treatment_docs"),
        _b("physics.dispersivity_method", "assumed", "ev_site_assumed"),
    ]
    for r in cfg.get("receptors", []):
        if not r.get("active", True):
            continue
        bindings.append(_b(
            f"receptors[{r['receptor_id']}].distance_m", "assumed", "ev_site_assumed"
        ))
    for c in cfg.get("constituents", []):
        if c.get("role") == "reference_only":
            continue
        cid = c["constituent_id"]
        basis = c.get("source_basis", "regulatory_default")
        if basis == "estimated":
            basis = "assumed"
        elif basis == "literature":
            basis = "documented"
        c["source_basis"] = basis
        if c.get("use_governed_default"):
            term = f"constituents[{cid}].use_governed_default"
            eid, pclass = "ev_regulatory", "regulatory_default"
        else:
            term = f"constituents[{cid}].source_concentration"
            if basis == "measured":
                if not any(e["evidence_id"] == "ev_measured" for e in evidence):
                    evidence.append({
                        "evidence_id": "ev_measured",
                        "provenance_class": "measured",
                        "confidence": "high",
                        "review_status": "accepted",
                        "source_description": "Field-measured source concentration",
                        "captured_date": "2026-01-01",
                        "notes": None,
                        "database_id": None,
                        "regulatory_authority": None,
                    })
                eid, pclass = "ev_measured", "measured"
            elif basis == "regulatory_default":
                eid, pclass = "ev_regulatory", "regulatory_default"
            elif basis == "documented":
                eid, pclass = "ev_treatment_docs", "documented"
            elif basis == "database_derived":
                eid, pclass = "ev_soil_db", "database_derived"
            else:
                eid, pclass = "ev_site_assumed", "assumed"
        bindings.append(_b(term, pclass, eid))
        bindings.append(_b(f"constituents[{cid}].source_basis", pclass, eid))
    cfg["evidence"] = evidence
    cfg["field_bindings"] = bindings
    cfg.setdefault("assumptions", [])
    return cfg


def _b(field_path, provenance_class, evidence_id, *, database_id=None,
       regulatory_authority=None, assumption_id=None, notes=None):
    return {
        "field_path": field_path,
        "provenance_class": provenance_class,
        "review_status": "accepted",
        "evidence_id": evidence_id,
        "database_id": database_id,
        "regulatory_authority": regulatory_authority,
        "assumption_id": assumption_id,
        "notes": notes,
    }


def v1_dict(**overrides) -> dict:
    """A raw V1.1.0 config dict (schema_version present) for driver tests.

    Includes complete accepted evidence bindings so
    ``validate_evidence_layer`` succeeds unless the caller strips them.
    """
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
            {"constituent_id": "e_coli", "role": "gating", "use_governed_default": True,
             "source_basis": "regulatory_default"},
            {"constituent_id": "nitrate_as_N", "role": "reference_only",
             "use_governed_default": True, "source_basis": "regulatory_default"},
        ],
        "physics": {"engine": "ogata_banks_1d", "dispersivity_method": "epa_ssg"},
        "reporting": {"comparison_soil_ids": ["sandy_loam"]},
        "assumptions": [],
    }
    base.update(overrides)
    if "evidence" not in overrides and "field_bindings" not in overrides:
        base = attach_complete_evidence(base)
        # Re-apply overrides that attach_complete_evidence deep-copied away
        # only for non-evidence keys already merged above.
    return base
