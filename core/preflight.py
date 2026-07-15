"""
preflight.py
============

Site Appropriateness Determination (SAD).

Runs BEFORE any physics. Evaluates the site configuration against a rule set
derived from 30 TAC Ch. 285 (OSSF rules), EPA Soil Screening Guidance (1996),
and standard practice for when a 1D analytical screening model is defensible.

As of OSSF-GW-002 the rules consume a validated, immutable
:class:`~core.contracts.site_case_v1.SiteCaseV1` — never a free-form dictionary
and never a narrative treatment string. Structural, unit, enum, numeric, and
database-reference validity are guaranteed by the contract layer *before*
preflight runs, so several former "malformed input" refusal branches (missing
fields, non-finite/negative numbers, unknown soil, unknown constituent) are now
caught earlier as typed contract errors and cannot reach these rules. The SAD
thresholds, rule IDs, citations, and proceed/warn/refuse dispositions are
unchanged.

Emits one of three dispositions:

  * ``proceed``   — screening model appropriate; physics may run
  * ``warn``      — screening model applicable but marginal; physics runs
                    and the report carries a prominent caveat
  * ``refuse``    — screening model NOT appropriate for this site; physics
                    MUST NOT run; report documents refusal with citations

The refusal path is NOT a warning-with-override. It is a hard boundary.
A refused determination is not authorizable: ``authorize_screening`` in
``core/authorization.py`` raises ``AuthorizationDeniedError`` and no token
is minted, so the physics engine (reachable only via
``physics_registry.run_authorized_engine``) has nothing to accept. See
ADR-0001 (doctrine) and ADR-0003 (enforcement).

Ruleset version: sad-1.0.0 (see governance.PREFLIGHT_RULESET_VERSION).
Rule sources are cited in the ``authority`` field of each rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .contracts.enums import DisinfectionStatus, ReceptorType, TreatmentLevel
from .contracts.validation import active_receptors
from .contracts.site_case_v1 import SiteCaseV1


# ---------------------------------------------------------------------------
# Rule outcomes and disposition
# ---------------------------------------------------------------------------

DISPOSITION_ORDER = ("proceed", "warn", "refuse")


@dataclass(frozen=True)
class RuleFinding:
    """One rule's finding against the site."""
    rule_id: str
    disposition: str          # 'proceed' | 'warn' | 'refuse'
    message: str
    authority: str            # regulatory / methodological citation


@dataclass
class SiteAppropriatenessDetermination:
    """Aggregated preflight result for one site."""
    disposition: str
    findings: List[RuleFinding] = field(default_factory=list)

    @property
    def refuses(self) -> bool:
        return self.disposition == "refuse"

    @property
    def warns(self) -> bool:
        return self.disposition == "warn"

    def refusal_reasons(self) -> List[RuleFinding]:
        return [f for f in self.findings if f.disposition == "refuse"]

    def warnings(self) -> List[RuleFinding]:
        return [f for f in self.findings if f.disposition == "warn"]


def _worst(dispositions: List[str]) -> str:
    """Return the most restrictive disposition seen."""
    for d in reversed(DISPOSITION_ORDER):  # refuse > warn > proceed
        if d in dispositions:
            return d
    return "proceed"


# ---------------------------------------------------------------------------
# Individual rules. Each rule inspects the validated site case and returns a
# RuleFinding. New rules append to RULES and increment the ruleset version.
# ---------------------------------------------------------------------------

def rule_earz(case: SiteCaseV1) -> RuleFinding:
    """Edwards Aquifer Recharge Zone requires WPAP and specialized analysis;
    the 1D screening model is not defensible in karst / recharge terrain."""
    if case.regulatory_location.edwards_aquifer_recharge_zone:
        return RuleFinding(
            rule_id="SAD-001",
            disposition="refuse",
            message="Site is within the Edwards Aquifer Recharge Zone. "
                    "30 TAC Ch. 285 Subchapter E requires Water Pollution "
                    "Abatement Plan (WPAP) and specialized analysis. "
                    "Screening model not appropriate.",
            authority="30 TAC 285.40 through 285.42; TCEQ EARZ program",
        )
    return RuleFinding(
        rule_id="SAD-001", disposition="proceed",
        message="Not in EARZ.", authority="30 TAC 285.40-42",
    )


def rule_karst(case: SiteCaseV1) -> RuleFinding:
    """Karst terrain has preferential flow that violates continuum
    Darcy assumptions."""
    if case.regulatory_location.karst_terrain:
        return RuleFinding(
            rule_id="SAD-002",
            disposition="refuse",
            message="Site identified as karst terrain. Preferential flow "
                    "invalidates continuum Darcy assumptions. Escalate to "
                    "numerical model with fracture/conduit representation.",
            authority="EPA SSG 1996 §2.5.4 (screening model boundary)",
        )
    return RuleFinding(
        rule_id="SAD-002", disposition="proceed",
        message="Not karst.", authority="EPA SSG 1996 §2.5.4",
    )


