"""Prescription schemas."""

from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel


class TreatmentResult(BaseModel):
    """Treatment result."""
    success: bool
    score: float
    feedback: str


class PrescriptionRecord(BaseModel):
    """Prescription record."""
    id: str
    patient_id: str
    doctor_id: str
    diagnosis: str
    treatment_plan: str
    prescribed_tick: int
    status: Literal["pending", "completed"]
    completed_tick: Optional[int] = None
    treatment_result: Optional[TreatmentResult] = None

