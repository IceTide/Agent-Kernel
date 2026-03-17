"""
Examination Room Plugin for Hospital Simulation.
Stores patient examination items and results, provides report generation.
"""

from typing import Dict, Any, List, Optional

from agentkernel_distributed.mas.environment.base.plugin_base import GenericPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages.kv_adapters.redis import RedisKVAdapter

logger = get_logger(__name__)


class ExaminationRoomPlugin(GenericPlugin):
    """
    Examination Room component that stores patient examination data.

    Provides generate_report to return results for requested examination items.
    Data is read from Redis on-demand using patient-specific keys.
    Redis key format: "hospital:examination:{patient_id}"
    """

    COMPONENT_TYPE = "examination_room"
    REDIS_KEY_PREFIX = "hospital:examination:"

    def __init__(self, redis: RedisKVAdapter):
        """
        Initialize ExaminationRoom plugin.

        Args:
            redis: Redis KV adapter for data retrieval
        """
        super().__init__()
        self.redis = redis

    def _get_patient_redis_key(self, patient_id: str) -> str:
        """
        Get Redis key for a specific patient's examination data.

        Args:
            patient_id: Patient ID

        Returns:
            Redis key string
        """
        return f"{self.REDIS_KEY_PREFIX}{patient_id}"

    async def _get_patient_profile(self, patient_id: str) -> Dict[str, Any]:
        """Fetch patient profile from Redis."""
        try:
            if self.redis:
                profile = await self.redis.get(f"{patient_id}:profile")
                if profile and isinstance(profile, dict):
                    return profile
        except Exception as e:
            logger.warning(f"Failed to get profile for patient {patient_id}: {e}")
        return {}

    def _normalize_gender(self, profile: Dict[str, Any]) -> str:
        demographics = profile.get("demographics") or {}
        gender = str(demographics.get("gender", "")).strip().lower()
        if gender in ("male", "m", "man", "boy"):
            return "male"
        if gender in ("female", "f", "woman", "girl"):
            return "female"
        return "male"

    def _infer_age_group(self, profile: Dict[str, Any]) -> str:
        demographics = profile.get("demographics") or {}
        age = demographics.get("age")
        try:
            age_value = float(age)
        except (TypeError, ValueError):
            return "adult"
        if age_value < 2:
            return "infant"
        if age_value < 12:
            return "child"
        if age_value < 18:
            return "adolescent"
        if age_value < 65:
            return "adult"
        return "elderly"

    async def _get_normal_exam_result(self, patient_id: str, item_name: str) -> Optional[str]:
        """Get normal exam result based on patient age group and gender."""
        if not self.redis:
            return None
        profile = await self._get_patient_profile(patient_id)
        age_group = self._infer_age_group(profile)
        gender = self._normalize_gender(profile)
        redis_key = f"hospital:normal_examination:{age_group}:{gender}:{item_name}"
        try:
            return await self.redis.get(redis_key)
        except Exception as e:
            logger.warning(f"Failed to get normal exam {redis_key}: {e}")
            return None

    async def _get_patient_examination_data(self, patient_id: str) -> List[Dict[str, str]]:
        """
        Get examination data for a specific patient from Redis.

        Args:
            patient_id: Patient ID

        Returns:
            List of examination items for the patient
        """
        try:
            if self.redis:
                redis_key = self._get_patient_redis_key(patient_id)
                data = await self.redis.get(redis_key)
                if data and isinstance(data, list):
                    return data
                else:
                    logger.debug(f"No examination data found for patient {patient_id} in Redis")
                    return []
        except Exception as e:
            logger.error(f"Failed to get examination data for patient {patient_id} from Redis: {e}")
            return []

    async def init(self):
        """Initialize plugin."""
        try:
            if self.redis:
                is_connected = await self.redis.is_connected()
                if is_connected:
                    logger.info(f"ExaminationRoomPlugin initialized with Redis connection.")
                else:
                    logger.warning(f"ExaminationRoomPlugin initialized but Redis is not connected.")
        except Exception as e:
            logger.warning(f"ExaminationRoomPlugin initialized but failed to verify Redis: {e}")

    async def save_to_db(self):
        """Save patient examination data back to Redis."""
        logger.debug("save_to_db called - data already persisted in Redis")

    def _normalize_patient_id(self, patient_id: str) -> str:
        """Normalize patient ID format."""
        if patient_id.startswith("Patient_"):
            num = patient_id.replace("Patient_", "")
            return f"Patient_{num}"
        return patient_id

    async def generate_report(self, patient_id: str, requested_items: List[str]) -> Dict[str, Any]:
        """
        Generate examination report for requested items.
        Reads data from Redis for the specific patient.

        Args:
            patient_id: Patient ID (e.g., "Patient_001")
            requested_items: List of examination item names to retrieve

        Returns:
            Dictionary with item_name as key, containing result data
        """
        normalized_id = self._normalize_patient_id(patient_id)
        patient_exams = await self._get_patient_examination_data(normalized_id)
        exam_map = {exam["item_name"]: exam["result"] for exam in patient_exams}

        results = {}
        for item in requested_items:
            if item in exam_map:
                results[item] = {"item_name": item, "result": exam_map[item], "status": "completed"}
            else:
                normal_result = await self._get_normal_exam_result(normalized_id, item)
                results[item] = {
                    "item_name": item,
                    "result": (
                        normal_result if normal_result else f"{item}: Within normal limits. No abnormalities detected."
                    ),
                    "status": "normal",
                }

        logger.info(f"Generated report for {patient_id}: {len(results)} items")
        return results

    async def get_patient_exams(self, patient_id: str) -> List[Dict[str, str]]:
        """
        Get all available examination items for a patient.
        Reads data from Redis for the specific patient.

        Args:
            patient_id: Patient ID

        Returns:
            List of examination items with results
        """
        normalized_id = self._normalize_patient_id(patient_id)
        return await self._get_patient_examination_data(normalized_id)

    async def add_patient_exams(self, patient_id: str, exams: List[Dict[str, str]]) -> bool:
        """
        Add or update examination data for a patient in Redis.

        Args:
            patient_id: Patient ID
            exams: List of {"item_name": str, "result": str}

        Returns:
            True if successful
        """
        try:
            normalized_id = self._normalize_patient_id(patient_id)
            redis_key = self._get_patient_redis_key(normalized_id)
            await self.redis.set(redis_key, exams)

            logger.info(f"Added {len(exams)} exam items for patient {patient_id} to Redis")
            return True
        except Exception as e:
            logger.error(f"Failed to add patient exams: {e}")
            return False
