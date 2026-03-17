"""Patient Queue Manager for batch loading patients to reduce resource usage."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from collections import deque

import ray
from pydantic import BaseModel

from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter

logger = get_logger(__name__)


@ray.remote
class PatientQueueManager:
    """Manages patient loading queue to limit concurrent active patients.

    This is a Ray Actor to ensure all controllers share the same queue state.
    Supports checkpoint/resume by persisting queue state to Redis.
    """
    REDIS_KEY_WAITING_QUEUE = "patient_queue:waiting"
    REDIS_KEY_ACTIVE_PATIENTS = "patient_queue:active"
    REDIS_KEY_FINISHED_PATIENTS = "patient_queue:finished"
    REDIS_KEY_METADATA = "patient_queue:metadata"

    def __init__(self, max_active_patients: int = 30, redis_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the patient queue manager.

        Args:
            max_active_patients: Maximum number of patients that can be active simultaneously
            redis_config: Optional Redis configuration dict for state persistence (for checkpoint/resume)
                         Should contain: host, port, db, and optionally other settings
        """
        self.max_active_patients = max_active_patients
        self._redis_config = redis_config
        self._redis_adapter: Optional[RedisKVAdapter] = None
        self._all_patient_configs: List[Dict[str, Any]] = []                             
        self._waiting_queue: deque = deque()                                                 
        self._active_patients: set = set()                                       
        self._finished_patients: set = set()                               
        self._total_patients = 0
        self._loaded_count = 0
        self._finished_count = 0

        logger.info(
            f"PatientQueueManager initialized with max_active_patients={max_active_patients}, "
            f"redis_enabled={redis_config is not None}"
        )

    async def _ensure_redis_connected(self) -> bool:
        """
        Ensure Redis adapter is connected. Creates connection if needed.

        Returns:
            True if Redis is available, False otherwise
        """
        if self._redis_adapter is not None:
            return True

        if self._redis_config is None:
            return False

        try:
            self._redis_adapter = RedisKVAdapter(
                host=self._redis_config.get("host", "localhost"),
                port=self._redis_config.get("port", 6379),
                db=self._redis_config.get("db", 0),
            )
            await self._redis_adapter.connect(config=self._redis_config)
            logger.info("PatientQueueManager: Redis adapter connected successfully")
            return True
        except Exception as e:
            logger.error(f"PatientQueueManager: Failed to connect Redis adapter: {e}", exc_info=True)
            self._redis_adapter = None
            return False

    async def initialize_queue(
        self, all_patient_configs: List[Dict[str, Any]], resume_mode: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Initialize the queue with all patient configurations.
        Returns the initial batch to load immediately.

        Args:
            all_patient_configs: List of all patient configurations
            resume_mode: If True, try to restore state from Redis

        Returns:
            List of patient configs to load initially (up to max_active_patients)
            Returns empty list if state was restored from Redis in resume mode
        """
        self._all_patient_configs = all_patient_configs
        self._total_patients = len(all_patient_configs)
        redis_available = await self._ensure_redis_connected()
        if resume_mode and redis_available:
            restored = await self._restore_from_redis()
            if restored:
                logger.info("Queue state restored from Redis checkpoint")
                return []                                                   
        initial_batch = all_patient_configs[:self.max_active_patients]
        waiting_patients = all_patient_configs[self.max_active_patients:]
        self._waiting_queue.extend(waiting_patients)
        for config in initial_batch:
            patient_id = config.get("id")
            if patient_id:
                self._active_patients.add(patient_id)

        self._loaded_count = len(initial_batch)

        logger.info(
            f"Queue initialized: {len(initial_batch)} patients loaded initially, "
            f"{len(waiting_patients)} patients waiting in queue"
        )
        if redis_available:
            await self._save_state_to_redis()

        return initial_batch

    async def mark_patient_finished(self, patient_id: str) -> None:
        """
        Mark a patient as finished and remove from active set.

        Args:
            patient_id: ID of the finished patient
        """
        if patient_id in self._active_patients:
            self._active_patients.remove(patient_id)
            self._finished_patients.add(patient_id)
            self._finished_count += 1
            logger.info(
                f"Patient {patient_id} marked as finished. "
                f"Active: {len(self._active_patients)}, "
                f"Finished: {self._finished_count}/{self._total_patients}"
            )
            redis_available = await self._ensure_redis_connected()
            if redis_available:
                await self._save_state_to_redis()
        else:
            logger.warning(f"Patient {patient_id} not found in active patients set")

    async def get_next_patient_config(self) -> Optional[Dict[str, Any]]:
        """
        Get the next patient configuration from the waiting queue.

        Returns:
            Patient config dict if available, None if queue is empty
        """
        if not self._waiting_queue:
            logger.info("Waiting queue is empty, no more patients to load")
            return None

        if len(self._active_patients) >= self.max_active_patients:
            logger.warning(
                f"Cannot load new patient: active patients ({len(self._active_patients)}) "
                f">= max ({self.max_active_patients})"
            )
            return None

        patient_config = self._waiting_queue.popleft()
        patient_id = patient_config.get("id")

        if patient_id:
            self._active_patients.add(patient_id)
            self._loaded_count += 1
            logger.info(
                f"Loading new patient {patient_id} from queue. "
                f"Active: {len(self._active_patients)}, "
                f"Loaded: {self._loaded_count}/{self._total_patients}, "
                f"Remaining in queue: {len(self._waiting_queue)}"
            )
            redis_available = await self._ensure_redis_connected()
            if redis_available:
                await self._save_state_to_redis()
        return patient_config

    def get_status(self) -> Dict[str, Any]:
        """
        Get current status of the patient queue.

        Returns:
            Dictionary with queue status information
        """
        return {
            "total_patients": self._total_patients,
            "active_patients": len(self._active_patients),
            "waiting_in_queue": len(self._waiting_queue),
            "loaded_count": self._loaded_count,
            "finished_count": self._finished_count,
            "max_active_patients": self.max_active_patients,
        }

    def is_queue_empty(self) -> bool:
        """Check if the waiting queue is empty."""
        return len(self._waiting_queue) == 0

    def has_capacity(self) -> bool:
        """Check if there is capacity to load more patients."""
        return len(self._active_patients) < self.max_active_patients

    def get_waiting_queue_length(self) -> int:
        """Get the number of patients waiting in queue."""
        return len(self._waiting_queue)

    def is_all_patients_finished(self) -> bool:
        """Check if all patients have finished their treatment.

        Returns:
            True if all patients are finished (no active and no waiting), False otherwise
        """
        return (
            self._total_patients > 0 and
            len(self._active_patients) == 0 and
            len(self._waiting_queue) == 0
        )

    async def _save_state_to_redis(self) -> None:
        """Save queue state to Redis for checkpoint/resume."""
        if not self._redis_adapter:
            return

        try:
            waiting_queue_serializable = []
            for config in self._waiting_queue:
                waiting_queue_serializable.append(self._serialize_config(config))
            waiting_queue_data = json.dumps(waiting_queue_serializable)
            await self._redis_adapter.set(self.REDIS_KEY_WAITING_QUEUE, waiting_queue_data)
            active_patients_data = json.dumps(list(self._active_patients))
            await self._redis_adapter.set(self.REDIS_KEY_ACTIVE_PATIENTS, active_patients_data)
            finished_patients_data = json.dumps(list(self._finished_patients))
            await self._redis_adapter.set(self.REDIS_KEY_FINISHED_PATIENTS, finished_patients_data)
            metadata = {
                "total_patients": self._total_patients,
                "loaded_count": self._loaded_count,
                "finished_count": self._finished_count,
                "max_active_patients": self.max_active_patients,
            }
            metadata_data = json.dumps(metadata)
            await self._redis_adapter.set(self.REDIS_KEY_METADATA, metadata_data)

            logger.debug("Queue state saved to Redis")
        except Exception as e:
            logger.error(f"Failed to save queue state to Redis: {e}", exc_info=True)

    async def _restore_from_redis(self) -> bool:
        """
        Restore queue state from Redis.

        Returns:
            True if state was successfully restored, False otherwise
        """
        if not self._redis_adapter:
            return False

        try:
            metadata_data = await self._redis_adapter.get(self.REDIS_KEY_METADATA)
            if not metadata_data:
                logger.info("No queue state found in Redis, starting fresh")
                return False

            metadata = json.loads(metadata_data)
            self._total_patients = metadata.get("total_patients", 0)
            self._loaded_count = metadata.get("loaded_count", 0)
            self._finished_count = metadata.get("finished_count", 0)
            finished_patients_data = await self._redis_adapter.get(self.REDIS_KEY_FINISHED_PATIENTS)
            if finished_patients_data:
                self._finished_patients = set(json.loads(finished_patients_data))
            active_patients_data = await self._redis_adapter.get(self.REDIS_KEY_ACTIVE_PATIENTS)
            if active_patients_data:
                self._active_patients = set(json.loads(active_patients_data))
            waiting_queue_data = await self._redis_adapter.get(self.REDIS_KEY_WAITING_QUEUE)
            if waiting_queue_data:
                waiting_queue_list = json.loads(waiting_queue_data)
                self._waiting_queue = deque(waiting_queue_list)

            logger.info(
                f"Queue state restored from Redis: "
                f"Active: {len(self._active_patients)}, "
                f"Waiting: {len(self._waiting_queue)}, "
                f"Finished: {self._finished_count}/{self._total_patients}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to restore queue state from Redis: {e}", exc_info=True)
            return False

    def get_active_patient_configs(self) -> List[Dict[str, Any]]:
        """
        Get configurations for currently active patients.

        Returns:
            List of configs for active patients
        """
        patient_config_map = {config.get("id"): config for config in self._all_patient_configs}
        active_configs = []
        for patient_id in self._active_patients:
            if patient_id in patient_config_map:
                active_configs.append(patient_config_map[patient_id])
            else:
                logger.warning(f"Active patient {patient_id} not found in stored patient configs")

        return active_configs

    async def clear_redis_state(self) -> None:
        """Clear queue state from Redis (useful for starting fresh)."""
        redis_available = await self._ensure_redis_connected()
        if not redis_available:
            return

        try:
            await self._redis_adapter.delete(self.REDIS_KEY_WAITING_QUEUE)
            await self._redis_adapter.delete(self.REDIS_KEY_ACTIVE_PATIENTS)
            await self._redis_adapter.delete(self.REDIS_KEY_FINISHED_PATIENTS)
            await self._redis_adapter.delete(self.REDIS_KEY_METADATA)
            logger.info("Queue state cleared from Redis")
        except Exception as e:
            logger.error(f"Failed to clear queue state from Redis: {e}", exc_info=True)

    def _serialize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serialize a patient config dict that may contain Pydantic objects.

        Args:
            config: Patient config dict with potential Pydantic objects

        Returns:
            JSON-serializable dict
        """
        result = {"id": config.get("id")}
        components = config.get("components", {})
        serialized_components = {}

        for comp_name, comp_config in components.items():
            if isinstance(comp_config, BaseModel):
                serialized_components[comp_name] = comp_config.model_dump()
            elif isinstance(comp_config, dict):
                serialized_comp = {}
                for key, value in comp_config.items():
                    if isinstance(value, BaseModel):
                        serialized_comp[key] = value.model_dump()
                    elif isinstance(value, dict):
                        nested = {}
                        for k, v in value.items():
                            if isinstance(v, BaseModel):
                                nested[k] = v.model_dump()
                            else:
                                nested[k] = v
                        serialized_comp[key] = nested
                    else:
                        serialized_comp[key] = value
                serialized_components[comp_name] = serialized_comp
            else:
                serialized_components[comp_name] = comp_config

        result["components"] = serialized_components
        if "component_order" in config:
            result["component_order"] = config["component_order"]

        return result
