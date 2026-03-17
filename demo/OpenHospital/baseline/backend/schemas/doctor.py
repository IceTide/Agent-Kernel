"""Doctor schemas."""

from typing import List, Optional, Literal
from pydantic import BaseModel


class DoctorSummary(BaseModel):
    """Doctor summary for list view."""
    id: str
    name: str
    department: str
    specialties: List[str]
    current_status: Literal["idle", "consulting"] = "idle"
    patient_count: int = 0


class Doctor(BaseModel):
    """Full doctor profile."""
    id: str
    name: str
    department: str
    specialties: List[str]
    consultation_room: str
    current_status: Optional[str] = "idle"
    current_patients: Optional[List[dict]] = None


class DoctorStatistics(BaseModel):
    """Doctor statistics."""
    total_patients: int = 0
    diagnosis_accuracy: float = 0.0
    completed_consultations: int = 0
