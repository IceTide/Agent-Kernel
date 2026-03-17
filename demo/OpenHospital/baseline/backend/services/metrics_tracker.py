"""
Real-time Metrics Tracker Service - Track per-doctor cumulative metrics.

This service tracks three key metrics for each doctor in real-time:
1. Diagnosis Accuracy
2. Examination Precision
3. Treatment Evaluation (Safety, Effectiveness, Personalization)

Memory Optimization:
- History lists are bounded to prevent unbounded memory growth
- Old data is preserved via cumulative sums, only details are discarded
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from collections import deque
import logging

logger = logging.getLogger(__name__)
MAX_HISTORY_LENGTH = 500


@dataclass
class CumulativeMetrics:
    """Cumulative metrics for a single doctor."""
    doctor_id: str
    diagnosis_total: int = 0                      
    diagnosis_accuracy_sum: float = 0.0                                 
    diagnosis_history: deque = field(default_factory=lambda: deque(maxlen=MAX_HISTORY_LENGTH))
    examination_total: int = 0
    examination_precision_sum: float = 0.0
    examination_history: deque = field(default_factory=lambda: deque(maxlen=MAX_HISTORY_LENGTH))
    treatment_total: int = 0
    treatment_score_sum: float = 0.0
    treatment_safety_sum: float = 0.0
    treatment_effectiveness_sum: float = 0.0
    treatment_personalization_sum: float = 0.0
    treatment_history: deque = field(default_factory=lambda: deque(maxlen=MAX_HISTORY_LENGTH))

    def add_diagnosis(self, patient_accuracy: float, tick: int, patient_id: str,
                      correct_count: int = 0, total_expected: int = 1):
        """Add a diagnosis result for a patient.

        Args:
            patient_accuracy: Accuracy for this patient (correct_count / total_expected)
            tick: Current simulation tick
            patient_id: Patient ID
            correct_count: Number of correct diagnoses
            total_expected: Total expected diagnoses for this patient
        """
        self.diagnosis_total += 1
        self.diagnosis_accuracy_sum += patient_accuracy

        avg_accuracy = self.diagnosis_accuracy_sum / self.diagnosis_total
        self.diagnosis_history.append({
            "patient_count": self.diagnosis_total,
            "accuracy": avg_accuracy,
            "tick": tick,
            "patient_id": patient_id,
            "patient_accuracy": patient_accuracy,
            "correct_count": correct_count,
            "total_expected": total_expected
        })

    def add_examination(self, precision: float, tick: int, patient_id: str):
        """Add an examination result."""
        self.examination_total += 1
        self.examination_precision_sum += precision

        avg_precision = self.examination_precision_sum / self.examination_total
        self.examination_history.append({
            "patient_count": self.examination_total,
            "precision": avg_precision,
            "tick": tick,
            "patient_id": patient_id,
            "current_precision": precision
        })

    def add_treatment(self, overall_score: float, safety: float,
                     effectiveness: float, personalization: float,
                     tick: int, patient_id: str):
        """Add a treatment evaluation result."""
        self.treatment_total += 1
        self.treatment_score_sum += overall_score
        self.treatment_safety_sum += safety
        self.treatment_effectiveness_sum += effectiveness
        self.treatment_personalization_sum += personalization

        avg_score = self.treatment_score_sum / self.treatment_total
        avg_safety = self.treatment_safety_sum / self.treatment_total
        avg_effectiveness = self.treatment_effectiveness_sum / self.treatment_total
        avg_personalization = self.treatment_personalization_sum / self.treatment_total

        self.treatment_history.append({
            "patient_count": self.treatment_total,
            "overall_score": avg_score,
            "safety": avg_safety,
            "effectiveness_alignment": avg_effectiveness,
            "personalization": avg_personalization,
            "tick": tick,
            "patient_id": patient_id,
            "current_score": overall_score
        })

    def get_current_stats(self) -> Dict[str, Any]:
        """Get current statistics."""
        return {
            "doctor_id": self.doctor_id,
            "diagnosis": {
                "total": self.diagnosis_total,
                "accuracy": self.diagnosis_accuracy_sum / self.diagnosis_total if self.diagnosis_total > 0 else 0.0
            },
            "examination": {
                "total": self.examination_total,
                "average_precision": self.examination_precision_sum / self.examination_total if self.examination_total > 0 else 0.0
            },
            "treatment": {
                "total": self.treatment_total,
                "average_score": self.treatment_score_sum / self.treatment_total if self.treatment_total > 0 else 0.0,
                "average_safety": self.treatment_safety_sum / self.treatment_total if self.treatment_total > 0 else 0.0,
                "average_effectiveness": self.treatment_effectiveness_sum / self.treatment_total if self.treatment_total > 0 else 0.0,
                "average_personalization": self.treatment_personalization_sum / self.treatment_total if self.treatment_total > 0 else 0.0
            }
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (convert deque to list for serialization)."""
        return {
            "doctor_id": self.doctor_id,
            "diagnosis_total": self.diagnosis_total,
            "diagnosis_accuracy_sum": self.diagnosis_accuracy_sum,
            "diagnosis_history": list(self.diagnosis_history),
            "examination_total": self.examination_total,
            "examination_precision_sum": self.examination_precision_sum,
            "examination_history": list(self.examination_history),
            "treatment_total": self.treatment_total,
            "treatment_score_sum": self.treatment_score_sum,
            "treatment_safety_sum": self.treatment_safety_sum,
            "treatment_effectiveness_sum": self.treatment_effectiveness_sum,
            "treatment_personalization_sum": self.treatment_personalization_sum,
            "treatment_history": list(self.treatment_history),
        }


