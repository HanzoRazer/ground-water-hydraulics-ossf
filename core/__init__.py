"""Core calculation modules for groundwater impact screening."""

from .darcy import FlowResult, evaluate_flow, darcy_flux, seepage_velocity
from .transport import TransportResult, evaluate_transport, retardation_factor, first_order_decay
from .attenuation import ReceptorEvaluation, classify_permeability, narrative_attestation

__all__ = [
    "FlowResult",
    "evaluate_flow",
    "darcy_flux",
    "seepage_velocity",
    "TransportResult",
    "evaluate_transport",
    "retardation_factor",
    "first_order_decay",
    "ReceptorEvaluation",
    "classify_permeability",
    "narrative_attestation",
]
