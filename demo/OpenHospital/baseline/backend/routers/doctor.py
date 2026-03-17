"""Doctor API routes - using EventStore as data source."""

from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
import os
import re
import logging
import time
import yaml

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import get_event_store, get_metrics_tracker, get_evaluation_cache

router = APIRouter(prefix="/api/doctors", tags=["doctors"])
logger = logging.getLogger(__name__)
_GROUND_TRUTH_CACHE: Dict[str, Any] = {}
_GROUND_TRUTH_CACHE_PATH: Optional[Path] = None
_GROUND_TRUTH_CACHE_MTIME: Optional[float] = None
_DOCTOR_EVALUATION_CACHE: Dict[str, Dict[str, Any]] = {}
_DOCTOR_EVALUATION_CACHE_TTL_SECONDS = int(os.environ.get("HOSPITAL_DOCTOR_EVAL_CACHE_TTL", "15"))
_DOCTOR_EVALUATION_CACHE_MAX_SIZE = 128
_evaluation_router = None

def get_evaluation_router():
    """Get or create the evaluation model router."""
    global _evaluation_router
    
    if _evaluation_router is None:
        try:
            from agentkernel_distributed.toolkit.models import AsyncModelRouter
            config_path = Path(__file__).parent.parent.parent / "configs" / "models_config.yaml"
            if not config_path.exists():
                logger.warning(f"Models config not found at {config_path}")
                return None
            
            with open(config_path, 'r', encoding='utf-8') as f:
                models_configs = yaml.safe_load(f)
            evaluation_configs = [
                cfg for cfg in models_configs 
                if "evaluation" in cfg.get("capabilities", [])
            ]
            
            if not evaluation_configs:
                logger.warning("No evaluation models configured in models_config.yaml")
                return None
            for cfg in evaluation_configs:
                if "chat" not in cfg.get("capabilities", []):
                    cfg["capabilities"].append("chat")
            
            logger.info(f"Initializing evaluation router with {len(evaluation_configs)} model(s)")
            logger.debug(f"Evaluation models: {[cfg.get('model') for cfg in evaluation_configs]}")
            _evaluation_router = AsyncModelRouter(evaluation_configs)
            
        except Exception as e:
            logger.error(f"Failed to initialize evaluation router: {e}", exc_info=True)
            return None
    
    return _evaluation_router
def get_doctor_status(store, doctor_id: str) -> str:
    """根据医生活动判断当前状态。"""
    messages = store.get_messages(doctor_id)
    if messages:
        return "consulting"
    
    return "idle"


def _is_patient_id(agent_id: str) -> bool:
    """Support both Patient_ and Patient- ID formats."""
    if not agent_id:
        return False
    return agent_id.startswith("Patient_") or agent_id.startswith("Patient-")


def _normalize_patient_phase(raw_phase: Any) -> str:
    """Normalize patient phase for lightweight summaries."""
    phase = str(raw_phase or "")
    if phase in {
        "idle", "home", "registered", "consulting", "examined", "treated", "finish",
        "waiting", "examination", "awaiting_results", "treatment", "completed", "follow_up",
    }:
        return phase

    event_to_phase = {
        "PATIENT_REGISTER": "registered",
        "PATIENT_MOVE": "waiting",
        "SEND_MESSAGE": "consulting",
        "SCHEDULE_EXAMINATION": "consulting",
        "DO_EXAMINATION": "examined",
        "PRESCRIBE_TREATMENT": "treated",
        "RECEIVE_TREATMENT": "treated",
        "IDLE": "idle",
    }
    return event_to_phase.get(phase, "home")


def _collect_patient_ids_from_messages(messages: List[dict]) -> List[str]:
    """Collect unique patient IDs from a message list."""
    patient_ids = set()
    for msg in messages:
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")
        if _is_patient_id(sender):
            patient_ids.add(sender)
        if _is_patient_id(receiver):
            patient_ids.add(receiver)
    return sorted(patient_ids)


def _build_light_patient_summary(patient: dict, store) -> dict:
    """Build lightweight patient summary without expensive history queries."""
    patient_id = patient.get("id", "")
    demographics = patient.get("demographics") or {"age": 0, "gender": "Male"}
    patient_name = demographics.get("name") or patient.get("name", patient_id)

    status = store.get_patient_status(patient_id)
    status_details = status.get("details", {}) if isinstance(status.get("details"), dict) else {}

    return {
        "id": patient_id,
        "name": patient_name,
        "demographics": demographics,
        "current_phase": _normalize_patient_phase(status.get("phase", "")),
        "assigned_doctor": status.get("assigned_doctor", ""),
        "department": status.get("department") or status_details.get("department", ""),
    }


def _prune_doctor_evaluation_cache(now: float) -> None:
    """Prune expired/overflow doctor evaluation cache entries."""
    expired_doctors = [
        doctor_id
        for doctor_id, payload in _DOCTOR_EVALUATION_CACHE.items()
        if now - payload.get("created_at", 0.0) > _DOCTOR_EVALUATION_CACHE_TTL_SECONDS
    ]
    for doctor_id in expired_doctors:
        _DOCTOR_EVALUATION_CACHE.pop(doctor_id, None)

    if len(_DOCTOR_EVALUATION_CACHE) <= _DOCTOR_EVALUATION_CACHE_MAX_SIZE:
        return
    oldest_first = sorted(
        _DOCTOR_EVALUATION_CACHE.items(),
        key=lambda item: item[1].get("created_at", 0.0)
    )
    overflow = len(_DOCTOR_EVALUATION_CACHE) - _DOCTOR_EVALUATION_CACHE_MAX_SIZE
    for doctor_id, _ in oldest_first[:overflow]:
        _DOCTOR_EVALUATION_CACHE.pop(doctor_id, None)


