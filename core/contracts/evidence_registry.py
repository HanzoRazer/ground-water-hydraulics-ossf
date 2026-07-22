"""
core/contracts/evidence_registry.py
===================================

Code-owned load-bearing field registry for OSSF-GW-003 evidence gating.

Defines which canonical ``SiteCase`` field paths require evidence bindings,
their tier, allowed provenance classes, acceptable review statuses, and
warning/refusal policy metadata. Dynamic paths expand deterministically from
active receptors and non-``reference_only`` constituents.

This module does not validate evidence records, compute digests, or invoke
downstream gates — those belong in ``evidence_validation.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Tuple

from .enums import (
    ConstituentRole,
    EvidenceReviewStatus,
    FieldTier,
    ProvenanceClass,
)
from .errors import EvidenceContractError
from .site_case_v1 import ConstituentSelection, SiteCaseV1

REGISTRY_VERSION = "evidence-registry-1.0.0"

_ALL_PROVENANCE: Tuple[ProvenanceClass, ...] = tuple(ProvenanceClass)
_ACCEPTED_ONLY: Tuple[EvidenceReviewStatus, ...] = (EvidenceReviewStatus.ACCEPTED,)


@dataclass(frozen=True)
class EvidenceGatePolicy:
    """Policy metadata for how a tier responds to evidence review states."""

    on_missing: str
    on_pending_review: str
    on_rejected: str
    on_superseded: str

    def __post_init__(self) -> None:
        for name in ("on_missing", "on_pending_review", "on_rejected", "on_superseded"):
            value = getattr(self, name)
            if value not in ("refuse", "warn"):
                raise EvidenceContractError(
                    f"EvidenceGatePolicy.{name} must be 'refuse' or 'warn'; got {value!r}."
                )


CRITICAL_GATE_POLICY = EvidenceGatePolicy(
    on_missing="refuse",
    on_pending_review="refuse",
    on_rejected="refuse",
    on_superseded="refuse",
)

IMPORTANT_GATE_POLICY = EvidenceGatePolicy(
    on_missing="refuse",
    on_pending_review="warn",
    on_rejected="warn",
    on_superseded="refuse",
)


@dataclass(frozen=True)
class FieldRequirement:
    """Immutable registry entry describing one load-bearing field path."""

    requirement_id: str
    field_path_pattern: str
    tier: FieldTier
    allowed_provenance_classes: Tuple[ProvenanceClass, ...]
    acceptable_review_statuses: Tuple[EvidenceReviewStatus, ...]
    gate_policy: EvidenceGatePolicy
    allows_multiple_bindings: bool = False

    def __post_init__(self) -> None:
        if not self.requirement_id:
            raise EvidenceContractError("FieldRequirement.requirement_id must be non-empty.")
        if not self.field_path_pattern:
            raise EvidenceContractError("FieldRequirement.field_path_pattern must be non-empty.")


@dataclass(frozen=True)
class ResolvedFieldRequirement:
    """A registry requirement expanded to a concrete field path for one case."""

    requirement: FieldRequirement
    field_path: str

    @property
    def requirement_id(self) -> str:
        return self.requirement.requirement_id

    @property
    def tier(self) -> FieldTier:
        return self.requirement.tier

    @property
    def gate_policy(self) -> EvidenceGatePolicy:
        return self.requirement.gate_policy


def _static_requirements() -> Tuple[FieldRequirement, ...]:
    critical = CRITICAL_GATE_POLICY
    important = IMPORTANT_GATE_POLICY
    return (
        FieldRequirement(
            requirement_id="groundwater.hydraulic_gradient",
            field_path_pattern="groundwater.hydraulic_gradient",
            tier=FieldTier.CRITICAL,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=critical,
        ),
        FieldRequirement(
            requirement_id="groundwater.depth_to_groundwater_m",
            field_path_pattern="groundwater.depth_to_groundwater_m",
            tier=FieldTier.CRITICAL,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=critical,
        ),
        FieldRequirement(
            requirement_id="subsurface.soil_id",
            field_path_pattern="subsurface.soil_id",
            tier=FieldTier.CRITICAL,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=critical,
        ),
        FieldRequirement(
            requirement_id="receptors.active.distance_m",
            field_path_pattern="receptors[{receptor_id}].distance_m",
            tier=FieldTier.CRITICAL,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=critical,
        ),
        FieldRequirement(
            requirement_id="constituents.gating.source_concentration",
            field_path_pattern="constituents[{constituent_id}].source_concentration",
            tier=FieldTier.CRITICAL,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=critical,
        ),
        FieldRequirement(
            requirement_id="constituents.gating.source_basis",
            field_path_pattern="constituents[{constituent_id}].source_basis",
            tier=FieldTier.CRITICAL,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=critical,
        ),
        FieldRequirement(
            requirement_id="treatment.treatment_level",
            field_path_pattern="treatment.treatment_level",
            tier=FieldTier.IMPORTANT,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=important,
        ),
        FieldRequirement(
            requirement_id="treatment.disinfection_status",
            field_path_pattern="treatment.disinfection_status",
            tier=FieldTier.IMPORTANT,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=important,
        ),
        FieldRequirement(
            requirement_id="physics.dispersivity_method",
            field_path_pattern="physics.dispersivity_method",
            tier=FieldTier.IMPORTANT,
            allowed_provenance_classes=_ALL_PROVENANCE,
            acceptable_review_statuses=_ACCEPTED_ONLY,
            gate_policy=important,
        ),
    )


_RECEPTOR_PATH_RE = re.compile(r"^receptors\[([A-Za-z0-9][A-Za-z0-9_.-]*)\]\.distance_m$")
_CONSTITUENT_CONC_RE = re.compile(
    r"^constituents\[([A-Za-z0-9][A-Za-z0-9_.-]*)\]\.source_concentration$"
)
_CONSTITUENT_BASIS_RE = re.compile(
    r"^constituents\[([A-Za-z0-9][A-Za-z0-9_.-]*)\]\.source_basis$"
)


def validate_registry_definitions(
    definitions: Iterable[FieldRequirement],
) -> Tuple[FieldRequirement, ...]:
    """Validate registry definitions and return an immutable tuple.

    Raises :class:`EvidenceContractError` when requirement IDs or static field
    path patterns duplicate.
    """
    items = tuple(definitions)
    seen_ids: dict[str, FieldRequirement] = {}
    seen_static_paths: dict[str, FieldRequirement] = {}
    for req in items:
        if req.requirement_id in seen_ids:
            raise EvidenceContractError(
                f"Duplicate evidence registry requirement_id {req.requirement_id!r}."
            )
        seen_ids[req.requirement_id] = req
        if "{" not in req.field_path_pattern:
            if req.field_path_pattern in seen_static_paths:
                raise EvidenceContractError(
                    f"Duplicate evidence registry field_path_pattern "
                    f"{req.field_path_pattern!r}."
                )
            seen_static_paths[req.field_path_pattern] = req
    return items


STATIC_FIELD_REQUIREMENTS: Tuple[FieldRequirement, ...] = validate_registry_definitions(
    _static_requirements()
)

_STATIC_BY_PATH: Mapping[str, FieldRequirement] = {
    req.field_path_pattern: req for req in STATIC_FIELD_REQUIREMENTS if "{" not in req.field_path_pattern
}

_TEMPLATE_BY_ID: Mapping[str, FieldRequirement] = {
    req.requirement_id: req
    for req in STATIC_FIELD_REQUIREMENTS
    if "{" in req.field_path_pattern
}


def gating_constituents(case: SiteCaseV1) -> Tuple[ConstituentSelection, ...]:
    """Constituents that participate in evidence gating (non-``reference_only``)."""
    return tuple(
        c for c in case.constituents if c.role is ConstituentRole.GATING
    )


def _expand_receptor_requirements(case: SiteCaseV1) -> Tuple[ResolvedFieldRequirement, ...]:
    template = _TEMPLATE_BY_ID["receptors.active.distance_m"]
    active = tuple(r for r in case.receptors if r.active)
    active = tuple(sorted(active, key=lambda r: r.receptor_id))
    return tuple(
        ResolvedFieldRequirement(
            requirement=template,
            field_path=f"receptors[{r.receptor_id}].distance_m",
        )
        for r in active
    )


def _expand_constituent_requirements(case: SiteCaseV1) -> Tuple[ResolvedFieldRequirement, ...]:
    conc_template = _TEMPLATE_BY_ID["constituents.gating.source_concentration"]
    basis_template = _TEMPLATE_BY_ID["constituents.gating.source_basis"]
    gating = tuple(sorted(gating_constituents(case), key=lambda c: c.constituent_id))
    resolved: list[ResolvedFieldRequirement] = []
    for c in gating:
        base = f"constituents[{c.constituent_id}]"
        resolved.append(
            ResolvedFieldRequirement(
                requirement=conc_template,
                field_path=f"{base}.source_concentration",
            )
        )
        resolved.append(
            ResolvedFieldRequirement(
                requirement=basis_template,
                field_path=f"{base}.source_basis",
            )
        )
    return tuple(resolved)


def _static_resolved_requirements() -> Tuple[ResolvedFieldRequirement, ...]:
    static_paths = (
        "groundwater.hydraulic_gradient",
        "groundwater.depth_to_groundwater_m",
        "subsurface.soil_id",
        "treatment.treatment_level",
        "treatment.disinfection_status",
        "physics.dispersivity_method",
    )
    return tuple(
        ResolvedFieldRequirement(requirement=_STATIC_BY_PATH[path], field_path=path)
        for path in static_paths
    )


def _tier_sort_key(resolved: ResolvedFieldRequirement) -> tuple:
    tier_order = {
        FieldTier.CRITICAL: 0,
        FieldTier.IMPORTANT: 1,
        FieldTier.INFORMATIONAL: 2,
    }
    return (tier_order[resolved.tier], resolved.field_path, resolved.requirement_id)


def iter_required_field_paths(case: SiteCaseV1) -> Tuple[ResolvedFieldRequirement, ...]:
    """Expand all load-bearing field requirements for ``case`` in deterministic order."""
    combined = (
        *_static_resolved_requirements(),
        *_expand_receptor_requirements(case),
        *_expand_constituent_requirements(case),
    )
    return tuple(sorted(combined, key=_tier_sort_key))


def get_field_requirement(field_path: str) -> Optional[FieldRequirement]:
    """Return the registry requirement for a concrete ``field_path``, if any."""
    if field_path in _STATIC_BY_PATH:
        return _STATIC_BY_PATH[field_path]
    match = _RECEPTOR_PATH_RE.match(field_path)
    if match is not None:
        return _TEMPLATE_BY_ID["receptors.active.distance_m"]
    if _CONSTITUENT_CONC_RE.match(field_path) is not None:
        return _TEMPLATE_BY_ID["constituents.gating.source_concentration"]
    if _CONSTITUENT_BASIS_RE.match(field_path) is not None:
        return _TEMPLATE_BY_ID["constituents.gating.source_basis"]
    return None


def iter_registry_definitions() -> Tuple[FieldRequirement, ...]:
    """Iterate immutable registry definitions in deterministic order."""
    return STATIC_FIELD_REQUIREMENTS


__all__ = [
    "REGISTRY_VERSION",
    "EvidenceGatePolicy",
    "FieldRequirement",
    "ResolvedFieldRequirement",
    "CRITICAL_GATE_POLICY",
    "IMPORTANT_GATE_POLICY",
    "STATIC_FIELD_REQUIREMENTS",
    "gating_constituents",
    "validate_registry_definitions",
    "iter_required_field_paths",
    "get_field_requirement",
    "iter_registry_definitions",
]
