"""
Real-time Evaluation Background Task.

This module provides a background task that automatically evaluates
doctor performance in real-time as treatment events occur.

Evaluation trigger strategy:
- Diagnosis metrics: on PRESCRIBE_TREATMENT
- Treatment LLM evaluation: on RECEIVE_TREATMENT (after patient completes treatment)

Memory Optimization:
- processed_events uses a bounded deque to prevent unbounded growth
"""

import asyncio
import logging
from collections import deque
from typing import Dict, Any, Optional
from ..services import get_event_store, get_metrics_tracker, get_evaluation_cache
from .doctor import call_llm_for_evaluation, check_diagnosis_match_with_comorbidity, calculate_examination_precision, load_ground_truth

logger = logging.getLogger(__name__)


class RealTimeEvaluator:
    """Real-time evaluator that monitors events and updates metrics."""
    MAX_PROCESSED_EVENTS = 10000                 

    def __init__(self):
        self.event_store = get_event_store()
        self.metrics_tracker = get_metrics_tracker()
        self.evaluation_cache = get_evaluation_cache()
        self.ground_truth = {}
        self._processed_event_ids: deque = deque(maxlen=self.MAX_PROCESSED_EVENTS)
        self._processed_event_set: set = set()            
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.semaphore = asyncio.Semaphore(5)                                                   

    async def start(self):
        """Start the real-time evaluation task."""
        if self.is_running:
            logger.warning("RealTimeEvaluator is already running")
            return

        self.is_running = True
        self.task = asyncio.create_task(self._evaluation_loop())
        logger.info("RealTimeEvaluator started")

    async def stop(self):
        """Stop the real-time evaluation task."""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("RealTimeEvaluator stopped")

    def load_ground_truth_data(self):
        """Load ground truth data for evaluation."""
        try:
            self.ground_truth = load_ground_truth()
            logger.info(f"Loaded ground truth for {len(self.ground_truth)} patients")
        except Exception as e:
            logger.error(f"Failed to load ground truth: {e}")
            self.ground_truth = {}

    async def _evaluation_loop(self):
        """Main evaluation loop that processes events."""
        logger.info("Evaluation loop started")
        self.load_ground_truth_data()
        logger.info("Processing existing events in EventStore...")
        await self._process_new_events()
        logger.info(f"Initial processing complete. Processed {len(self._processed_event_set)} events.")

        while self.is_running:
            try:
                await self._process_new_events()
                await asyncio.sleep(2)                         

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in evaluation loop: {e}", exc_info=True)
                await asyncio.sleep(5)                        

        logger.info("Evaluation loop stopped")

    async def _process_new_events(self):
        """Process new events from the event store."""
        all_events = self.event_store.get_all_events()

        for event in all_events:
            event_id = self._get_event_id(event)
            if event_id in self._processed_event_set:
                continue
            event_name = event.get("name")

            if event_name == "PRESCRIBE_TREATMENT":
                await self._process_diagnosis_event(event)
            elif event_name == "RECEIVE_TREATMENT":
                await self._process_treatment_completion_event(event)
            elif event_name == "SCHEDULE_EXAMINATION":
                await self._process_examination_event(event)
            self._mark_event_processed(event_id)

    def _mark_event_processed(self, event_id: str):
        """Mark an event as processed with bounded storage."""
        if len(self._processed_event_ids) >= self.MAX_PROCESSED_EVENTS:
            oldest_id = self._processed_event_ids[0]              
            self._processed_event_set.discard(oldest_id)

        self._processed_event_ids.append(event_id)
        self._processed_event_set.add(event_id)

    def _get_event_id(self, event: Dict[str, Any]) -> str:
        """Generate a unique ID for an event."""
        payload = event.get('payload', {})
        agent_id = payload.get('doctor_id', payload.get('agent_id', ''))
        patient_id = payload.get('patient_id', '')
        record_id = payload.get('record_id') or payload.get('prescription_id', '')
        return f"{event.get('tick', 0)}_{event.get('name', '')}_{agent_id}_{patient_id}_{record_id}"

    async def _process_diagnosis_event(self, event: Dict[str, Any]):
        """Process diagnosis metrics when doctor prescribes treatment."""
        try:
            payload = event.get("payload", {})
            doctor_id = payload.get("doctor_id", payload.get("agent_id", ""))
            patient_id = payload.get("patient_id", "")
            diagnosis = payload.get("diagnosis", "")
            tick = event.get("tick", 0)

            if not doctor_id or not patient_id:
                return
            patient_truth = self.ground_truth.get(patient_id, {})
            expected_diagnosis = patient_truth.get("final_diagnosis", "")

            if expected_diagnosis:
                all_correct, correct_count, total_expected = check_diagnosis_match_with_comorbidity(
                    diagnosis, expected_diagnosis
                )
                patient_accuracy = correct_count / total_expected if total_expected > 0 else 0.0
                self.metrics_tracker.add_diagnosis(
                    doctor_id, patient_accuracy, tick, patient_id,
                    correct_count, total_expected
                )
                logger.debug(f"Diagnosis evaluated for {doctor_id}: {correct_count}/{total_expected} correct, accuracy={patient_accuracy:.2f}")

        except Exception as e:
            logger.error(f"Error processing diagnosis event: {e}", exc_info=True)

    def _resolve_prescription_context(self, patient_id: str, record_id: str = "") -> Optional[Dict[str, Any]]:
        """Resolve prescription details (doctor/diagnosis/treatment) for a treatment completion event."""
        prescriptions = self.event_store.get_prescriptions(patient_id)
        if not prescriptions:
            return None
        if record_id:
            for prescription in reversed(prescriptions):
                if prescription.get("id") == record_id:
                    return prescription
        completed_prescriptions = [
            prescription for prescription in prescriptions
            if prescription.get("status") == "completed"
        ]
        if completed_prescriptions:
            return max(
                completed_prescriptions,
                key=lambda prescription: (
                    prescription.get("completed_tick") or 0,
                    prescription.get("prescribed_tick") or 0,
                ),
            )
        return max(
            prescriptions,
            key=lambda prescription: prescription.get("prescribed_tick") or 0,
        )

    async def _process_treatment_completion_event(self, event: Dict[str, Any]):
        """Process treatment evaluation only after patient completes treatment."""
        try:
            payload = event.get("payload", {})
            tick = event.get("tick", 0)

            patient_id = payload.get("patient_id", payload.get("agent_id", ""))
            record_id = payload.get("prescription_id") or payload.get("record_id", "")

            if not patient_id:
                return

            doctor_id = payload.get("doctor_id", "")
            diagnosis = payload.get("diagnosis", "")
            treatment_plan = payload.get("treatment_plan", "")

            if not doctor_id or not treatment_plan:
                prescription = self._resolve_prescription_context(patient_id, record_id)
                if not prescription:
                    logger.debug(
                        "Skip treatment evaluation: missing prescription context for patient=%s record=%s",
                        patient_id,
                        record_id,
                    )
                    return

                doctor_id = doctor_id or prescription.get("doctor_id", "")
                diagnosis = diagnosis or prescription.get("diagnosis", "")
                treatment_plan = treatment_plan or prescription.get("treatment_plan", "")

            if not doctor_id or not treatment_plan:
                return
            patient_truth = self.ground_truth.get(patient_id, {})
            reference_treatment = patient_truth.get("treatment_plan", "")

            if reference_treatment and treatment_plan:
                try:
                    eval_result = self.evaluation_cache.get_evaluation(
                        doctor_id, patient_id, diagnosis, treatment_plan
                    )
                    
                    if not eval_result:
                        async with self.semaphore:
                            eval_result = self.evaluation_cache.get_evaluation(
                                doctor_id, patient_id, diagnosis, treatment_plan
                            )
                            if not eval_result:
                                eval_result = await call_llm_for_evaluation(
                                    diagnosis=diagnosis,
                                    generated_treatment=treatment_plan,
                                    reference_treatment=reference_treatment
                                )
                                self.evaluation_cache.set_evaluation(
                                    doctor_id, patient_id, diagnosis, treatment_plan, eval_result
                                )
                    overall_score = eval_result.get("overall_score_normalized", 0.0)
                    safety = eval_result.get("safety_normalized", 0.0)
                    effectiveness = eval_result.get("effectiveness_alignment_normalized", 0.0)
                    personalization = eval_result.get("personalization_normalized", 0.0)
                    self.metrics_tracker.add_treatment(
                        doctor_id, overall_score, safety, effectiveness, personalization, tick, patient_id
                    )
                    logger.debug(f"Treatment evaluated for {doctor_id} after completion: score={overall_score:.2f}")

                except Exception as e:
                    logger.error(f"Failed to evaluate treatment for {doctor_id}: {e}")

        except Exception as e:
            logger.error(f"Error processing treatment completion event: {e}", exc_info=True)

    async def _process_examination_event(self, event: Dict[str, Any]):
        """Process an examination scheduling event."""
        try:
            payload = event.get("payload", {})
            doctor_id = payload.get("doctor_id", payload.get("agent_id", ""))
            patient_id = payload.get("patient_id", "")
            predicted_items = payload.get("items", [])
            tick = event.get("tick", 0)

            if not doctor_id or not patient_id or not predicted_items:
                return
            patient_truth = self.ground_truth.get(patient_id, {})
            expected_items = patient_truth.get("necessary_examinations", [])

            if expected_items:
                precision = calculate_examination_precision(predicted_items, expected_items)
                self.metrics_tracker.add_examination(doctor_id, precision, tick, patient_id)
                logger.debug(f"Examination evaluated for {doctor_id}: precision={precision:.2f}")

        except Exception as e:
            logger.error(f"Error processing examination event: {e}", exc_info=True)
_evaluator: Optional[RealTimeEvaluator] = None


def get_evaluator() -> RealTimeEvaluator:
    """Get the global evaluator instance."""
    global _evaluator
    if _evaluator is None:
        _evaluator = RealTimeEvaluator()
    return _evaluator


async def start_real_time_evaluation():
    """Start the real-time evaluation background task."""
    evaluator = get_evaluator()
    await evaluator.start()


async def stop_real_time_evaluation():
    """Stop the real-time evaluation background task."""
    evaluator = get_evaluator()
    await evaluator.stop()
