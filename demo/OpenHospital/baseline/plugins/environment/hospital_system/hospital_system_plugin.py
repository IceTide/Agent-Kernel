"""
Hospital Information System Plugin for Hospital Simulation.
Manages examination records, prescription records, and medical documentation.
Following the Baseline_instruction.md specification.

NOTE: This plugin is designed for distributed environments where doctors and patients
may run on different pods. All data operations read from and write to Redis directly
to ensure data consistency across pods.
"""

from typing import Dict, Any, List, Optional
import uuid
from enum import Enum

from agentkernel_distributed.mas.environment.base.plugin_base import GenericPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages.kv_adapters.redis import RedisKVAdapter

logger = get_logger(__name__)


class RecordStatus(str, Enum):
    """Status enum for medical records."""

    PENDING = "pending"             
    COMPLETED = "completed"              
    CANCELLED = "cancelled"       
REDIS_KEY_EXAMINATION = "his:exam:"
REDIS_KEY_PRESCRIPTION = "his:presc:"
REDIS_KEY_REGISTRATION = "his:reg:"
REDIS_KEY_EXAM_INDEX = "his:exam_index"                                     
REDIS_KEY_PRESC_INDEX = "his:presc_index"                                      
REDIS_KEY_PATIENT_EXAMS = "his:patient_exams:"                                 
REDIS_KEY_PATIENT_PRESCS = "his:patient_prescs:"                                  
REDIS_KEY_DOCTOR_PATIENTS = "his:doctor_patients:"                                   
REDIS_KEY_PATIENT_DOCTOR = "his:patient_doctor:"                           


