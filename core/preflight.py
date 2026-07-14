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
``physics_registry.run_authorized_engine``) has nothing to accept.

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
# Individual rules
# ---------------------------------------------------------------------------

def rule_earz(site_cfg: dict, soils: dict) -> RuleFinding:
    """Edwards Aquifer Recharge Zone: requires WPAP and specialized analysis."""
    zone_flags = site_cfg.get("regulatory_zones", {})
    in_earz = zone_flags.get("edwards_aquifer_recharge_zone", False)
    if in_earz:
        return RuleFinding(
            rule_id="SAD-001",
            disposition="refuse",
            message=(
                "Site is within the Edwards Aquifer Recharge Zone. "
                "30 TAC Ch. 285 Subchapter E requires Water Pollution "
                "Abatement Plan (WPAP) and specialized analysis. "
                "Screening model not appropriate."
            ),
            authority="30 TAC 285.40 through 285.42; TCEQ EARZ program",
        )
    return RuleFinding(
        rule_id="SAD-001", disposition="proceed",
        message="Not in EARZ.", authority="30 TAC 285.40-42",
    )


def rule_karst(site_cfg: dict, soils: dict) -> RuleFinding:
    """Karst terrain has preferential flow that violates Darcy assumptions."""
    zone_flags = site_cfg.get("regulatory_zones", {})
    karst = zone_flags.get("karst_terrain", False)
    if karst:
        return RuleFinding(
            rule_id="SAD-002",
            disposition="refuse",
            message=(
                "Site identified as karst terrain. Preferential flow "
                "invalidates continuum Darcy assumptions. Escalate to "
                "numerical model with fracture/conduit representation."
            ),
            authority="EPA SSG 1996 §2.5.4 (screening model boundary)",
        )
    return RuleFinding(
        rule_id="SAD-002", disposition="proceed",
        message="No karst indicators.", authority="EPA SSG 1996 §2.5.4",
    )


def rule_min_receptor_distance(site_cfg: dict, soils: dict) -> RuleFinding:
    """Warn when any receptor is closer than the 4.6-m regulatory minimum."""
    receptors = site_cfg.get("receptors", [])
    close = [
        r.get("name", "?")
        for r in receptors
        if float(r.get("distance_m", 999)) < 4.6
    ]
    if close:
        return RuleFinding(
            rule_id="SAD-003",
            disposition="warn",
            message=(
                f"Receptor(s) {close} are closer than the 4.6-m (15-ft) "
                "minimum setback. Results are conservative but the "
                "regulatory minimum may not be met."
            ),
            authority="30 TAC 285.30(a)(3); EPA SSG 1996 §2.3",
        )
    return RuleFinding(
        rule_id="SAD-003", disposition="proceed",
        message="All receptors meet minimum setback.",
        authority="30 TAC 285.30(a)(3)",
    )


RULES = [rule_earz, rule_karst, rule_min_receptor_distance]


def evaluate_site(
    site_cfg: dict,
    soils: dict,
) -> SiteAppropriatenessDetermination:
    """Run all SAD rules against the site config.

    Returns a ``SiteAppropriatenessDetermination`` whose disposition is the
    most restrictive finding across all rules.
    """
    findings: List[RuleFinding] = []
    for rule in RULES:
        findings.append(rule(site_cfg, soils))
    overall = _worst([f.disposition for f in findings])
    return SiteAppropriatenessDetermination(
        disposition=overall,
        findings=findings,
    )
