"""
preflight.py
============

Site Appropriateness Determination (SAD).

Runs BEFORE any physics. Evaluates the site configuration against a rule set
derived from 30 TAC Ch. 285 (OSSF rules), EPA Soil Screening Guidance (1996),
and standard practice for when a 1D analytical screening model is defensible.

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
ADR-0001 (doctrine) and ADR-0003 (enforcement). This mirrors the C2
process-exclusive canonical authority pattern: the preflight has exclusive
authority over scope, and the authorization contract is the single
enforcement point.

Ruleset version: sad-1.0.0 (see governance.PREFLIGHT_RULESET_VERSION).
Rule sources are cited in the ``authority`` field of each rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


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
# Individual rules. Each rule inspects the site config and returns a
# RuleFinding. New rules append to RULES and increment the ruleset version.
# ---------------------------------------------------------------------------

def rule_earz(site_cfg: dict, soils: dict) -> RuleFinding:
    """Edwards Aquifer Recharge Zone requires WPAP and specialized analysis;
    the 1D screening model is not defensible in karst / recharge terrain."""
    zone_flags = site_cfg.get("regulatory_zones", {})
    in_earz = zone_flags.get("edwards_aquifer_recharge_zone", False)
    if in_earz:
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


def rule_karst(site_cfg: dict, soils: dict) -> RuleFinding:
    """Karst terrain has preferential flow that violates continuum
    Darcy assumptions."""
    zone_flags = site_cfg.get("regulatory_zones", {})
    karst = zone_flags.get("karst_terrain", False)
    if karst:
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


def rule_water_table_depth(site_cfg: dict, soils: dict) -> RuleFinding:
    """Ch. 285.33(b)(1)(A) requires min 2-ft separation between disposal
    and groundwater; below that, vadose attenuation is insufficient."""
    depth_m = site_cfg.get("subsurface", {}).get("depth_to_water_table_m")
    if depth_m is None:
        return RuleFinding(
            rule_id="SAD-003", disposition="refuse",
            message="depth_to_water_table_m not provided. Required for "
                    "screening determination per Ch. 285.30 site evaluation.",
            authority="30 TAC 285.30(b)(4)",
        )
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


def rule_soil_class(site_cfg: dict, soils: dict) -> RuleFinding:
    """Pure sand and coarser: screening model insufficiently conservative."""
    soil_type = site_cfg.get("subsurface", {}).get("soil_type")
    if soil_type is None:
        return RuleFinding(
            rule_id="SAD-004", disposition="refuse",
            message="soil_type not provided.",
            authority="30 TAC 285.30 site evaluation required",
        )
    if soil_type not in soils:
        return RuleFinding(
            rule_id="SAD-004", disposition="refuse",
            message=f"Unknown soil_type '{soil_type}'.",
            authority="internal: soil_database.json authority",
        )
    if soil_type == "sand":
        return RuleFinding(
            rule_id="SAD-004", disposition="refuse",
            message="Soil is classified as 'sand'. Advective transport "
                    "dominates and screening model does not adequately "
                    "represent preferential pathways in coarse soils. "
                    "Escalate to vadose or numerical model.",
            authority="Ch. 285.30(a)(3); EPA SSG 1996 §2.5.4",
        )
    if soil_type == "loamy_sand":
        return RuleFinding(
            rule_id="SAD-004", disposition="warn",
            message="Soil is classified as 'loamy_sand'. Rapid transport "
                    "expected; verify K_sat with site-specific percolation "
                    "test rather than relying on class-average values.",
            authority="Ch. 285.30(a)(3)",
        )
    return RuleFinding(
        rule_id="SAD-004", disposition="proceed",
        message=f"Soil class '{soil_type}' within screening scope.",
        authority="Ch. 285.30(a)(3)",
    )


def rule_receptor_distance(site_cfg: dict, soils: dict) -> RuleFinding:
    """Very short distances: screening model unreliable AND likely below
    the regulatory minimum setback anyway.

    Type-specific hard minimums (private well 50 ft, public well 150 ft) are
    checked against EVERY receptor, not just the nearest one: a nearer
    non-well receptor (e.g. a property boundary) must not mask a farther but
    still-illegal well setback. Only after no receptor violates a hard
    minimum does the nearest receptor control the generic <15 m warning.
    """
    receptors = site_cfg.get("receptors", [])
    if not receptors:
        return RuleFinding(
            rule_id="SAD-005", disposition="refuse",
            message="No receptors specified. At minimum, the nearest water "
                    "well and property line must be enumerated.",
            authority="30 TAC 285.91 (Table X: setbacks)",
        )

    # Structural guard: every receptor needs a positive, finite distance_m.
    # A malformed entry must produce a governed refusal, not a raw KeyError.
    for i, r in enumerate(receptors):
        d = r.get("distance_m") if isinstance(r, dict) else None
        if isinstance(d, bool) or not isinstance(d, (int, float)) or d != d or d <= 0:
            label = (r.get("name") if isinstance(r, dict) else None) or f"index {i}"
            return RuleFinding(
                rule_id="SAD-005", disposition="refuse",
                message=f"Receptor '{label}' has an invalid distance_m "
                        f"({d!r}); a positive numeric distance is required "
                        "for every receptor.",
                authority="30 TAC 285.30(b)(4) site evaluation",
            )

    # Hard, type-specific setback minimums apply to ALL receptors.
    for r in receptors:
        d_ft = r["distance_m"] / 0.3048
        rtype = r.get("type")
        name = r.get("name", "receptor")
        if rtype == "private_well" and d_ft < 50.0:
            return RuleFinding(
                rule_id="SAD-005", disposition="refuse",
                message=f"Private well receptor '{name}' at {d_ft:.1f} ft is "
                        "below the 50-ft absolute minimum for a private water "
                        "well. This is a setback violation, not a "
                        "waiver-eligible condition.",
                authority="30 TAC 285.91(10) Table X",
            )
        if rtype == "public_well" and d_ft < 150.0:
            return RuleFinding(
                rule_id="SAD-005", disposition="refuse",
                message=f"Public water supply well '{name}' at {d_ft:.1f} ft "
                        "is below the 150-ft minimum. Regulatory issue "
                        "outside screening scope.",
                authority="30 TAC 285.91(10); 30 TAC Ch. 290",
            )

    # Generic short-distance warning is driven by the nearest receptor.
    nearest = min(receptors, key=lambda r: r["distance_m"])
    d_m = nearest["distance_m"]
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


def rule_gradient(site_cfg: dict, soils: dict) -> RuleFinding:
    """Very steep gradients are outside the screening envelope and usually
    indicate the flow-direction assumption should be re-verified."""
    grad = site_cfg.get("subsurface", {}).get("hydraulic_gradient")
    if grad is None:
        return RuleFinding(
            rule_id="SAD-006", disposition="refuse",
            message="hydraulic_gradient not provided.",
            authority="Site evaluation per Ch. 285.30",
        )
    if isinstance(grad, bool) or not isinstance(grad, (int, float)) or grad != grad:
        return RuleFinding(
            rule_id="SAD-006", disposition="refuse",
            message=f"hydraulic_gradient {grad!r} is not a finite number.",
            authority="Site evaluation per Ch. 285.30",
        )
    if grad < 0.0:
        return RuleFinding(
            rule_id="SAD-006", disposition="refuse",
            message=f"Hydraulic gradient of {grad:.4f} is negative. For a "
                    "source-to-receptor screening model a negative gradient "
                    "indicates a sign-convention or input error (flow away "
                    "from the receptor), not a low-magnitude condition. "
                    "Re-verify flow direction before screening.",
            authority="EPA SSG 1996; Ch. 285.30 site evaluation",
        )
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


def rule_treatment_class(site_cfg: dict, soils: dict) -> RuleFinding:
    """Screening assumes secondary treatment with disinfection (Class I ATU).
    Primary-only effluent has an order-of-magnitude higher pathogen load
    and is outside the assumed source term."""
    tclass = site_cfg.get("source", {}).get("treatment_class", "")
    tclass_low = tclass.lower()
    if "primary" in tclass_low and "secondary" not in tclass_low:
        return RuleFinding(
            rule_id="SAD-007", disposition="refuse",
            message="Source is primary-only treatment. Screening assumes "
                    "Class I aerobic + disinfection source terms; refuse.",
            authority="30 TAC 285.32(b)(1); tool source-term assumption",
        )
    if "disinfection" not in tclass_low and "class i" not in tclass_low:
        return RuleFinding(
            rule_id="SAD-007", disposition="warn",
            message=f"Treatment class '{tclass}' does not explicitly "
                    "reference disinfection; verify source concentrations.",
            authority="30 TAC 285.32",
        )
    return RuleFinding(
        rule_id="SAD-007", disposition="proceed",
        message=f"Treatment class '{tclass}' within screening scope.",
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


def evaluate_site(site_cfg: dict, soils: dict) -> SiteAppropriatenessDetermination:
    """Run every rule and aggregate to a single disposition."""
    findings = [rule(site_cfg, soils) for rule in RULES]
    overall = _worst([f.disposition for f in findings])
    return SiteAppropriatenessDetermination(
        disposition=overall,
        findings=findings,
    )
