# ADR-0002 — Physics Engine Tier Structure

**Status:** Accepted — sad-1.0.0
**Date:** 2025 (initial)

---

## Context

The Groundwater Screening Toolkit began as a single-script tool.  As
multiple calculation methods were considered (steady-state decay,
Ogata-Banks transient, future Domenico, etc.), the need for a structured
way to register, describe, and invoke physics engines became apparent.

Without a registry, each call site would need to know which module and
function to import.  This creates a fragile, convention-based system where
the caller is responsible for finding and calling the right function —
with no enforcement that the function has been vetted or authorized.

## Decision

Physics engines are organized into tiers:

- **Tier 1 (Screening):** Fast, analytical, 1-D, steady-state-flow
  solutions appropriate for regulatory screening.  Ogata-Banks 1D and the
  transport module's advection-decay model are Tier 1.
- **Tier 2 (Numerical):** Numerical models (HYDRUS, MODFLOW/MT3DMS) that
  may be wrapped in future versions for site-specific analysis.  Not yet
  implemented.

All tiers must register through a common registry (`core/physics_registry.py`)
so that:

1. Every registered engine is discoverable.
2. Every execution path goes through a common authorization gate.
3. Metadata (name, version, scope) is consistently available.

Engine modules follow the naming convention `core/physics_<name>.py`.
Each module registers a singleton instance at import time.

## Consequences

- **Positive:** Consistent discovery and execution path for all engines.
- **Positive:** Tier 1 engines share a common authorization model.
- **Negative:** Adding an engine requires following the registration
  convention; a bare function is not sufficient.
- **Neutral:** The tier structure is forward-looking; Tier 2 is not yet
  implemented and may require a separate ADR.

## References

- `docs/adr/ADR-0005-abstract-physics-engine-interface.md`
- `core/physics_registry.py`