def _to_normalized_score(value: Any) -> float:
    """Normalize a score to 0-1 range (supports legacy 1-5 values)."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0

    if score > 1.0:
        score = score / 5.0

    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _extract_normalized_eval_scores(eval_result: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Extract normalized treatment evaluation scores with backward compatibility."""
    safety = _to_normalized_score(eval_result.get("safety_normalized", eval_result.get("safety")))
    effectiveness = _to_normalized_score(
        eval_result.get("effectiveness_alignment_normalized", eval_result.get("effectiveness_alignment"))
    )
    personalization = _to_normalized_score(
        eval_result.get("personalization_normalized", eval_result.get("personalization"))
    )
    overall = _to_normalized_score(eval_result.get("overall_score_normalized", eval_result.get("overall_score")))
    return safety, effectiveness, personalization, overall


def build_doctor_summary(doctor: dict, store) -> dict:
    """构建 DoctorSummary 格式的响应。"""
    doctor_id = doctor.get("id", "")
    messages = store.get_messages(doctor_id)
    patient_ids = _collect_patient_ids_from_messages(messages)
    specialties = doctor.get("specialties", [])
    if isinstance(specialties, str):
        specialties = [specialties]
    
    return {
        "id": doctor_id,
        "name": doctor.get("name", doctor_id),
        "department": doctor.get("department", ""),
        "specialties": specialties,
        "current_status": get_doctor_status(store, doctor_id),
        "patient_count": len(patient_ids),
    }


def build_doctor_detail(doctor: dict, store) -> dict:
    """构建 Doctor 完整信息的响应。"""
    doctor_id = doctor.get("id", "")

    messages = store.get_messages(doctor_id)
    patient_ids = _collect_patient_ids_from_messages(messages)
    current_patients = []
    for patient_id in patient_ids:
        patient = store.get_agent(patient_id)
        if patient:
            current_patients.append(_build_light_patient_summary(patient, store))
    specialties = doctor.get("specialties", [])
    if isinstance(specialties, str):
        specialties = [specialties]

    return {
        "id": doctor_id,
        "name": doctor.get("name", doctor_id),
        "department": doctor.get("department", ""),
        "specialties": specialties,
        "consultation_room": doctor.get("consultation_room", ""),
        "current_status": get_doctor_status(store, doctor_id),
        "current_patients": current_patients,
    }


@router.get("", summary="获取所有医生列表")
async def get_doctors() -> List[dict]:
    """
    获取所有医生的摘要信息 (DoctorSummary[])。
    
    数据来源: EventStore (内存缓存或日志文件)
    """
    store = get_event_store()
    doctors = store.get_doctors()
    
    return [build_doctor_summary(doctor, store) for doctor in doctors]


@router.get("/{doctor_id}", summary="获取医生详情")
async def get_doctor(doctor_id: str) -> dict:
    """
    获取单个医生的完整信息 (Doctor)。
    """
    store = get_event_store()
    doctor = store.get_agent(doctor_id)
    
    if not doctor:
        raise HTTPException(status_code=404, detail=f"Doctor {doctor_id} not found")
    
    return build_doctor_detail(doctor, store)



@router.get("/{doctor_id}/patients", summary="获取医生的患者列表")
async def get_doctor_patients(doctor_id: str) -> List[dict]:
    """
    获取医生当前负责的患者摘要信息 (PatientSummary[])。
    """
    store = get_event_store()
    doctor = store.get_agent(doctor_id)
    
    if not doctor:
        raise HTTPException(status_code=404, detail=f"Doctor {doctor_id} not found")
    messages = store.get_messages(doctor_id)
    patient_ids = _collect_patient_ids_from_messages(messages)

    result = []
    for patient_id in patient_ids:
        patient = store.get_agent(patient_id)
        if patient:
            result.append(_build_light_patient_summary(patient, store))
    
    return result


@router.get("/{doctor_id}/conversations", summary="获取医生的所有对话")
async def get_doctor_conversations(doctor_id: str) -> List[dict]:
    """获取医生的所有对话记录。"""
    store = get_event_store()
    return store.get_messages(doctor_id)


def _infer_message_type(sender: str, receiver: str, fallback: Optional[str] = None) -> str:
    if fallback:
        return fallback
    if sender.startswith("Doctor_") and _is_patient_id(receiver):
        return "doctor_to_patient"
    if _is_patient_id(sender) and receiver.startswith("Doctor_"):
        return "patient_to_doctor"
    return "agent_to_agent"


