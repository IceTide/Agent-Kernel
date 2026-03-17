"""Patient schemas."""

from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel
PatientPhase = str                                                                


class Demographics(BaseModel):
    """Patient demographics."""
    age: int = 0
    gender: str = "Unknown"                                   


class PatientSummary(BaseModel):
    """Patient summary for list view."""
    id: str
    name: str
    demographics: Demographics
    current_phase: PatientPhase = "idle"
    assigned_doctor: Optional[str] = None
    department: Optional[str] = None


class PatientState(BaseModel):
    """Patient runtime state."""
    current_phase: PatientPhase = "idle"
    assigned_doctor: Optional[str] = None
    department: Optional[str] = None
    consultation_room: Optional[str] = None
    current_location: Optional[str] = None
    treatment_result: Optional[Literal["success", "failure"]] = None


class TrajectoryEvent(BaseModel):
    """Patient trajectory event."""
    tick: int
    event_type: str
    agent_id: str
    status: str
    payload: Dict[str, Any] = {}


class Patient(BaseModel):
    """Full patient profile."""
    id: str
    name: str
    template: str = "PatientAgent"
    initial_location: str = "community"
    demographics: Demographics
    persona: str = ""
    initial_complaint: str = ""
    communication_style_label: str = ""
    appearance: str = ""
    current_phase: Optional[PatientPhase] = "idle"
    assigned_doctor: Optional[str] = None
    department: Optional[str] = None
    consultation_room: Optional[str] = None
    current_location: Optional[str] = None


class ExaminationRecord(BaseModel):
    """Examination record (imported for patient detail)."""
    id: str
    patient_id: str
    doctor_id: str
    examination_items: List[str]
    ordered_tick: int
    status: Literal["pending", "completed"]
    completed_tick: Optional[int] = None
    results: Optional[Dict[str, Any]] = None


class PrescriptionRecord(BaseModel):
    """Prescription record (imported for patient detail)."""
    id: str
    patient_id: str
    doctor_id: str
    diagnosis: str
    treatment_plan: str
    prescribed_tick: int
    status: Literal["pending", "completed"]
    completed_tick: Optional[int] = None
    treatment_result: Optional[Dict[str, Any]] = None


class PatientDetail(Patient):
    """Patient detail with all records."""
    state: PatientState = PatientState()
    examinations: List[ExaminationRecord] = []
    prescriptions: List[PrescriptionRecord] = []
    trajectory: List[TrajectoryEvent] = []
