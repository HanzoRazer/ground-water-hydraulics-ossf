"""
preflight.py — Site-appropriateness preflight evaluation.

Public surface (Tier 1 via core.__init__):
    evaluate_site, ScreeningScopeError

Public surface (Tier 2 via core.__init__):
    RuleFinding, SiteAppropriatenessDetermination

Internal (Tier 3 — import via ``core.preflight`` only):
    rule_soil_class_in_database, rule_hydraulic_gradient_positive,
    rule_at_least_one_receptor
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.governance import screening_boundary


class ScreeningScopeError(Exception):
    """Raised when a site is outside the scope of this screening methodology.

    Tier 1 — Consumer API.
    """


class FindingSeverity(str, Enum):
    """Severity level for a preflight :class:`RuleFinding`."""

    INFO = "INFO"
    WARNING = "WARNING"
    FATAL = "FATAL"


@dataclass
class RuleFinding:
    """A single finding produced by a preflight rule.

    Tier 2 — Extension API (for rule authors).

    Attributes
    ----------
    rule_id:
        Short identifier for the rule that produced this finding
        (e.g. ``"SOIL-001"``).
    severity:
        :class:`FindingSeverity` level.
    message:
        Human-readable description of the finding.
    field_path:
        Optional dot-path to the config field that triggered the finding
        (e.g. ``"soil_class"``).
    """

    rule_id: str
    severity: FindingSeverity
    message: str
    field_path: str | None = None


@dataclass
class SiteAppropriatenessDetermination:
    """The combined result of running all preflight rules against a site.

    Tier 2 — Extension API (for rule authors).

    Attributes
    ----------
    site_id:
        Identifier of the site evaluated.
    is_appropriate:
        True if no FATAL findings were produced.
    findings:
        Ordered list of all :class:`RuleFinding` objects produced.
    """

    site_id: str
    is_appropriate: bool
    findings: list[RuleFinding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Individual rule functions — Tier 3
# ---------------------------------------------------------------------------

def rule_soil_class_in_database(
    config: dict[str, Any],
    soils_db: dict[str, Any],
) -> RuleFinding | None:
    """Check that the site soil class is present in the soils database.

    Tier 3 — import via ``core.preflight`` only.
    """
    soil_class = config.get("soil_class")
    if soil_class is not None and soil_class not in soils_db:
        return RuleFinding(
            rule_id="SOIL-001",
            severity=FindingSeverity.FATAL,
            message=(
                f"Soil class {soil_class!r} is not present in the soils "
                "database.  Check the soil_class field."
            ),
            field_path="soil_class",
        )
    return None


def rule_hydraulic_gradient_positive(
    config: dict[str, Any],
    soils_db: dict[str, Any],
) -> RuleFinding | None:
    """Check that the hydraulic gradient is strictly positive.

    Tier 3 — import via ``core.preflight`` only.
    """
    gradient = config.get("hydraulic_gradient")
    if gradient is not None:
        try:
            if float(gradient) <= 0:
                return RuleFinding(
                    rule_id="HYDRO-001",
                    severity=FindingSeverity.FATAL,
                    message=(
                        f"Hydraulic gradient must be positive; got {gradient}."
                    ),
                    field_path="hydraulic_gradient",
                )
        except (TypeError, ValueError):
            return RuleFinding(
                rule_id="HYDRO-002",
                severity=FindingSeverity.FATAL,
                message=(
                    f"Hydraulic gradient must be a number; got {gradient!r}."
                ),
                field_path="hydraulic_gradient",
            )
    return None


def rule_at_least_one_receptor(
    config: dict[str, Any],
    soils_db: dict[str, Any],
) -> RuleFinding | None:
    """Check that at least one receptor is configured.

    Tier 3 — import via ``core.preflight`` only.
    """
    receptors = config.get("receptors", [])
    if not receptors:
        return RuleFinding(
            rule_id="SITE-001",
            severity=FindingSeverity.FATAL,
            message="At least one receptor must be configured.",
            field_path="receptors",
        )
    return None


# ---------------------------------------------------------------------------
# Ordered rule pipeline — internal
# ---------------------------------------------------------------------------

_PREFLIGHT_RULES = [
    rule_soil_class_in_database,
    rule_hydraulic_gradient_positive,
    rule_at_least_one_receptor,
]


# ---------------------------------------------------------------------------
# Public entry point — Tier 1
# ---------------------------------------------------------------------------

@screening_boundary
def evaluate_site(
    config: dict[str, Any],
    soils_db: dict[str, Any],
    *,
    raise_on_fatal: bool = True,
) -> SiteAppropriatenessDetermination:
    """Run all preflight rules against a site configuration.

    Tier 1 — Consumer API.

    Parameters
    ----------
    config:
        Parsed site configuration dictionary.
    soils_db:
        Soils database mapping class name to soil properties.
    raise_on_fatal:
        If ``True`` (default), raises :exc:`ScreeningScopeError` when any
        FATAL finding is produced.

    Returns
    -------
    SiteAppropriatenessDetermination

    Raises
    ------
    ScreeningScopeError
        If *raise_on_fatal* is ``True`` and any FATAL finding is present.
    """
    site_id = config.get("site_id", "unknown")
    findings: list[RuleFinding] = []

    for rule_fn in _PREFLIGHT_RULES:
        finding = rule_fn(config, soils_db)
        if finding is not None:
            findings.append(finding)

    fatal = [f for f in findings if f.severity == FindingSeverity.FATAL]
    is_appropriate = len(fatal) == 0

    determination = SiteAppropriatenessDetermination(
        site_id=site_id,
        is_appropriate=is_appropriate,
        findings=findings,
    )

    if not is_appropriate and raise_on_fatal:
        messages = "; ".join(f.message for f in fatal)
        raise ScreeningScopeError(
            f"Site {site_id!r} is outside the scope of this screening "
            f"methodology: {messages}"
        )

    return determination