@router.get("/{doctor_id}/consultations", summary="获取医生之间的会诊对话（按患者分组）")
async def get_doctor_consultations(doctor_id: str) -> List[dict]:
    """获取医生之间的会诊消息，按患者 ID 分组返回。"""
    store = get_event_store()
    messages = store.get_messages(doctor_id)

    grouped_messages: Dict[str, List[dict]] = {}

    for msg in messages:
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")
        if not sender.startswith("Doctor_") or not receiver.startswith("Doctor_"):
            continue

        metadata = msg.get("metadata") or {}
        patient_id = metadata.get("patient_id") or msg.get("patient_id")
        if not patient_id:
            continue

        grouped_messages.setdefault(patient_id, []).append(msg)

    results: List[dict] = []
    for patient_id, msgs in grouped_messages.items():
        sorted_msgs = sorted(msgs, key=lambda m: (m.get("tick", 0), m.get("timestamp", "")))
        formatted_messages = []
        for idx, msg in enumerate(sorted_msgs):
            sender = msg.get("sender", "")
            receiver = msg.get("receiver", "")
            formatted_messages.append(
                {
                    "id": idx + 1,
                    "sender": sender,
                    "receiver": receiver,
                    "content": msg.get("full_content") or msg.get("content", ""),
                    "created_at": msg.get("tick", 0),
                    "patient_id": patient_id,
                    "message_type": _infer_message_type(
                        sender, receiver, fallback=msg.get("message_type")
                    ),
                }
            )

        last_tick = max((m.get("created_at", 0) for m in formatted_messages), default=None)
        results.append(
            {
                "patient_id": patient_id,
                "message_count": len(formatted_messages),
                "last_message_tick": last_tick,
                "messages": formatted_messages,
            }
        )

    results.sort(key=lambda x: x.get("last_message_tick", 0) or 0, reverse=True)
    return results


@router.get("/{doctor_id}/statistics", summary="获取医生统计数据")
async def get_doctor_statistics(doctor_id: str) -> dict:
    """
    获取医生的统计数据 (DoctorStatistics)。
    """
    store = get_event_store()
    doctor = store.get_agent(doctor_id)
    
    if not doctor:
        raise HTTPException(status_code=404, detail=f"Doctor {doctor_id} not found")
    
    messages = store.get_messages(doctor_id)
    patient_ids = set()
    for msg in messages:
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")
        if _is_patient_id(sender):
            patient_ids.add(sender)
        if _is_patient_id(receiver):
            patient_ids.add(receiver)
    
    return {
        "total_patients": len(patient_ids),
        "diagnosis_accuracy": 0.0,
        "completed_consultations": 0,
    }

