# ADR-0005: Abstract Physics Engine

**Status:** Accepted — screening-3.0.0

## Context

Without a defined interface for physics engines, each engine implementation was
coupled to the calling code via ad-hoc conventions.  This made it impossible
to register and dispatch multiple engines without modifying the dispatch logic.

## Decision

Introduce `AbstractPhysicsEngine` (ABC) with `metadata() → EngineMetadata`
and `run(config) → dict` as the required contract.  `EngineMetadata` is a
frozen dataclass with `name`, `version`, and `description`.

`AbstractPhysicsEngine` and `register_engine` are Tier 2 (Extension API);
`EngineMetadata`, `get_engine`, and `list_engines` are Tier 1 (Consumer API).

## Consequences

Engine authors subclass `AbstractPhysicsEngine`; dispatch code uses
`get_engine(name)` without knowing implementation details.  A registry
(`_REGISTRY` in `core.physics_registry`) tracks active engines.

## References

- `core/physics_registry.py`
