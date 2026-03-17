"""Simulation event schemas."""

from typing import Dict, Any, Literal
from pydantic import BaseModel


EventCategory = Literal["agent", "system", "environment"]


class SimulationEvent(BaseModel):
    """Simulation event."""
    category: EventCategory
    name: str
    payload: Dict[str, Any]
    tick: int


class SimulationStatus(BaseModel):
    """Simulation status."""
    current_tick: int = 0
    total_doctors: int = 0
    total_patients: int = 0
    active_consultations: int = 0
    is_running: bool = False


class SimulationStatistics(BaseModel):
    """Simulation statistics."""
    diagnosis_accuracy: float = 0.0
    examination_precision: float = 0.0
    total_tokens: int = 0