def load_ground_truth(force_reload: bool = False) -> Dict[str, Any]:
    """Load ground truth data with file-level cache and mtime invalidation."""
    global _GROUND_TRUTH_CACHE, _GROUND_TRUTH_CACHE_PATH, _GROUND_TRUTH_CACHE_MTIME

    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent                                          
    candidate_paths = [
        project_root / "data" / "ground_truth" / "ground_truth.json",
        Path("data/ground_truth/ground_truth.json"),
        Path("../data/ground_truth/ground_truth.json"),
        Path("../../data/ground_truth/ground_truth.json"),
    ]

    data_dir = os.environ.get("MAS_DATA_DIR")
    if data_dir:
        candidate_paths.append(Path(data_dir) / "ground_truth" / "ground_truth.json")

    ground_truth_file: Optional[Path] = None
    for path in candidate_paths:
        if path.exists():
            ground_truth_file = path
            break

    if ground_truth_file is None:
        if not _GROUND_TRUTH_CACHE:
            logger.warning("Ground truth file not found in any location")
        return _GROUND_TRUTH_CACHE

    try:
        file_mtime = ground_truth_file.stat().st_mtime
    except OSError:
        file_mtime = None

    cache_valid = (
        not force_reload
        and _GROUND_TRUTH_CACHE
        and _GROUND_TRUTH_CACHE_PATH == ground_truth_file
        and _GROUND_TRUTH_CACHE_MTIME == file_mtime
    )
    if cache_valid:
        return _GROUND_TRUTH_CACHE

    logger.info(f"Loading ground truth from: {ground_truth_file}")
    try:
        with open(ground_truth_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            logger.warning("Ground truth file format is not a dict, fallback to empty dict")
            data = {}

        _GROUND_TRUTH_CACHE = data
        _GROUND_TRUTH_CACHE_PATH = ground_truth_file
        _GROUND_TRUTH_CACHE_MTIME = file_mtime
        logger.info(f"Ground truth cache refreshed with {len(_GROUND_TRUTH_CACHE)} patients")
        return _GROUND_TRUTH_CACHE
    except Exception as e:
        logger.error(f"Failed to load ground truth: {e}")
        return _GROUND_TRUTH_CACHE


def check_diagnosis_match(predicted: str, expected: str) -> bool:
    """Check if predicted diagnosis matches expected (flexible matching).

    Args:
        predicted: Predicted diagnosis (string)
        expected: Expected diagnosis (string)

    Returns:
        True if predicted matches expected
    """
    if not expected:
        return False

    predicted_lower = predicted.lower().strip()
    expected_lower = expected.lower().strip()
    if predicted_lower == expected_lower:
        return True
    if expected_lower in predicted_lower or predicted_lower in expected_lower:
        return True

    return False


def check_diagnosis_match_with_comorbidity(predicted, expected) -> Tuple[bool, int, int]:
    """Check diagnosis match supporting both single and comorbidity cases.

    Args:
        predicted: Predicted diagnosis (string or list of strings)
        expected: Expected diagnosis (string or list of strings)

    Returns:
        Tuple of (all_correct, correct_count, total_expected)
        - all_correct: True if all expected diagnoses are matched
        - correct_count: Number of correctly matched diagnoses
        - total_expected: Total number of expected diagnoses
    """
    if isinstance(predicted, str):
        predicted_list = [predicted] if predicted else []
    else:
        predicted_list = predicted if predicted else []

    if isinstance(expected, str):
        expected_list = [expected] if expected else []
    else:
        expected_list = expected if expected else []

    if not expected_list:
        return False, 0, 0
    correct_count = 0
    for exp in expected_list:
        for pred in predicted_list:
            if check_diagnosis_match(pred, exp):
                correct_count += 1
                break

    all_correct = correct_count == len(expected_list)
    return all_correct, correct_count, len(expected_list)


def calculate_examination_precision(predicted_items: List[str], expected_items: List[str]) -> float:
    """
    Calculate examination precision.
    
    Formula: Precision = TP / |L_pred|
    where TP = |L_pred ∩ L_gold|
    """
    if not predicted_items:
        return 0.0
    
    predicted_set = set(predicted_items)
    expected_set = set(expected_items)
    tp = len(predicted_set & expected_set)
    precision = tp / len(predicted_set) if predicted_set else 0.0
    
    return precision


@router.get("/{doctor_id}/evaluation", summary="获取医生诊疗评估")
async def get_doctor_evaluation(doctor_id: str) -> Dict[str, Any]:
    """
    获取医生的诊疗表现评估。
    
    包括:
    - 诊治的患者列表
    - 每个患者的诊断准确性
    - 检查合理性（精确度）
    - 治疗方案评分（如有ground truth）
    """
    store = get_event_store()
    doctor = store.get_agent(doctor_id)
    
    if not doctor:
        raise HTTPException(status_code=404, detail=f"Doctor {doctor_id} not found")
    now = time.time()
    _prune_doctor_evaluation_cache(now)
    cached_payload = _DOCTOR_EVALUATION_CACHE.get(doctor_id)
    if cached_payload and now - cached_payload.get("created_at", 0.0) <= _DOCTOR_EVALUATION_CACHE_TTL_SECONDS:
        return cached_payload["data"]
    ground_truth = load_ground_truth()
    messages = store.get_messages(doctor_id)
    patient_ids = set()
    for msg in messages:
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")
        if _is_patient_id(sender):
            patient_ids.add(sender)
        if _is_patient_id(receiver):
            patient_ids.add(receiver)
    patient_evaluations = []
    total_diagnoses = 0
    correct_diagnoses = 0
    total_examinations = 0
    examination_precisions = []
    
    for patient_id in sorted(patient_ids):
        patient_eval = {
            "patient_id": patient_id,
            "patient_name": "",
            "diagnosis": {
                "predicted": "",
                "expected": "",
                "correct": False,
                "available": False
            },
            "examinations": [],
            "examination_precision": 0.0,
            "treatment": {
                "provided": False,
                "diagnosis": "",
                "treatment_plan": ""
            }
        }
        patient = store.get_agent(patient_id)
        if patient:
            patient_eval["patient_name"] = patient.get("name", patient_id)
        patient_truth = ground_truth.get(patient_id, {})
        prescriptions = store.get_prescriptions(patient_id)
        doctor_prescriptions = [
            p for p in prescriptions 
            if p.get("doctor_id") == doctor_id
        ]
        
        if doctor_prescriptions:
            latest_rx = doctor_prescriptions[-1]
            predicted_diagnosis = latest_rx.get("diagnosis", "")
            expected_diagnosis = patient_truth.get("final_diagnosis", "")

            if expected_diagnosis:
                all_correct, correct_count, total_expected = check_diagnosis_match_with_comorbidity(
                    predicted_diagnosis, expected_diagnosis
                )
                expected_display = expected_diagnosis if isinstance(expected_diagnosis, str) else ", ".join(expected_diagnosis)
                predicted_display = predicted_diagnosis if isinstance(predicted_diagnosis, str) else ", ".join(predicted_diagnosis) if predicted_diagnosis else ""

                patient_eval["diagnosis"] = {
                    "predicted": predicted_display,
                    "expected": expected_display,
                    "correct": all_correct,
                    "correct_count": correct_count,
                    "total_expected": total_expected,
                    "available": True
                }
                total_diagnoses += total_expected
                correct_diagnoses += correct_count
            else:
                predicted_display = predicted_diagnosis if isinstance(predicted_diagnosis, str) else ", ".join(predicted_diagnosis) if predicted_diagnosis else ""
                patient_eval["diagnosis"] = {
                    "predicted": predicted_display,
                    "expected": "",
                    "correct": False,
                    "available": False
                }
            treatment_plan = latest_rx.get("treatment_plan", "")
            reference_treatment = patient_truth.get("treatment_plan", "")
            
            treatment_eval_result = None
            if treatment_plan and reference_treatment:
                cache = get_evaluation_cache()
                raw_cached = cache.get_evaluation(
                    doctor_id, patient_id, predicted_diagnosis, treatment_plan
                )
                
                if raw_cached:
                    treatment_eval_result = raw_cached.copy()
                    safety, effectiveness, personalization, overall = _extract_normalized_eval_scores(raw_cached)
                    treatment_eval_result["safety"] = safety
                    treatment_eval_result["effectiveness_alignment"] = effectiveness
                    treatment_eval_result["personalization"] = personalization
                    treatment_eval_result["overall_score"] = overall
                    treatment_eval_result["safety_normalized"] = safety
                    treatment_eval_result["effectiveness_alignment_normalized"] = effectiveness
                    treatment_eval_result["personalization_normalized"] = personalization
                    treatment_eval_result["overall_score_normalized"] = overall

            patient_eval["treatment"] = {
                "provided": True,
                "diagnosis": predicted_display,                                      
                "treatment_plan": treatment_plan,
                "reference_treatment": reference_treatment,            
                "evaluation": treatment_eval_result                                     
            }
        examinations = store.get_examinations(patient_id)
        doctor_examinations = [
            e for e in examinations 
            if e.get("doctor_id") == doctor_id
        ]
        
        exam_details = []
        for exam in doctor_examinations:
            predicted_items = exam.get("examination_items", [])
            expected_items = patient_truth.get("necessary_examinations", [])
            
            precision = 0.0
            if predicted_items and expected_items:
                precision = calculate_examination_precision(predicted_items, expected_items)
                examination_precisions.append(precision)
                total_examinations += 1
            elif predicted_items:
                total_examinations += 1
            
            exam_details.append({
                "ordered_tick": exam.get("ordered_tick", 0),
                "items": predicted_items,
                "expected_items": expected_items,
                "precision": round(precision, 4),
                "has_ground_truth": bool(expected_items)
            })
        
        patient_eval["examinations"] = exam_details
        if exam_details:
            precisions_with_gt = [e["precision"] for e in exam_details if e["has_ground_truth"]]
            if precisions_with_gt:
                patient_eval["examination_precision"] = round(
                    sum(precisions_with_gt) / len(precisions_with_gt), 4
                )
        
        patient_evaluations.append(patient_eval)
    diagnosis_accuracy = (
        correct_diagnoses / total_diagnoses 
        if total_diagnoses > 0 else 0.0
    )
    
    average_examination_precision = (
        sum(examination_precisions) / len(examination_precisions)
        if examination_precisions else 0.0
    )
    
    result = {
        "doctor_id": doctor_id,
        "doctor_name": doctor.get("name", doctor_id),
        "department": doctor.get("department", ""),
        "summary": {
            "total_patients": len(patient_ids),
            "total_diagnoses": total_diagnoses,
            "correct_diagnoses": correct_diagnoses,
            "diagnosis_accuracy": round(diagnosis_accuracy, 4),
            "total_examinations": total_examinations,
            "average_examination_precision": round(average_examination_precision, 4),
            "has_ground_truth": bool(ground_truth)
        },
        "patients": patient_evaluations
    }

    _DOCTOR_EVALUATION_CACHE[doctor_id] = {
        "created_at": now,
        "data": result,
    }

    return result

class TreatmentEvaluationRequest(BaseModel):
    """Request model for treatment evaluation."""
    doctor_id: Optional[str] = None
    patient_id: str
    diagnosis: str
    treatment_plan: str
    reference_treatment: str


class TreatmentEvaluationResponse(BaseModel):
    """Response model for treatment evaluation."""
    patient_id: str
    clinical_appropriateness: float                                   
    completeness: float                                   
    safety: float
    effectiveness_alignment: float
    personalization: float
    overall_score: float
    reasoning: str
    evaluation_method: str = "llm"
TREATMENT_EVALUATION_SYSTEM_PROMPT = """Role: Medical Expert Evaluator
Objective: Evaluate an AI-generated treatment plan against a specific Patient Case and a Reference Standard.
You will be provided with three key inputs:
1. **Patient Case:** Clinical profile (History, Diagnostics, **Explicit Contraindications List**).
2. **Reference (Standard of Care):** The ground truth medical standard for this specific case.
3. **Generated Treatment:** The AI plan to be evaluated.
*Focus: Harm Avoidance. Check against the provided 'CONTRAINDICATIONS' list and Patient Profile.*
*Note: Safety is a baseline requirement, not a bonus. Violations result in score deductions.*
- **5 (Safe):** No safety risks. Perfectly respects the provided Contraindications list, allergies, and interactions. (No deduction)
- **4 (Good):** Minor considerations (e.g., monitoring needed) but no direct harm. (Deduct 0.3 points)
- **3 (Fair):** Minor oversight (e.g., missing cautionary advice). (Deduct 1.0 point)
- **2 (Risky):** Significant risk (e.g., ignored interaction, age-inappropriate). (Deduct 2.0 points)
- **1 (Dangerous):** FATAL/SEVERE error. Violates the provided **CONTRAINDICATIONS** list, causes lethal interaction, or pregnancy violation. (Deduct 4.0 points)
*Focus: Alignment with the provided 'Reference (Standard of Care)'.*
- **5 (Excellent):** Perfect Alignment. Matches the **Reference**'s key interventions, adjuncts, and monitoring plan.
- **4 (Good):** High Alignment. Includes the Reference's primary interventions but misses minor supportive details.
- **3 (Fair):** Partial. Addresses diagnosis but deviates significantly from the Reference strategy.
- **2 (Poor):** Suboptimal. Misses key Reference interventions or uses weak alternatives.
- **1 (Wrong):** Contradicts the Reference Standard completely.
*Focus: Holistic Fit & Psychosocial Adaptation (Beyond the generic Reference).*
- **5 (Hyper-personalized):** Contextually brilliant. Adapts the Reference to specific lifestyle triggers (diet, work), behavioral strategies, and precise bio-adjustments.
- **4 (Context-Aware):** Good adaptation. Correct adjustments for renal/age/weight + relevant general advice.
- **3 (Generic):** Textbook Standard. Follows Reference but lacks specific patient tailoring (e.g., ignores occupation).
- **2 (Insensitive):** Generic template that clashes with patient reality (e.g., pill form for infant).
- **1 (Mismatch):** Ignores critical non-safety constraints.
1. **Calculation:** `base_score = (Effectiveness * 0.6 + Personalization * 0.4)`, then apply safety penalty deduction. Final score minimum is 1.0.
2. **Safety Penalty:** 5→0, 4→-0.5, 3→-1.0, 2→-2.0, 1→-4.0
3. **Format:** Output raw JSON only. Do NOT use markdown blocks.
{
  "safety": <int 1-5>,
  "effectiveness_alignment": <int 1-5>,
  "personalization": <int 1-5>,
  "reasoning": "<Concise analysis. 1.Safety: Did it violate the Contraindications list? 2.Effectiveness: How well did it match the Reference? 3.Personalization: Specific tailoring details.>"
}"""

TREATMENT_EVALUATION_USER_PROMPT = """## Patient Case

**Demographics:** {patient_name}, {patient_age}y, {patient_gender} | Occupation: {patient_occupation} | Marital: {patient_marital_status}

**Patient Profile:**
{patient_persona}

**Present Illness History:**
{present_illness_history}

**Medical History:**
{medical_history}

**Personal History:**
{personal_history}

**Family History:**
{family_history}

**Diagnostic Findings:**
{examination_results}

**CONTRAINDICATIONS (CRITICAL - Must Check):**
{contraindications}

---
{diagnosis}
{generated_treatment}
{reference_treatment}

---

Evaluate the Generated Treatment against the Patient Case and Reference Standard. Focus on: (1) Safety - Does it violate CONTRAINDICATIONS? (2) Effectiveness - Does it align with Reference? (3) Personalization - Is it tailored to patient specifics? Output JSON only."""


async def call_llm_for_evaluation(
    diagnosis,
    generated_treatment: str,
    reference_treatment: str,
    patient_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Call LLM API to evaluate treatment plan using AsyncModelRouter.

    Args:
        diagnosis: Diagnosis string or list of strings (for comorbidity)
        generated_treatment: Generated treatment plan
        reference_treatment: Reference treatment plan
        patient_info: Optional patient information
    """
    router = get_evaluation_router()
    if router is None:
        raise HTTPException(
            status_code=500,
            detail="Evaluation model not configured. Please check models_config.yaml"
        )
    diagnosis_str = diagnosis if isinstance(diagnosis, str) else ", ".join(diagnosis) if diagnosis else ""
    def _safe_get(d, key, default=""):
        if d is None:
            return default
        val = d.get(key, default)
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else default
        return str(val) if val else default
    def _format_examinations(exams: Optional[List[Dict]]) -> str:
        if not exams:
            return "No examination data available"
        return "\n".join([
            f"- {e.get('item_name', 'Unknown')}: {e.get('result', 'No result')}"
            for e in exams[:10]
        ])
    def _format_contraindications(patient_data: Optional[Dict]) -> str:
        if not patient_data:
            return "No contraindications information available"

        ground_truth = patient_data.get("ground_truth", {})
        contraindications = ground_truth.get("contraindications", {})

        if not contraindications:
            return "No specific contraindications documented"

        parts = []
        drugs = contraindications.get("drugs", [])
        treatments = contraindications.get("treatments", [])

        if drugs:
            if isinstance(drugs, list):
                parts.append(f"- Contraindicated Drugs: {', '.join(str(d) for d in drugs)}")
            else:
                parts.append(f"- Contraindicated Drugs: {drugs}")

        if treatments:
            if isinstance(treatments, list):
                parts.append(f"- Contraindicated Treatments: {', '.join(str(t) for t in treatments)}")
            else:
                parts.append(f"- Contraindicated Treatments: {treatments}")

        return "\n".join(parts) if parts else "No specific contraindications documented"
    def _format_history(history: Optional[Dict], default: str = "Not provided") -> str:
        if not history:
            return default
        return json.dumps(history, ensure_ascii=False, indent=2)
    user_prompt = TREATMENT_EVALUATION_USER_PROMPT.format(
        patient_name=_safe_get(patient_info.get("demographics", {}) if patient_info else {}, "name", "Unknown"),
        patient_age=_safe_get(patient_info.get("demographics", {}) if patient_info else {}, "age", "N/A"),
        patient_gender=_safe_get(patient_info.get("demographics", {}) if patient_info else {}, "gender", "N/A"),
        patient_occupation=_safe_get(patient_info.get("demographics", {}) if patient_info else {}, "occupation", "N/A"),
        patient_marital_status=_safe_get(patient_info.get("demographics", {}) if patient_info else {}, "marital_status", "N/A"),
        patient_persona=_safe_get(patient_info, "persona", "Not provided") if patient_info else "Not provided",
        present_illness_history=_format_history(patient_info.get("present_illness_history") if patient_info else None),
        medical_history=_format_history(patient_info.get("medical_history") if patient_info else None),
        personal_history=_format_history(patient_info.get("personal_history") if patient_info else None),
        family_history=_format_history(patient_info.get("family_history") if patient_info else None),
        examination_results=_format_examinations(patient_info.get("request_examinations") if patient_info else None),
        contraindications=_format_contraindications(patient_info),
        diagnosis=diagnosis_str or "Not specified",
        generated_treatment=generated_treatment or "No treatment plan provided",
        reference_treatment=reference_treatment or "No reference treatment available"
    )

    logger.info(f"Calling LLM for evaluation with diagnosis: {diagnosis_str[:100] if diagnosis_str else 'N/A'}...")
    logger.debug(f"User prompt length: {len(user_prompt)} chars")

    try:
        response_data = await router.chat(
            user_prompt=user_prompt,
            system_prompt=TREATMENT_EVALUATION_SYSTEM_PROMPT,
            timeout=60,
            temperature=0.1,
            max_tokens=1000
        )
        
        logger.info(f"Received response_data type: {type(response_data)}")
        response_list, token_usage = response_data
        
        logger.info(f"response_list: {response_list}, token_usage: {token_usage}")
        
        if not response_list:
            logger.error("Empty response_list from evaluation model")
            raise HTTPException(
                status_code=500,
                detail="Empty response from evaluation model. Please check model configuration and API key."
            )
        
        if not response_list[0]:
            logger.error(f"First element of response_list is empty: {response_list}")
            raise HTTPException(
                status_code=500,
                detail="Empty response content from evaluation model"
            )
        
        content = response_list[0]
        logger.debug(f"LLM response: {content}")
        json_match = re.search(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', content, re.DOTALL)
        if json_match:
            eval_result = json.loads(json_match.group())
            required_fields = ["safety", "effectiveness_alignment", "personalization"]
            for field in required_fields:
                if field in eval_result:
                    eval_result[field] = max(1.0, min(5.0, float(eval_result[field])))
            safety_penalty = {5: 0.0, 4: 0.5, 3: 1.0, 2: 2.0, 1: 4.0}
            safety_score = int(eval_result.get("safety", 1.0))
            penalty = safety_penalty.get(safety_score, 0.0)
            base_score = (
                eval_result.get("effectiveness_alignment", 1.0) * 0.6 +
                eval_result.get("personalization", 1.0) * 0.4
            )
            eval_result["overall_score"] = max(1.0, base_score - penalty)
            eval_result["safety_normalized"] = eval_result.get("safety", 1.0) / 5.0
            eval_result["effectiveness_alignment_normalized"] = eval_result.get("effectiveness_alignment", 1.0) / 5.0
            eval_result["personalization_normalized"] = eval_result.get("personalization", 1.0) / 5.0
            eval_result["overall_score_normalized"] = eval_result.get("overall_score", 1.0) / 5.0
            if token_usage:
                eval_result["token_usage"] = {
                    "prompt_tokens": token_usage.prompt_tokens,
                    "completion_tokens": token_usage.completion_tokens,
                    "total_tokens": token_usage.total_tokens
                }

            return eval_result
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse JSON from LLM response: {content[:200]}..."
            )
            
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON in LLM response: {e}"
        )
    except Exception as e:
        logger.error(f"Error calling evaluation model: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Evaluation model error: {str(e)}"
        )


@router.post("/evaluate-treatment", summary="评估治疗方案（LLM）")
async def evaluate_treatment_plan(request: TreatmentEvaluationRequest) -> TreatmentEvaluationResponse:
    """
    使用LLM评估单个治疗方案的质量。

    评估维度（Safety-Penalty Framework）：
    - Safety & Contraindications (安全性与禁忌症) - 扣分项：5→0, 4→-0.3, 3→-1.0, 2→-2.0, 1→-4.0
    - Effectiveness & Alignment (有效性与对齐) - Weight: 60%
    - Patient-Specific Personalization (个性化) - Weight: 40%

    计算公式：base_score = (Effectiveness * 0.6 + Personalization * 0.4) - safety_penalty

    使用 agentkernel 的 AsyncModelRouter 从 models_config.yaml 加载评估模型。
    """
    try:
        cache = get_evaluation_cache()
        cache_doctor_id = request.doctor_id or "API_AUTO_EVAL"
        eval_result = cache.get_evaluation(
            cache_doctor_id,
            request.patient_id,
            request.diagnosis,
            request.treatment_plan,
        )

        if not eval_result:
            eval_result = await call_llm_for_evaluation(
                diagnosis=request.diagnosis,
                generated_treatment=request.treatment_plan,
                reference_treatment=request.reference_treatment
            )
            cache.set_evaluation(
                cache_doctor_id,
                request.patient_id,
                request.diagnosis,
                request.treatment_plan,
                eval_result,
            )

        return TreatmentEvaluationResponse(
            patient_id=request.patient_id,
            clinical_appropriateness=eval_result.get("safety_normalized", 0.0),
            completeness=eval_result.get("effectiveness_alignment_normalized", 0.0),
            safety=eval_result.get("safety_normalized", 0.0),
            effectiveness_alignment=eval_result.get("effectiveness_alignment_normalized", 0.0),
            personalization=eval_result.get("personalization_normalized", 0.0),
            overall_score=eval_result.get("overall_score_normalized", 0.0),
            reasoning=eval_result.get("reasoning", ""),
            evaluation_method="llm"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during treatment evaluation: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation error: {str(e)}")


@router.get("/ground-truth", summary="获取Ground Truth数据")
async def get_ground_truth() -> Dict[str, Any]:
    """
    获取所有患者的 ground truth 数据。
    """
    ground_truth = load_ground_truth()
    if not ground_truth:
        raise HTTPException(status_code=404, detail="Ground truth data not found")
    return ground_truth


@router.get("/{doctor_id}/metrics", summary="获取医生实时指标")
async def get_doctor_metrics(doctor_id: str) -> Dict[str, Any]:
    """
    获取医生的实时累积指标。
    
    始终基于 get_doctor_evaluation 的全量数据进行计算，确保与 Clinical Evaluation 一致。
    """
    try:
        eval_data = await get_doctor_evaluation(doctor_id)
        summary = eval_data.get("summary", {})
        patients = eval_data.get("patients", [])
        diagnosis_history = []
        patient_count = 0        
        accuracy_sum = 0.0           
        examination_history = []
        exam_count = 0
        exam_precision_sum = 0.0
        treatment_history = []
        treat_count = 0
        treat_score_sum = 0.0
        treat_safety_sum = 0.0
        treat_effectiveness_sum = 0.0
        treat_personalization_sum = 0.0

        for p in patients:
            patient_id = p.get("patient_id")
            diag = p.get("diagnosis", {})
            if diag.get("available"):
                total_expected = diag.get("total_expected", 1)
                correct_count = diag.get("correct_count", 1 if diag.get("correct") else 0)
                patient_accuracy = correct_count / total_expected if total_expected > 0 else 0.0
                patient_count += 1
                accuracy_sum += patient_accuracy

                diagnosis_history.append({
                    "patient_count": patient_count,               
                    "accuracy": round(accuracy_sum / patient_count, 4) if patient_count > 0 else 0.0,
                    "tick": 0,          
                    "patient_id": patient_id,
                    "patient_accuracy": patient_accuracy,           
                    "correct_count": correct_count,
                    "total_expected": total_expected
                })
            exam_details = p.get("examinations", [])
            if exam_details:
                p_precision = p.get("examination_precision", 0.0)
                
                exam_count += 1
                exam_precision_sum += p_precision
                
                examination_history.append({
                    "patient_count": exam_count,
                    "precision": round(exam_precision_sum / exam_count, 4),
                    "tick": 0,
                    "patient_id": patient_id,
                    "current_precision": p_precision
                })
            
            treatment_data = p.get("treatment", {})
            eval_result = treatment_data.get("evaluation")
            
            if isinstance(eval_result, dict) and eval_result:
                safety_score, effectiveness_score, personalization_score, overall_score = _extract_normalized_eval_scores(eval_result)
                treat_count += 1
                current_score = overall_score
                treat_score_sum += overall_score
                treat_safety_sum += safety_score
                treat_effectiveness_sum += effectiveness_score
                treat_personalization_sum += personalization_score
                
                treatment_history.append({
                    "patient_count": treat_count,
                    "overall_score": round(treat_score_sum / treat_count, 4),
                    "safety": round(treat_safety_sum / treat_count, 4),
                    "effectiveness_alignment": round(treat_effectiveness_sum / treat_count, 4),
                    "personalization": round(treat_personalization_sum / treat_count, 4),
                    "tick": 0,
                    "patient_id": patient_id,
                    "current_score": current_score
                })

        return {
            "doctor_id": doctor_id,
            "diagnosis_total": patient_count,        
            "diagnosis_accuracy_sum": accuracy_sum,           
            "diagnosis_history": diagnosis_history,
            
            "examination_total": summary.get("total_examinations", 0),
            "examination_precision_sum": summary.get("average_examination_precision", 0.0) * summary.get("total_examinations", 0),
            "examination_history": examination_history,
            
            "treatment_total": treat_count,
            "treatment_score_sum": treat_score_sum,
            "treatment_safety_sum": treat_safety_sum,
            "treatment_effectiveness_sum": treat_effectiveness_sum,
            "treatment_personalization_sum": treat_personalization_sum,
            "treatment_history": treatment_history
        }
        
    except Exception as e:
        logger.error(f"Error generating metrics from evaluation: {e}")
        return {
            "doctor_id": doctor_id,
            "diagnosis_total": 0,
            "diagnosis_correct": 0,
            "diagnosis_history": [],
            "examination_total": 0,
            "examination_precision_sum": 0.0,
            "examination_history": [],
            "treatment_total": 0,
            "treatment_score_sum": 0.0,
            "treatment_safety_sum": 0.0,
            "treatment_effectiveness_sum": 0.0,
            "treatment_personalization_sum": 0.0,
            "treatment_history": []
        }


@router.get("/{doctor_id}/metrics/stats", summary="获取医生当前统计")
async def get_doctor_stats(doctor_id: str) -> Dict[str, Any]:
    """
    获取医生的当前统计数据（汇总）。

    返回:
    - 诊断准确率（总数、正确数、准确率）
    - 检查精确率（总数、平均精确率）
    - 治疗评分（总数、平均分、各子分数）
    """
    metrics_tracker = get_metrics_tracker()
    stats = metrics_tracker.get_doctor_stats(doctor_id)

    if not stats:
        try:
            eval_data = await get_doctor_evaluation(doctor_id)
            summary = eval_data.get("summary", {})
            return {
                "doctor_id": doctor_id,
                "diagnosis": {
                    "total": summary.get("total_diagnoses", 0),
                    "correct": summary.get("correct_diagnoses", 0),
                    "accuracy": summary.get("diagnosis_accuracy", 0.0)
                },
                "examination": {
                    "total": summary.get("total_examinations", 0),
                    "average_precision": summary.get("average_examination_precision", 0.0)
                },
                "treatment": {
                    "total": 0,
                    "average_score": 0.0,
                    "average_safety": 0.0,
                    "average_effectiveness": 0.0,
                    "average_personalization": 0.0
                }
            }
        except Exception:
            return {
                "doctor_id": doctor_id,
                "diagnosis": {
                    "total": 0,
                    "correct": 0,
                    "accuracy": 0.0
                },
                "examination": {
                    "total": 0,
                    "average_precision": 0.0
                },
                "treatment": {
                    "total": 0,
                    "average_score": 0.0,
                    "average_safety": 0.0,
                    "average_effectiveness": 0.0,
                    "average_personalization": 0.0
                }
            }

    return stats
