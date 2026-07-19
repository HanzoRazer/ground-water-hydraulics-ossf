"""
core/contracts/evidence_registry.py
===================================

Load-bearing field registry for the OSSF evidence layer (OSSF-GW-003).

Defined in code (not config) so the completeness gate is versioned with the
contract. Critical missing/rejected evidence refuses before preflight;
Important pending/rejected evidence warns but may proceed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, TYPE_CHECKING

from .enums import ConstituentRole, FieldTier

if TYPE_CHECKING:
    from .site_case_v1 import SiteCaseV1


@dataclass(frozen=True)
class RequiredBinding:
    """One required evidence binding for a concrete field path on a case."""

    field_path: str
    tier: FieldTier
    rationale: str


# Static scalar / section paths (expanded further per case below).
_STATIC_CRITICAL = (
    ("groundwater.hydraulic_gradient",
     "Drives seepage velocity; SAD-006 envelope"),
    ("groundwater.depth_to_groundwater_m",
     "SAD-003 shallow water table"),
    ("subsurface.soil_id",
     "K_sat / retardation path"),
)

_STATIC_IMPORTANT = (
    ("treatment.treatment_level", "SAD-007 treatment classification"),
    ("treatment.disinfection_status", "SAD-007 disinfection"),
    ("physics.dispersivity_method", "Engine compatibility"),
)


def required_bindings_for_case(case: "SiteCaseV1") -> List[RequiredBinding]:
    """Expand the load-bearing registry against a concrete validated case.

    * Active receptors only require ``receptors[{id}].distance_m``.
    * ``reference_only`` constituents skip source-concentration requirements
      but still require ``source_basis`` when present as load-bearing for
      gating constituents; reference_only skips both source_term and basis.
    * Gating constituents require a source-term binding
      (``source_concentration`` or ``use_governed_default``) plus
      ``source_basis``.
    """
    out: List[RequiredBinding] = []

    for path, rationale in _STATIC_CRITICAL:
        out.append(RequiredBinding(field_path=path, tier=FieldTier.CRITICAL,
                                   rationale=rationale))
    for path, rationale in _STATIC_IMPORTANT:
        out.append(RequiredBinding(field_path=path, tier=FieldTier.IMPORTANT,
                                   rationale=rationale))

    for r in case.receptors:
        if not r.active:
            continue
        out.append(RequiredBinding(
            field_path=f"receptors[{r.receptor_id}].distance_m",
            tier=FieldTier.CRITICAL,
            rationale="SAD-005 setbacks (active receptors only)",
        ))

    for c in case.constituents:
        if c.role == ConstituentRole.REFERENCE_ONLY:
            continue
        if c.use_governed_default:
            term_path = f"constituents[{c.constituent_id}].use_governed_default"
        else:
            term_path = f"constituents[{c.constituent_id}].source_concentration"
        out.append(RequiredBinding(
            field_path=term_path,
            tier=FieldTier.CRITICAL,
            rationale="Source term (explicit or governed default)",
        ))
        out.append(RequiredBinding(
            field_path=f"constituents[{c.constituent_id}].source_basis",
            tier=FieldTier.CRITICAL,
            rationale="Must match binding provenance class",
        ))

    return out


__all__ = [
    "RequiredBinding",
    "required_bindings_for_case",
]
