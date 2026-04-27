"""Public package surface for the CHORAS FA adapter."""

from .models import AdapterOutcome
from .orchestrator import run_from_choras_json

__version__ = "0.1.0"

__all__ = ["AdapterOutcome", "run_from_choras_json"]
