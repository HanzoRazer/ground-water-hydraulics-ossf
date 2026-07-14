"""
core — Groundwater screening calculation modules.

Modules
-------
darcy               Darcy flux and seepage velocity
transport           Travel time, retardation, first-order decay / attenuation,
                    and the screening pass/fail policy
validation          Structural / cross-field site-configuration validation
report              Human-readable text report formatter
governance          METHODOLOGY_VERSION, MethodologyAttestation, sha256 helpers
preflight           Site Appropriateness Determination (SAD) rules and outcomes
authorization       ScreeningAuthorization token: minting and validation
run_session         RunSession context manager, SessionScopedExecutor (O(1) guard)
physics_engine_base AbstractPhysicsEngine base class; EngineMetadata
physics_ogata_banks Ogata-Banks 1D advection-dispersion engine
physics_registry    Engine registry; run_authorized_engine entry point
"""
