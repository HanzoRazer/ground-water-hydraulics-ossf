"""
core/contracts/legacy.py
========================

The single approved, explicit converter from the pre-V1 (unversioned) OSSF
site-config shape to :class:`~core.contracts.site_case_v1.SiteCaseV1`
(OSSF-GW-002 §3.10 / §5.7).

Conversion is deterministic and non-inventive:

* known legacy paths map to V1 paths through an explicit table;
* the free-form ``source.treatment_class`` narrative is mapped only through an
  explicit, tested lookup — an unknown string raises :class:`LegacyConfigError`
  rather than being guessed;
* missing material engineering assumptions are never fabricated;
* stable receptor IDs (absent in the legacy shape) are generated
  deterministically and reported as conversion warnings.

The converted result is routed through the canonical parser, so a successful
return is a fully validated :class:`SiteCaseV1`.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

from .enums import ReceptorType
from .errors import LegacyConfigError
from .serialization import parse_site_case_dict
from .site_case_v1 import SCHEMA_VERSION, SiteCaseV1

# Explicit legacy treatment narrative -> structured (level, status, method).
# Extend ONLY with known, unambiguous historical strings. No substring/heuristic
# interpretation is authorized.
_LEGACY_TREATMENT_MAP = {
    "Class I Aerobic + Disinfection (TCEQ Ch. 285.32)": ("secondary", "disinfected", "chlorine"),
}

_VALID_RECEPTOR_TYPES = {m.value for m in ReceptorType}


def _normalize_treatment_key(value: str) -> str:
    """Deterministic whitespace normalization for legacy treatment lookup only."""
    return " ".join(value.split())


def _lookup_legacy_treatment(tclass: str) -> tuple[str, str, str] | None:
    """Exact, then whitespace-normalized lookup against the explicit map."""
    if tclass in _LEGACY_TREATMENT_MAP:
        return _LEGACY_TREATMENT_MAP[tclass]
    norm = _normalize_treatment_key(tclass)
    for key, mapped in _LEGACY_TREATMENT_MAP.items():
        if _normalize_treatment_key(key) == norm:
            return mapped
    return None


def _warn(warnings_out: Optional[List[str]], message: str) -> None:
    if warnings_out is not None:
        warnings_out.append(message)


def convert_legacy_site_config_to_v1(
    raw: Mapping[str, Any],
    *,
    soil_database: Mapping[str, Any],
    constituent_database: Mapping[str, Any],
    warnings_out: Optional[List[str]] = None,
) -> SiteCaseV1:
    """Convert a pre-V1 site config to a validated :class:`SiteCaseV1`.

    Parameters
    ----------
    raw : the legacy (unversioned) config mapping.
    warnings_out : optional list; deterministic conversion warnings are
        appended to it (e.g. generated receptor IDs, treatment mapping used).

    Raises
    ------
    LegacyConfigError
        if the input already declares a schema version (not a legacy config),
        or if any value is materially ambiguous (e.g. an unknown treatment
        narrative or receptor type).
    """
    if not isinstance(raw, Mapping):
        raise LegacyConfigError(f"legacy config must be an object; got {type(raw).__name__}")
    if raw.get("schema_version"):
        raise LegacyConfigError(
            "input already declares a schema_version; use the V1 parser, not "
            "the legacy converter."
        )

    project = raw.get("project", {}) or {}
    site_id = project.get("site_id")
    if not site_id:
        raise LegacyConfigError("legacy config is missing project.site_id.")

    # Treatment: explicit table only.
    source = raw.get("source", {}) or {}
    tclass = source.get("treatment_class")
    mapped = _lookup_legacy_treatment(tclass) if isinstance(tclass, str) else None
    if mapped is None:
        raise LegacyConfigError(
            f"legacy source.treatment_class {tclass!r} is not in the explicit "
            "legacy treatment map; it is materially ambiguous and must be "
            "restated with structured V1 treatment fields rather than guessed."
        )
    level, status, method = mapped
    _warn(warnings_out, f"mapped legacy treatment_class {tclass!r} -> "
                        f"treatment_level={level}, disinfection_status={status}, "
                        f"disinfection_method={method}")

    subsurface = raw.get("subsurface", {}) or {}

    # Receptors: generate deterministic stable IDs (a label, not an assumption).
    legacy_receptors = raw.get("receptors", []) or []
    receptors: List[dict] = []
    for i, r in enumerate(legacy_receptors):
        rtype = r.get("type")
        if rtype not in _VALID_RECEPTOR_TYPES:
            raise LegacyConfigError(
                f"legacy receptor[{i}] type {rtype!r} is not a known receptor "
                f"type; expected one of {sorted(_VALID_RECEPTOR_TYPES)}."
            )
        rid = f"receptor_{i + 1}"
        _warn(warnings_out, f"generated receptor_id {rid!r} for legacy receptor "
                            f"{r.get('name')!r}")
        receptors.append({
            "receptor_id": rid,
            "receptor_type": rtype,
            "distance_m": r.get("distance_m"),
            "display_name": r.get("name"),
            "active": True,
        })

    # Constituents: preserve legacy default-vs-override + nitrate reference mode.
    c0_overrides = source.get("C0_overrides", {}) or {}
    nitrate_mode = (raw.get("reporting", {}) or {}).get(
        "nitrate_reporting_mode", "advective_reference_only"
    )
    constituents: List[dict] = []
    for cname in raw.get("constituents_to_evaluate", []) or []:
        is_nitrate = cname == "nitrate_as_N"
        role = ("reference_only"
                if is_nitrate and nitrate_mode == "advective_reference_only"
                else "gating")
        if cname in c0_overrides:
            constituents.append({
                "constituent_id": cname, "role": role,
                "source_concentration": c0_overrides[cname],
                "source_basis": "estimated",
            })
            _warn(warnings_out, f"constituent {cname!r} uses explicit legacy "
                                f"C0 override {c0_overrides[cname]!r} (source_basis=estimated)")
        else:
            constituents.append({
                "constituent_id": cname, "role": role,
                "use_governed_default": True, "source_basis": "regulatory_default",
            })
            _warn(warnings_out, f"constituent {cname!r} uses the governed "
                                "database default source concentration")

    physics = raw.get("physics", {}) or {}
    comparison = (raw.get("comparison_scenarios", {}) or {}).get("soils", []) or []

    v1_raw = {
        "schema_version": SCHEMA_VERSION,
        "site_id": site_id,
        "project": {
            "name": project.get("name"),
            "engineer": project.get("engineer"),
            "county": project.get("county"),
            "regulatory_authority": project.get("tceq_authority"),
            "description": source.get("description"),
        },
        "regulatory_location": {
            "edwards_aquifer_recharge_zone": (raw.get("regulatory_zones", {}) or {}).get("edwards_aquifer_recharge_zone", False),
            "edwards_aquifer_transition_zone": (raw.get("regulatory_zones", {}) or {}).get("edwards_aquifer_transition_zone", False),
            "edwards_aquifer_contributing_zone": (raw.get("regulatory_zones", {}) or {}).get("edwards_aquifer_contributing_zone", False),
            "karst_terrain": (raw.get("regulatory_zones", {}) or {}).get("karst_terrain", False),
            "coastal_zone": (raw.get("regulatory_zones", {}) or {}).get("coastal_zone", False),
        },
        "treatment": {
            "treatment_level": level,
            "disinfection_status": status,
            "disinfection_method": method,
        },
        "source": {
            "design_flow_gpd": source.get("design_flow_gpd"),
            "description": source.get("description"),
        },
        "subsurface": {
            "soil_id": subsurface.get("soil_type"),
            "soil_thickness_m": subsurface.get("soil_thickness_m"),
        },
        "groundwater": {
            "depth_to_groundwater_m": subsurface.get("depth_to_water_table_m"),
            "hydraulic_gradient": subsurface.get("hydraulic_gradient"),
        },
        "receptors": receptors,
        "constituents": constituents,
        "physics": {
            "engine": physics.get("engine"),
            "dispersivity_method": physics.get("dispersivity_method"),
        },
        "reporting": {
            "comparison_soil_ids": list(comparison),
        },
        "assumptions": [],
    }

    return parse_site_case_dict(
        v1_raw, soil_database=soil_database, constituent_database=constituent_database
    )


__all__ = ["convert_legacy_site_config_to_v1"]