def rule_water_table_depth(case: SiteCaseV1) -> RuleFinding:
    """Ch. 285.33(b)(1)(A) requires min 2-ft separation between disposal
    and groundwater; below that, vadose attenuation is insufficient.

    Presence and positivity of ``depth_to_groundwater_m`` are guaranteed by
    the contract; the former "not provided" refusal cannot reach here."""
    depth_m = case.groundwater.depth_to_groundwater_m
    depth_ft = depth_m / 0.3048
    if depth_ft < 2.0:
        return RuleFinding(
            rule_id="SAD-003", disposition="refuse",
            message=f"Water table at {depth_ft:.1f} ft is below the 2-ft "
                    "regulatory minimum. Screening model not applicable; "
                    "site may not be suitable for surface application.",
            authority="30 TAC 285.33(b)(1)(A)",
        )
    if depth_ft < 4.0:
        return RuleFinding(
            rule_id="SAD-003", disposition="warn",
            message=f"Water table at {depth_ft:.1f} ft is shallow. "
                    "Vadose zone attenuation is limited; verify with "
                    "seasonal high-water piezometer data.",
            authority="30 TAC 285.30(b)(4); EPA SSG 1996",
        )
    return RuleFinding(
        rule_id="SAD-003", disposition="proceed",
        message=f"Water table at {depth_ft:.1f} ft below source.",
        authority="30 TAC 285.33(b)(1)(A)",
    )


def rule_soil_class(case: SiteCaseV1) -> RuleFinding:
    """Pure sand and coarser: screening model insufficiently conservative.

    Existence of the soil in the database is guaranteed by the contract
    (``UnknownSoilError`` is raised before preflight), so the former
    "unknown soil_type" refusal cannot reach here; this rule keys off the
    canonical soil class ID."""
    soil_id = case.subsurface.soil_id
    if soil_id == "sand":
        return RuleFinding(
            rule_id="SAD-004", disposition="refuse",
            message="Soil is classified as 'sand'. Advective transport "
                    "dominates and screening model does not adequately "
                    "represent preferential pathways in coarse soils. "
                    "Escalate to vadose or numerical model.",
            authority="Ch. 285.30(a)(3); EPA SSG 1996 §2.5.4",
        )
    if soil_id == "loamy_sand":
        return RuleFinding(
            rule_id="SAD-004", disposition="warn",
            message="Soil is classified as 'loamy_sand'. Rapid transport "
                    "expected; verify K_sat with site-specific percolation "
                    "test rather than relying on class-average values.",
            authority="Ch. 285.30(a)(3)",
        )
    return RuleFinding(
        rule_id="SAD-004", disposition="proceed",
        message=f"Soil class '{soil_id}' within screening scope.",
        authority="Ch. 285.30(a)(3)",
    )


def rule_receptor_distance(case: SiteCaseV1) -> RuleFinding:
    """Very short distances: screening model unreliable AND likely below
    the regulatory minimum setback anyway.

    Type-specific hard minimums (private well 50 ft, public well 150 ft) are
    checked against EVERY receptor, not just the nearest one: a nearer
    non-well receptor (e.g. a property boundary) must not mask a farther but
    still-illegal well setback. Only after no receptor violates a hard
    minimum does the nearest receptor control the generic <15 m warning.

    Positivity and finiteness of every ``distance_m`` are guaranteed by the
    contract, so the former malformed-distance refusal cannot reach here.

    Only ``active`` receptors participate; inactive entries are documentation
    only and do not affect setbacks or nearest-receptor warnings."""
    receptors = active_receptors(case)
    if not receptors:
        return RuleFinding(
            rule_id="SAD-005", disposition="refuse",
            message="No active receptors specified. At minimum, the nearest water "
                    "well and property line must be enumerated.",
            authority="30 TAC 285.91 (Table X: setbacks)",
        )

    # Hard, type-specific setback minimums apply to ALL receptors.
    for r in receptors:
        d_ft = r.distance_m / 0.3048
        if r.receptor_type == ReceptorType.PRIVATE_WELL and d_ft < 50.0:
            return RuleFinding(
                rule_id="SAD-005", disposition="refuse",
                message=f"Private well receptor '{r.display_name}' at {d_ft:.1f} ft "
                        "is below the 50-ft absolute minimum for a private water "
                        "well. This is a setback violation, not a "
                        "waiver-eligible condition.",
                authority="30 TAC 285.91(10) Table X",
            )
        if r.receptor_type == ReceptorType.PUBLIC_WELL and d_ft < 150.0:
            return RuleFinding(
                rule_id="SAD-005", disposition="refuse",
                message=f"Public water supply well '{r.display_name}' at {d_ft:.1f} ft "
                        "is below the 150-ft minimum. Regulatory issue "
                        "outside screening scope.",
                authority="30 TAC 285.91(10); 30 TAC Ch. 290",
            )

    # Generic short-distance warning is driven by the nearest receptor.
    nearest = min(receptors, key=lambda r: r.distance_m)
    d_m = nearest.distance_m
    d_ft = d_m / 0.3048
    if d_m < 15.0:
        return RuleFinding(
            rule_id="SAD-005", disposition="warn",
            message=f"Nearest receptor at {d_m:.1f} m; screening "
                    "model has limited resolution below 15 m.",
            authority="EPA SSG 1996 §2.5.4",
        )
    return RuleFinding(
        rule_id="SAD-005", disposition="proceed",
        message=f"Nearest receptor at {d_m:.1f} m ({d_ft:.1f} ft).",
        authority="30 TAC 285.91",
    )


