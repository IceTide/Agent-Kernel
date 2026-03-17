"""Patient API routes - using EventStore as data source."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..services import get_event_store

router = APIRouter(prefix="/api/patients", tags=["patients"])
EVENT_TO_PHASE = {
    "PATIENT_REGISTER": "registered",
    "PATIENT_MOVE": "waiting",
    "SEND_MESSAGE": "consulting",
    "SCHEDULE_EXAMINATION": "consulting",                       
    "DO_EXAMINATION": "examined",                    
    "PRESCRIBE_TREATMENT": "treated",                          
    "RECEIVE_TREATMENT": "treated",                    
    "IDLE": "idle",
    "unknown": "idle",
}
VALID_PHASES = {
    "idle",
    "home",                   
    "registered",          
    "consulting",          
    "examined",             
    "treated",              
    "finish",               
    "waiting",
    "examination",
    "awaiting_results",
    "treatment",
    "completed",
    "follow_up",
}


def normalize_phase(raw_phase: str) -> str:
    """将原始阶段值规范化为标准 PatientPhase。"""
    if not raw_phase:
        return "idle"
    if raw_phase in VALID_PHASES:
        return raw_phase
    normalized = EVENT_TO_PHASE.get(raw_phase, "idle")
    return normalized


def infer_patient_phase(patient_id: str, store) -> str:
    """
    根据患者的轨迹和消息历史推断当前阶段。

    推断逻辑（按优先级）：
    1. 如果有处方记录且已完成 -> finish (原 completed)
    2. 如果有处方记录（待处理）-> treated (原 treatment)
    3. 如果有检查记录且已完成 -> examined (原 awaiting_results)
    4. 如果有检查记录（待处理）-> consulting (患者在等待做检查或正在做检查)
    5. 如果有与医生的对话记录 -> consulting
    6. 如果已注册（有分配的医生）-> registered
    7. 否则 -> home (原 idle)
    """
    status = store.get_patient_status(patient_id)
    raw_phase = status.get("phase", "")
    if raw_phase in VALID_PHASES:
        return raw_phase
    prescriptions = store.get_prescriptions(patient_id)
    examinations = store.get_examinations(patient_id)
    messages = store.get_messages(patient_id)
    completed_prescriptions = [p for p in prescriptions if p.get("status") == "completed"]
    pending_prescriptions = [p for p in prescriptions if p.get("status") == "pending"]

    if completed_prescriptions:
        return "finish"             

    if pending_prescriptions:
        return "treated"                 
    completed_exams = [e for e in examinations if e.get("status") == "completed"]
    pending_exams = [e for e in examinations if e.get("status") == "pending"]

    if completed_exams and not pending_exams:
        return "examined"                 

    if pending_exams:
        return "consulting"                    
    has_messages = any(m.get("sender") == patient_id or m.get("receiver") == patient_id for m in messages)

    if has_messages:
        return "consulting"
    assigned_doctor = status.get("assigned_doctor", "")
    if assigned_doctor or status.get("event") == "PATIENT_REGISTER":
        return "registered"

    return "home"        


def get_patient_doctor_from_messages(patient_id: str, store) -> str:
    """从消息记录中获取患者的主要医生 ID。"""
    messages = store.get_messages(patient_id)
    doctor_counts = {}
    for msg in messages:
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")

        doctor_id = None
        if sender.startswith("Doctor_"):
            doctor_id = sender
        elif receiver.startswith("Doctor_"):
            doctor_id = receiver

        if doctor_id:
            doctor_counts[doctor_id] = doctor_counts.get(doctor_id, 0) + 1
    if doctor_counts:
        return max(doctor_counts, key=doctor_counts.get)

    return ""


def build_patient_summary(patient: dict, store) -> dict:
    """构建 PatientSummary 格式的响应。"""
    patient_id = patient.get("id", "")
    status = store.get_patient_status(patient_id)
    current_phase = infer_patient_phase(patient_id, store)
    demographics = patient.get("demographics", {})
    if not demographics:
        demographics = {"age": 0, "gender": "Male"}

    patient_name = demographics.get("name") or patient.get("name", patient_id)

    status_details = status.get("details", {}) if isinstance(status.get("details"), dict) else {}
    department = status.get("department") or status_details.get("department", "")
    assigned_doctor = status.get("assigned_doctor", "")
    if not assigned_doctor.startswith("Doctor_"):
        assigned_doctor = get_patient_doctor_from_messages(patient_id, store)

    return {
        "id": patient_id,
        "name": patient_name,
        "demographics": demographics,
        "current_phase": current_phase,
        "assigned_doctor": assigned_doctor,
        "department": department,
    }


def build_patient_detail(patient: dict, store) -> dict:
    """构建 PatientDetail 格式的响应。"""
    patient_id = patient.get("id", "")
    status = store.get_patient_status(patient_id)
    trajectory = store.get_patient_trajectory(patient_id)
    examinations = store.get_examinations(patient_id)
    prescriptions = store.get_prescriptions(patient_id)
    current_phase = infer_patient_phase(patient_id, store)
    demographics = patient.get("demographics", {})
    if not demographics:
        demographics = {"age": 0, "gender": "Male"}

    patient_name = demographics.get("name") or patient.get("name", patient_id)

    status_details = status.get("details", {}) if isinstance(status.get("details"), dict) else {}
    department = status.get("department") or status_details.get("department", "")
    assigned_doctor = status.get("assigned_doctor", "")
    if not assigned_doctor.startswith("Doctor_"):
        assigned_doctor = get_patient_doctor_from_messages(patient_id, store)
    formatted_trajectory = []
    for event in trajectory:
        formatted_trajectory.append(
            {
                "tick": event.get("tick", 0),
                "event_type": event.get("event") or event.get("name", ""),
                "agent_id": event.get("patient_id") or patient_id,
                "status": event.get("status", "success"),
                "payload": event.get("details", {}),
            }
        )
    present_illness_history = patient.get("present_illness_history", {})
    chief_complaint = (
        present_illness_history.get("chief_complaint") or
        patient.get("initial_complaint") or
        ""
    )

    return {
        "id": patient_id,
        "name": patient_name,
        "template": patient.get("template", "PatientAgent"),
        "initial_location": patient.get("initial_location", "community"),
        "demographics": demographics,
        "persona": patient.get("persona", ""),
        "initial_complaint": chief_complaint,
        "communication_style_label": patient.get("communication_style_label", ""),
        "appearance": patient.get("appearance", ""),
        "present_illness_history": present_illness_history,
        "medical_history": patient.get("medical_history", {}),
        "personal_history": patient.get("personal_history", {}),
        "family_history": patient.get("family_history", {}),
        "state": {
            "current_phase": current_phase,
            "assigned_doctor": assigned_doctor,
            "department": department,
            "consultation_room": status.get("consultation_room", ""),
            "current_location": status.get("location", ""),
            "treatment_result": status.get("treatment_result"),
        },
        "current_phase": current_phase,
        "assigned_doctor": assigned_doctor,
        "department": department,
        "consultation_room": status.get("consultation_room", ""),
        "current_location": status.get("location", ""),
        "examinations": examinations,
        "prescriptions": prescriptions,
        "trajectory": formatted_trajectory,
    }


@router.get("", summary="获取所有患者列表")
async def get_patients(
    phase: Optional[str] = Query(None, description="按状态过滤"),
    doctor_id: Optional[str] = Query(None, description="按医生ID过滤"),
) -> List[dict]:
    """
    获取所有患者的摘要信息 (PatientSummary[])。

    数据来源: EventStore (内存缓存或日志文件)
    使用批量优化方法，避免 O(n*m) 的查询复杂度。
    """
    store = get_event_store()
    patients = store.get_patients()
    all_summaries = store.get_all_patient_summaries()

    result = []
    for patient in patients:
        patient_id = patient.get("id", "")
        summary_data = all_summaries.get(patient_id, {})
        demographics = patient.get("demographics", {})
        if not demographics:
            demographics = {"age": 0, "gender": "Male"}

        patient_name = demographics.get("name") or patient.get("name", patient_id)

        current_phase = summary_data.get("phase", "home")
        assigned_doctor = summary_data.get("assigned_doctor", "")
        department = summary_data.get("department", "")
        if phase and current_phase != phase:
            continue
        if doctor_id and assigned_doctor != doctor_id:
            continue

        result.append({
            "id": patient_id,
            "name": patient_name,
            "demographics": demographics,
            "current_phase": current_phase,
            "assigned_doctor": assigned_doctor,
            "department": department,
        })

    return result


@router.get("/{patient_id}", summary="获取患者详情")
async def get_patient(patient_id: str) -> dict:
    """
    获取单个患者的完整详情 (PatientDetail)。

    前端使用这个接口获取患者详细信息。
    """
    store = get_event_store()
    patient = store.get_agent(patient_id)

    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    return build_patient_detail(patient, store)


@router.get("/{patient_id}/detail", summary="获取患者完整详情（别名）")
async def get_patient_detail(patient_id: str) -> dict:
    """获取单个患者的完整详情（与 /{patient_id} 相同）。"""
    return await get_patient(patient_id)


@router.get("/{patient_id}/trajectory", summary="获取患者轨迹")
async def get_patient_trajectory(patient_id: str) -> List[dict]:
    """
    获取患者的状态变化轨迹 (TrajectoryEvent[])。
    """
    store = get_event_store()
    patient = store.get_agent(patient_id)

    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    trajectory = store.get_patient_trajectory(patient_id)
    result = []
    for event in trajectory:
        result.append(
            {
                "tick": event.get("tick", 0),
                "event_type": event.get("event") or event.get("name", ""),
                "agent_id": event.get("patient_id") or patient_id,
                "status": event.get("status", "success"),
                "payload": event.get("details", {}),
            }
        )

    return result


@router.get("/{patient_id}/conversations", summary="获取患者对话")
async def get_patient_conversations(patient_id: str) -> List[dict]:
    """获取患者的所有对话。"""
    store = get_event_store()
    return store.get_messages(patient_id)


@router.get("/{patient_id}/examinations", summary="获取患者检查记录")
async def get_patient_examinations(patient_id: str) -> List[dict]:
    """获取患者的检查记录。"""
    store = get_event_store()
    return store.get_examinations(patient_id)


@router.get("/{patient_id}/prescriptions", summary="获取患者处方记录")
async def get_patient_prescriptions(patient_id: str) -> List[dict]:
    """获取患者的处方记录。"""
    store = get_event_store()
    return store.get_prescriptions(patient_id)
