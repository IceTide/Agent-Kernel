"""Examination schemas."""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel


class ExaminationResult(BaseModel):
    """Single examination result."""
    name: str
    result: str
    reference_range: Optional[str] = None
    abnormal: Optional[bool] = None


class ExaminationRecord(BaseModel):
    """Examination record."""
    id: str
    patient_id: str
    doctor_id: str
    examination_items: List[str]
    ordered_tick: int
    status: Literal["pending", "completed"]
    completed_tick: Optional[int] = None
    results: Optional[Dict[str, Any]] = None

