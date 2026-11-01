"""Portable, standard-library-only offline GPU telemetry policy evaluator."""
from .validator import GateError, evaluate

__all__ = ["GateError", "evaluate"]