def rule_gradient(case: SiteCaseV1) -> RuleFinding:
    """Very steep gradients are outside the screening envelope and usually
    indicate the flow-direction assumption should be re-verified.

    Finiteness and non-negativity of the gradient are guaranteed by the
    contract (a negative gradient is rejected as a sign-convention error
    before preflight)."""
    grad = case.groundwater.hydraulic_gradient
    if grad < 0.001:
        return RuleFinding(
            rule_id="SAD-006", disposition="warn",
            message=f"Hydraulic gradient of {grad:.4f} is very low; "
                    "verify flow direction (seasonal reversals possible).",
            authority="EPA SSG 1996",
        )
    if grad > 0.1:
        return RuleFinding(
            rule_id="SAD-006", disposition="refuse",
            message=f"Hydraulic gradient of {grad:.4f} exceeds screening "
                    "envelope; verify with piezometer data and escalate.",
            authority="EPA SSG 1996",
        )
    if grad > 0.05:
        return RuleFinding(
            rule_id="SAD-006", disposition="warn",
            message=f"Hydraulic gradient of {grad:.4f} is high; verify "
                    "with site-specific measurements.",
            authority="EPA SSG 1996",
        )
    return RuleFinding(
        rule_id="SAD-006", disposition="proceed",
        message=f"Hydraulic gradient {grad:.4f} within normal range.",
        authority="EPA SSG 1996",
    )


def rule_treatment_class(case: SiteCaseV1) -> RuleFinding:
    """Screening assumes secondary treatment with disinfection (Class I ATU).
    Primary-only effluent has an order-of-magnitude higher pathogen load
    and is outside the assumed source term.

    Keys off the structured ``treatment_level`` and ``disinfection_status``
    enums (OSSF-GW-002) — never a substring search of a narrative string."""
    treatment = case.treatment
    if treatment.treatment_level == TreatmentLevel.PRIMARY:
        return RuleFinding(
            rule_id="SAD-007", disposition="refuse",
            message="Source is primary-only treatment. Screening assumes "
                    "Class I aerobic + disinfection source terms; refuse.",
            authority="30 TAC 285.32(b)(1); tool source-term assumption",
        )
    if treatment.disinfection_status == DisinfectionStatus.NONE:
        return RuleFinding(
            rule_id="SAD-007", disposition="warn",
            message=f"Treatment level '{treatment.treatment_level.value}' has "
                    "no disinfection; verify source concentrations.",
            authority="30 TAC 285.32",
        )
    return RuleFinding(
        rule_id="SAD-007", disposition="proceed",
        message=f"Treatment level '{treatment.treatment_level.value}' with "
                f"'{treatment.disinfection_status.value}' within screening scope.",
        authority="30 TAC 285.32",
    )


# ---------------------------------------------------------------------------
# Ruleset registry (ADR-0001 canonical authority)
# ---------------------------------------------------------------------------

RULES = [
    rule_earz,
    rule_karst,
    rule_water_table_depth,
    rule_soil_class,
    rule_receptor_distance,
    rule_gradient,
    rule_treatment_class,
]


def evaluate_site(case: SiteCaseV1) -> SiteAppropriatenessDetermination:
    """Run every rule against a validated ``SiteCaseV1`` and aggregate to a
    single disposition."""
    findings = [rule(case) for rule in RULES]
    overall = _worst([f.disposition for f in findings])
    return SiteAppropriatenessDetermination(
        disposition=overall,
        findings=findings,
    )