class HospitalSystemPlugin(GenericPlugin):
    """
    Hospital Information System (HIS) plugin.

    Manages:
    1. Examination Registry - Records of ordered and completed examinations
    2. Prescription Registry - Records of prescribed treatments
    3. Patient registration and doctor assignment

    Acts as the central data store for hospital operations.
    
    IMPORTANT: All data is stored in Redis for distributed consistency.
    No in-memory caching is used to ensure all pods see the same data.
    """

    COMPONENT_TYPE = "hospital_system"

    def __init__(self, redis: RedisKVAdapter):
        """
        Initialize HIS plugin.

        Args:
            redis: Redis KV adapter for persistence
        """
        super().__init__()
        self.redis = redis

    async def init(self):
        """Initialize HIS plugin."""
        logger.info("HospitalSystemPlugin initialized (distributed mode - all data in Redis).")

    async def save_to_db(self):
        """No-op: All data is already in Redis."""
        pass

    async def add_examination(
        self,
        patient_id: str,
        doctor_id: str,
        current_tick: int,
        examination_items: List[str],
    ) -> str:
        """
        Create a new examination record (开具检查单).

        Triggered when doctor calls Schedule_examination action.

        Args:
            patient_id: Patient ID
            doctor_id: Doctor ID who ordered the examination
            current_tick: Current simulation tick
            examination_items: List of examination item names

        Returns:
            Generated record ID
        """
        record_id = f"EXAM_{str(uuid.uuid4())[:8]}"

        record = {
            "id": record_id,
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "created_tick": current_tick,
            "examination_items": examination_items,
            "status": RecordStatus.PENDING.value,
            "results": None,
            "completed_tick": None,
        }
        await self.redis.set(f"{REDIS_KEY_EXAMINATION}{record_id}", record)
        exam_index = await self.redis.get(REDIS_KEY_EXAM_INDEX) or []
        if record_id not in exam_index:
            exam_index.append(record_id)
            await self.redis.set(REDIS_KEY_EXAM_INDEX, exam_index)
        patient_exams = await self.redis.get(f"{REDIS_KEY_PATIENT_EXAMS}{patient_id}") or []
        if record_id not in patient_exams:
            patient_exams.append(record_id)
            await self.redis.set(f"{REDIS_KEY_PATIENT_EXAMS}{patient_id}", patient_exams)

        logger.info(f"Created examination record {record_id} for patient {patient_id}: {examination_items}")
        return record_id

    async def get_pending_examinations(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Get pending examination records for a patient (查询待办检查).

        Args:
            patient_id: Patient ID

        Returns:
            List of pending examination records
        """
        pending = []
        patient_exams = await self.redis.get(f"{REDIS_KEY_PATIENT_EXAMS}{patient_id}") or []
        
        for exam_id in patient_exams:
            record = await self.redis.get(f"{REDIS_KEY_EXAMINATION}{exam_id}")
            if record and record.get("status") == RecordStatus.PENDING.value:
                pending.append(record)
        
        logger.debug(f"Found {len(pending)} pending examinations for patient {patient_id}")
        return pending

    async def complete_examination(
        self,
        record_id: str,
        results: Dict[str, Any],
        completed_tick: int,
    ) -> bool:
        """
        Mark examination as completed with results (更新检查状态).

        Args:
            record_id: Examination record ID
            results: Examination results data
            completed_tick: Tick when completed

        Returns:
            True if successful
        """
        record = await self.redis.get(f"{REDIS_KEY_EXAMINATION}{record_id}")
        
        if not record:
            logger.warning(f"Examination record {record_id} not found")
            return False
        if record.get("status") != RecordStatus.PENDING.value:
            logger.warning(f"Cannot complete examination {record_id}: invalid status {record.get('status')}")
            return False

        record["status"] = RecordStatus.COMPLETED.value
        record["results"] = results
        record["completed_tick"] = completed_tick

        await self.redis.set(f"{REDIS_KEY_EXAMINATION}{record_id}", record)
        logger.info(f"Examination {record_id} completed")
        return True

    async def get_examination_results(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Get completed examination results for a patient.

        Args:
            patient_id: Patient ID

        Returns:
            List of completed examination records with results
        """
        completed = []
        redis_key = f"{REDIS_KEY_PATIENT_EXAMS}{patient_id}"
        patient_exams = await self.redis.get(redis_key) or []
        logger.debug(f"DEBUG: get_examination_results for {patient_id}. Key: {redis_key}. Found exams: {patient_exams}")

        for exam_id in patient_exams:
            record = await self.redis.get(f"{REDIS_KEY_EXAMINATION}{exam_id}")
            if record:
                status = record.get("status")
                logger.debug(f"DEBUG: Exam {exam_id} status: {status}")
                if status == RecordStatus.COMPLETED.value:
                    completed.append(record)
            else:
                logger.warning(f"DEBUG: Exam {exam_id} found in index but record missing from Redis")
        
        logger.info(f"DEBUG: Returning {len(completed)} completed exams for {patient_id}")
        return completed

    async def add_prescription(
        self,
        patient_id: str,
        doctor_id: str,
        current_tick: int,
        treatment_content: str,
    ) -> str:
        """
        Create a new prescription record (开具处方单).

        Triggered when doctor calls Prescribe_treatment action.

        Args:
            patient_id: Patient ID
            doctor_id: Doctor ID who prescribed
            current_tick: Current simulation tick
            treatment_content: Treatment description/plan
        Returns:
            Generated record ID
        """
        record_id = f"PRESC_{str(uuid.uuid4())[:8]}"

        record = {
            "id": record_id,
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "created_tick": current_tick,
            "treatment_content": treatment_content,
            "status": RecordStatus.PENDING.value,
            "completed_tick": None,
        }
        await self.redis.set(f"{REDIS_KEY_PRESCRIPTION}{record_id}", record)
        presc_index = await self.redis.get(REDIS_KEY_PRESC_INDEX) or []
        if record_id not in presc_index:
            presc_index.append(record_id)
            await self.redis.set(REDIS_KEY_PRESC_INDEX, presc_index)
        patient_prescs = await self.redis.get(f"{REDIS_KEY_PATIENT_PRESCS}{patient_id}") or []
        if record_id not in patient_prescs:
            patient_prescs.append(record_id)
            await self.redis.set(f"{REDIS_KEY_PATIENT_PRESCS}{patient_id}", patient_prescs)

        logger.info(f"Created prescription {record_id} for patient {patient_id}: {treatment_content}")
        return record_id

    async def get_pending_prescription(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Get pending prescription record for a patient (查询待取药).

        Args:
            patient_id: Patient ID

        Returns:
            Pending prescription record or None if not found
        """
        patient_prescs = await self.redis.get(f"{REDIS_KEY_PATIENT_PRESCS}{patient_id}") or []
        
        for presc_id in patient_prescs:
            record = await self.redis.get(f"{REDIS_KEY_PRESCRIPTION}{presc_id}")
            if record and record.get("status") == RecordStatus.PENDING.value:
                return record
        
        return None

    async def complete_prescription(
        self,
        record_id: str,
        completed_tick: int,
    ) -> bool:
        """
        Mark prescription as completed (更新处方状态 - 已取药).

        Args:
            record_id: Prescription record ID
            completed_tick: Tick when completed

        Returns:
            True if successful
        """
        record = await self.redis.get(f"{REDIS_KEY_PRESCRIPTION}{record_id}")
        
        if not record:
            logger.warning(f"Prescription record {record_id} not found")
            return False

        if record.get("status") != RecordStatus.PENDING.value:
            logger.warning(f"Cannot complete prescription {record_id}: invalid status")
            return False

        record["status"] = RecordStatus.COMPLETED.value
        record["completed_tick"] = completed_tick

        await self.redis.set(f"{REDIS_KEY_PRESCRIPTION}{record_id}", record)
        logger.info(f"Prescription {record_id} completed (medication dispensed)")
        return True

    async def get_patient_history(self, patient_id: str) -> Dict[str, Any]:
        """
        Get all medical records for a patient (获取患者病历/历史).

        Args:
            patient_id: Patient ID

        Returns:
            Dictionary containing examination and prescription history
        """
        examinations = []
        patient_exams = await self.redis.get(f"{REDIS_KEY_PATIENT_EXAMS}{patient_id}") or []
        for exam_id in patient_exams:
            record = await self.redis.get(f"{REDIS_KEY_EXAMINATION}{exam_id}")
            if record:
                examinations.append(record)
        prescriptions = []
        patient_prescs = await self.redis.get(f"{REDIS_KEY_PATIENT_PRESCS}{patient_id}") or []
        for presc_id in patient_prescs:
            record = await self.redis.get(f"{REDIS_KEY_PRESCRIPTION}{presc_id}")
            if record:
                prescriptions.append(record)
        examinations.sort(key=lambda x: x.get("created_tick", 0), reverse=True)
        prescriptions.sort(key=lambda x: x.get("created_tick", 0), reverse=True)

        return {
            "patient_id": patient_id,
            "examinations": examinations,
            "prescriptions": prescriptions,
            "total_examinations": len(examinations),
            "total_prescriptions": len(prescriptions),
        }

    async def query_by_tick(self, start_tick: int, end_tick: int = None) -> Dict[str, Any]:
        """
        Query records by tick range (按日期查询记录).

        Args:
            start_tick: Start tick
            end_tick: End tick (defaults to start_tick)

        Returns:
            Records created in the tick range
        """
        if end_tick is None:
            end_tick = start_tick

        examinations = []
        prescriptions = []
        exam_index = await self.redis.get(REDIS_KEY_EXAM_INDEX) or []
        for exam_id in exam_index:
            record = await self.redis.get(f"{REDIS_KEY_EXAMINATION}{exam_id}")
            if record:
                tick = record.get("created_tick", 0)
                if start_tick <= tick <= end_tick:
                    examinations.append(record)
        presc_index = await self.redis.get(REDIS_KEY_PRESC_INDEX) or []
        for presc_id in presc_index:
            record = await self.redis.get(f"{REDIS_KEY_PRESCRIPTION}{presc_id}")
            if record:
                tick = record.get("created_tick", 0)
                if start_tick <= tick <= end_tick:
                    prescriptions.append(record)

        return {
            "tick_range": [start_tick, end_tick],
            "examinations": examinations,
            "prescriptions": prescriptions,
        }

    async def register_patient(
        self,
        patient_id: str,
        department: str,
        doctor_id: str,
        current_tick: int,
    ) -> str:
        """
        Register a patient and bind to a doctor.

        Args:
            patient_id: Patient ID
            department: Target department
            doctor_id: Assigned doctor ID
            current_tick: Current simulation tick

        Returns:
            Registration ID
        """
        registration_id = f"REG_{str(uuid.uuid4())[:8]}"

        registration = {
            "id": registration_id,
            "patient_id": patient_id,
            "department": department,
            "doctor_id": doctor_id,
            "registered_tick": current_tick,
            "status": "active",
        }
        await self.redis.set(f"{REDIS_KEY_REGISTRATION}{patient_id}", registration)
        doctor_patients = await self.redis.get(f"{REDIS_KEY_DOCTOR_PATIENTS}{doctor_id}") or []
        if patient_id not in doctor_patients:
            doctor_patients.append(patient_id)
            await self.redis.set(f"{REDIS_KEY_DOCTOR_PATIENTS}{doctor_id}", doctor_patients)
        await self.redis.set(f"{REDIS_KEY_PATIENT_DOCTOR}{patient_id}", doctor_id)

        logger.info(f"Patient {patient_id} registered to Dr. {doctor_id} in {department}")
        return registration_id

    async def get_patient_registration(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get patient's registration information."""
        return await self.redis.get(f"{REDIS_KEY_REGISTRATION}{patient_id}")

    async def get_assigned_doctor(self, patient_id: str) -> Optional[str]:
        """Get the doctor assigned to a patient."""
        return await self.redis.get(f"{REDIS_KEY_PATIENT_DOCTOR}{patient_id}")

    async def get_doctor_patients(self, doctor_id: str) -> List[str]:
        """Get list of patients assigned to a doctor."""
        return await self.redis.get(f"{REDIS_KEY_DOCTOR_PATIENTS}{doctor_id}") or []

    async def get_doctors_by_department(self, department: str) -> List[str]:
        """
        Get list of doctor IDs in a department.

        Args:
            department: Department name

        Returns:
            List of doctor IDs
        """
        return []

    async def delete_examination_record(self, record_id: str) -> bool:
        """Delete an examination record."""
        record = await self.redis.get(f"{REDIS_KEY_EXAMINATION}{record_id}")
        if not record:
            return False
        
        patient_id = record.get("patient_id")
        await self.redis.delete(f"{REDIS_KEY_EXAMINATION}{record_id}")
        exam_index = await self.redis.get(REDIS_KEY_EXAM_INDEX) or []
        if record_id in exam_index:
            exam_index.remove(record_id)
            await self.redis.set(REDIS_KEY_EXAM_INDEX, exam_index)
        if patient_id:
            patient_exams = await self.redis.get(f"{REDIS_KEY_PATIENT_EXAMS}{patient_id}") or []
            if record_id in patient_exams:
                patient_exams.remove(record_id)
                await self.redis.set(f"{REDIS_KEY_PATIENT_EXAMS}{patient_id}", patient_exams)
        
        logger.info(f"Deleted examination record {record_id}")
        return True

    async def delete_prescription_record(self, record_id: str) -> bool:
        """Delete a prescription record."""
        record = await self.redis.get(f"{REDIS_KEY_PRESCRIPTION}{record_id}")
        if not record:
            return False
        
        patient_id = record.get("patient_id")
        await self.redis.delete(f"{REDIS_KEY_PRESCRIPTION}{record_id}")
        presc_index = await self.redis.get(REDIS_KEY_PRESC_INDEX) or []
        if record_id in presc_index:
            presc_index.remove(record_id)
            await self.redis.set(REDIS_KEY_PRESC_INDEX, presc_index)
        if patient_id:
            patient_prescs = await self.redis.get(f"{REDIS_KEY_PATIENT_PRESCS}{patient_id}") or []
            if record_id in patient_prescs:
                patient_prescs.remove(record_id)
                await self.redis.set(f"{REDIS_KEY_PATIENT_PRESCS}{patient_id}", patient_prescs)
        
        logger.info(f"Deleted prescription record {record_id}")
        return True