class MetricsTracker:
    """Track real-time metrics for all doctors."""

    def __init__(self):
        self._metrics: Dict[str, CumulativeMetrics] = {}
        logger.info("MetricsTracker initialized")

    def get_or_create_metrics(self, doctor_id: str) -> CumulativeMetrics:
        """Get or create metrics for a doctor."""
        if doctor_id not in self._metrics:
            self._metrics[doctor_id] = CumulativeMetrics(doctor_id=doctor_id)
            logger.info(f"Created metrics tracker for doctor: {doctor_id}")
        return self._metrics[doctor_id]

    def add_diagnosis(self, doctor_id: str, patient_accuracy: float, tick: int, patient_id: str,
                      correct_count: int = 0, total_expected: int = 1):
        """Record a diagnosis result for a patient."""
        metrics = self.get_or_create_metrics(doctor_id)
        metrics.add_diagnosis(patient_accuracy, tick, patient_id, correct_count, total_expected)
        logger.debug(f"Added diagnosis for {doctor_id}: patient_accuracy={patient_accuracy:.2f}, total_patients={metrics.diagnosis_total}")

    def add_examination(self, doctor_id: str, precision: float, tick: int, patient_id: str):
        """Record an examination result."""
        metrics = self.get_or_create_metrics(doctor_id)
        metrics.add_examination(precision, tick, patient_id)
        logger.debug(f"Added examination for {doctor_id}: precision={precision:.2f}, total={metrics.examination_total}")

    def add_treatment(self, doctor_id: str, overall_score: float, safety: float,
                     effectiveness: float, personalization: float,
                     tick: int, patient_id: str):
        """Record a treatment evaluation result."""
        metrics = self.get_or_create_metrics(doctor_id)
        metrics.add_treatment(overall_score, safety, effectiveness, personalization, tick, patient_id)
        logger.debug(f"Added treatment for {doctor_id}: score={overall_score:.2f}, total={metrics.treatment_total}")

    def get_doctor_metrics(self, doctor_id: str) -> Optional[Dict[str, Any]]:
        """Get metrics for a specific doctor."""
        if doctor_id not in self._metrics:
            return None
        return self._metrics[doctor_id].to_dict()

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all doctors."""
        return {
            doctor_id: metrics.to_dict()
            for doctor_id, metrics in self._metrics.items()
        }

    def get_doctor_stats(self, doctor_id: str) -> Optional[Dict[str, Any]]:
        """Get current statistics for a doctor."""
        if doctor_id not in self._metrics:
            return None
        return self._metrics[doctor_id].get_current_stats()

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get current statistics for all doctors."""
        return {
            doctor_id: metrics.get_current_stats()
            for doctor_id, metrics in self._metrics.items()
        }

    def clear(self):
        """Clear all metrics."""
        self._metrics = {}
        logger.info("MetricsTracker cleared")

    def clear_doctor(self, doctor_id: str):
        """Clear metrics for a specific doctor."""
        if doctor_id in self._metrics:
            del self._metrics[doctor_id]
            logger.info(f"Cleared metrics for doctor: {doctor_id}")
_metrics_tracker: Optional[MetricsTracker] = None


def get_metrics_tracker() -> MetricsTracker:
    """Get the global metrics tracker instance."""
    global _metrics_tracker
    if _metrics_tracker is None:
        _metrics_tracker = MetricsTracker()
    return _metrics_tracker


def reset_metrics_tracker():
    """Reset the global metrics tracker."""
    global _metrics_tracker
    _metrics_tracker = MetricsTracker()
