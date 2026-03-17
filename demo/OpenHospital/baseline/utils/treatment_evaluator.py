"""
Treatment Evaluator for Hospital Simulation.
Evaluates proposed treatment plans against ground truth using LLM.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)

GROUND_TRUTH_PATH = Path(__file__).parent.parent / "data" / "ground_truth" / "ground_truth.json"


@dataclass
class EvaluationResult:
    """Result of treatment evaluation."""
    patient_id: str
    final_score: float       
    dimension_scores: Dict[str, float]
    feedback: str


def load_ground_truth() -> Dict[str, Any]:
    """Load ground truth data from JSON file."""
    if not GROUND_TRUTH_PATH.exists():
        raise FileNotFoundError(f"Ground truth file not found: {GROUND_TRUTH_PATH}")
    
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_patient_ground_truth(patient_id: str) -> Optional[Dict[str, Any]]:
    """Get ground truth for a specific patient."""
    ground_truth = load_ground_truth()
    return ground_truth.get(patient_id)


async def evaluate_treatment(
    patient_id: str,
    proposed_treatment: str,
    model_router: Any
) -> EvaluationResult:
    """
    Evaluate a proposed treatment plan against ground truth using LLM.
    
    Args:
        patient_id: Patient ID (e.g., "Patient_001")
        proposed_treatment: Proposed treatment plan as text
        model_router: Model router for LLM calls
    
    Returns:
        EvaluationResult with final score (0-1) and feedback
    """
    ground_truth = get_patient_ground_truth(patient_id)
    if not ground_truth:
        return EvaluationResult(
            patient_id=patient_id,
            final_score=0.0,
            dimension_scores={},
            feedback=f"No ground truth found for patient {patient_id}"
        )
    final_diagnosis = ground_truth.get("final_diagnosis", "")
    disease_name = ", ".join(final_diagnosis) if isinstance(final_diagnosis, list) else final_diagnosis
    treatment_plan = ground_truth.get("treatment_plan", {})
    gt_treatment_text = f"""Medications: {', '.join(treatment_plan.get('medications', []))}
Surgeries/Procedures: {', '.join(treatment_plan.get('surgeries_or_procedures', [])) or 'None'}
Admission Advice: {treatment_plan.get('admission_advice', 'N/A')}"""

    system_prompt = """You are a medical expert evaluating treatment plans.

Given the disease name, standard treatment plan (ground truth), and a proposed treatment plan, evaluate the proposed treatment.

Score the following dimensions (each 0-1):
1. diagnosis_accuracy: Does the proposed treatment address the correct disease?
2. medication_appropriateness: Are the medications appropriate for this condition?
3. procedure_completeness: Are necessary procedures/examinations included?
4. safety: Is the treatment safe and without harmful omissions?

Weights: diagnosis_accuracy=0.3, medication_appropriateness=0.35, procedure_completeness=0.2, safety=0.15

Respond ONLY in JSON format:
{
    "diagnosis_accuracy": <0-1>,
    "medication_appropriateness": <0-1>,
    "procedure_completeness": <0-1>,
    "safety": <0-1>,
    "feedback": "<brief overall feedback>"
}"""

    user_prompt = f"""Disease: {disease_name}

Standard Treatment Plan:
{gt_treatment_text}

Proposed Treatment Plan:
{proposed_treatment}

Please evaluate the proposed treatment."""

    try:
        response = await model_router.chat(user_prompt, system_prompt=system_prompt)
        response_text = response.strip()
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        evaluation = json.loads(response_text)
        dimension_scores = {
            "diagnosis_accuracy": float(evaluation.get("diagnosis_accuracy", 0)),
            "medication_appropriateness": float(evaluation.get("medication_appropriateness", 0)),
            "procedure_completeness": float(evaluation.get("procedure_completeness", 0)),
            "safety": float(evaluation.get("safety", 0))
        }
        weights = {
            "diagnosis_accuracy": 0.3,
            "medication_appropriateness": 0.35,
            "procedure_completeness": 0.2,
            "safety": 0.15
        }
        
        final_score = sum(
            dimension_scores[k] * weights[k] for k in weights
        )
        final_score = max(0.0, min(1.0, final_score))                
        
        return EvaluationResult(
            patient_id=patient_id,
            final_score=round(final_score, 4),
            dimension_scores=dimension_scores,
            feedback=evaluation.get("feedback", "")
        )
        
    except Exception as e:
        logger.error(f"Evaluation failed for {patient_id}: {e}")
        return EvaluationResult(
            patient_id=patient_id,
            final_score=0.0,
            dimension_scores={},
            feedback=f"Evaluation failed: {e}"
        )
