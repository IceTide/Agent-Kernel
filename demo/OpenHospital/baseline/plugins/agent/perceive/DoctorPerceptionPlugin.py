"""
Doctor Perception Plugin for Hospital Simulation.
Handles message reception and conversation history for doctor agents.
"""

from typing import Dict, Any, List, Tuple, Optional
import heapq
import itertools

from agentkernel_distributed.types.schemas.message import Message
from agentkernel_distributed.mas.agent.base.plugin_base import PerceivePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter

logger = get_logger(__name__)


class DoctorPerceptionPlugin(PerceivePlugin):
    """
    Perception plugin for doctor agents.
    Manages message queue and conversation history with multiple patients.
    """

    def __init__(self, redis: RedisKVAdapter):
        super().__init__()
        self.redis = redis
        self.priority_queue: List[Tuple[float, int, int, Message]] = []
        self.counter = itertools.count()

    async def init(self):
        """Initialize perception plugin."""
        self.agent_id = self._component.agent.agent_id
        self.global_tick = 0
        self._patient_chat_history: Dict[str, List[Dict[str, Any]]] = {}
        self._doctor_consultation_history: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self._perception: Optional[Dict[str, Any]] = None
        await self.load_from_db()

    @property
    def perception(self) -> Optional[Dict[str, Any]]:
        """Get current perception data."""
        return self._perception

    async def execute(self, current_tick: int):
        """Execute perception logic each tick, get one message from queue."""
        if hasattr(self, 'global_tick') and self.global_tick == current_tick:
            logger.debug(f"[{self.agent_id}] Already executed in tick {current_tick}, skipping")
            return

        self.global_tick = current_tick
        message = self._get_one_message()

        self._perception = message if message else {"speaker": None, "content": None}
        await self.redis.set(f"{self.agent_id}:perception", self._perception)
        await self.save_to_db()

    async def add_message(self, message: Message):
        """Add a message to the queue and chat history."""
        if message.from_id != self.agent_id:
            count = next(self.counter)
            priority_class = 0 if message.from_id.startswith("Doctor_") else 1

            entry = (self.global_tick, priority_class, count, message)
            heapq.heappush(self.priority_queue, entry)
        if message.from_id.startswith("Doctor_") and message.from_id != self.agent_id:
            patient_id = None
            if message.extra and isinstance(message.extra, dict):
                if "metadata" in message.extra:
                    patient_id = message.extra["metadata"].get("patient_id")
                elif "patient_id" in message.extra:
                    patient_id = message.extra.get("patient_id")

            if patient_id:
                doctor_id = message.from_id
                if patient_id not in self._doctor_consultation_history:
                    self._doctor_consultation_history[patient_id] = {}
                if doctor_id not in self._doctor_consultation_history[patient_id]:
                    self._doctor_consultation_history[patient_id][doctor_id] = []
                self._doctor_consultation_history[patient_id][doctor_id].append({
                    "speaker": message.from_id,
                    "content": message.content
                })
                if len(self._doctor_consultation_history[patient_id][doctor_id]) > 20:
                    self._doctor_consultation_history[patient_id][doctor_id] = self._doctor_consultation_history[patient_id][doctor_id][-20:]
            else:
                logger.warning(
                    f"[{self.agent_id}] Doctor message from {message.from_id} missing patient_id in metadata"
                )
        else:
            patient_id = message.from_id if message.from_id != self.agent_id else message.to_id
            if patient_id not in self._patient_chat_history:
                self._patient_chat_history[patient_id] = []
            self._patient_chat_history[patient_id].append({
                "speaker": message.from_id,
                "content": message.content
            })
            if len(self._patient_chat_history[patient_id]) > 20:
                self._patient_chat_history[patient_id] = self._patient_chat_history[patient_id][-20:]

    def _get_one_message(self) -> Optional[Dict[str, Any]]:
        """Retrieve one message from the queue."""
        if not self.priority_queue:
            return None
        _, _, _, raw_message = heapq.heappop(self.priority_queue)
        if raw_message.from_id.startswith("Doctor"):
            logger.info(f"[{self.agent_id}] 🔍 DEBUG: Received message from {raw_message.from_id}")
            logger.info(f"  raw_message.extra type: {type(raw_message.extra)}")
            logger.info(f"  raw_message.extra content: {raw_message.extra}")
        metadata = {}
        if raw_message.extra and isinstance(raw_message.extra, dict):
            if "metadata" in raw_message.extra:
                metadata = raw_message.extra.get("metadata", {})
                logger.info(f"  ✅ Found metadata in extra['metadata']: {metadata}")
            elif "patient_id" in raw_message.extra:
                metadata["patient_id"] = raw_message.extra.get("patient_id")
                logger.info(f"  ✅ Found patient_id directly in extra: {raw_message.extra.get('patient_id')}")
            else:
                if raw_message.from_id.startswith("Doctor"):
                    logger.info(
                        f" ❌ raw_message.from_id: {raw_message.from_id}, raw_message.to_id: {raw_message.to_id}, raw_message.content: {raw_message.content}"
                    )
                    logger.warning(
                        f"  ❌ No metadata or patient_id found in extra! Keys: {list(raw_message.extra.keys())}"
                    )
        else:
            if raw_message.from_id.startswith("Doctor"):
                logger.warning(f"  ❌ extra is None or not a dict!")

        message_dict = {
            "speaker": raw_message.from_id,
            "content": raw_message.content,
            "metadata": metadata,                                                  
        }
        if raw_message.from_id.startswith("Doctor"):
            logger.info(
                f"[{self.agent_id}] 📤 Final message_dict metadata: {metadata}, has patient_id: {'patient_id' in metadata}"
            )

        return message_dict

    def get_patient_chat_history(self, patient_id: str, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent chat history with a specific patient (direct conversation only).

        Args:
            patient_id: The patient's agent ID
            count: Number of recent messages to retrieve

        Returns:
            List of recent messages with the patient
        """
        if patient_id not in self._patient_chat_history:
            return []
        return self._patient_chat_history[patient_id][-count:]

    def get_doctor_consultation_history(
        self, patient_id: str, doctor_id: Optional[str] = None, count: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent doctor consultation history about a specific patient.

        Args:
            patient_id: The patient's agent ID
            doctor_id: Optional doctor's agent ID. If provided, returns only messages from this doctor.
                      If None, returns all doctor consultation messages about this patient.
            count: Number of recent messages to retrieve

        Returns:
            List of recent doctor-to-doctor messages about the patient
        """
        if patient_id not in self._doctor_consultation_history:
            return []

        if doctor_id:
            if doctor_id not in self._doctor_consultation_history[patient_id]:
                return []
            return self._doctor_consultation_history[patient_id][doctor_id][-count:]
        else:
            all_messages = []
            for doc_id, messages in self._doctor_consultation_history[patient_id].items():
                all_messages.extend(messages)
            return all_messages[-count:]

    def get_consulting_doctors(self, patient_id: str) -> List[str]:
        """Get list of doctor IDs who have consulted about a specific patient.

        Args:
            patient_id: The patient's agent ID

        Returns:
            List of doctor IDs who have participated in consultations about this patient
        """
        if patient_id not in self._doctor_consultation_history:
            return []
        return list(self._doctor_consultation_history[patient_id].keys())

    def get_chat_history(self, patient_id: str, count: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """Get all chat history related to a specific patient (both direct chat and doctor consultations).

        Args:
            patient_id: The patient's agent ID
            count: Number of recent messages to retrieve for each type

        Returns:
            Dictionary with 'patient_chat' and 'doctor_consultation' keys
        """
        return {
            "patient_chat": self.get_patient_chat_history(patient_id, count),
            "doctor_consultation": self.get_doctor_consultation_history(patient_id, count),
        }

    def cleanup_patient_data(self, patient_id: str) -> None:
        """
        Clean up patient-related chat history from perception plugin.
        Called by reflect plugin after reflection is complete.

        Args:
            patient_id: Patient ID to clean up
        """
        if patient_id in self._patient_chat_history:
            del self._patient_chat_history[patient_id]
            logger.debug(f"[{self.agent_id}] Removed patient chat history with {patient_id}")
        if patient_id in self._doctor_consultation_history:
            del self._doctor_consultation_history[patient_id]
            logger.debug(f"[{self.agent_id}] Removed doctor consultation history for {patient_id}")

    def _get_temp_vars(self) -> Optional[Dict[str, Any]]:
        """Get temporary variables for checkpoint/resume."""
        serialized_queue = []
        for tick, priority_class, count, message in self.priority_queue:
            serialized_queue.append({
                "tick": tick,
                "priority_class": priority_class,
                "count": count,
                "message": message.model_dump() if hasattr(message, 'model_dump') else message
            })

        return {
            "priority_queue": serialized_queue,
            "patient_chat_history": self._patient_chat_history,
            "doctor_consultation_history": self._doctor_consultation_history,
            "perception": self._perception,
            "last_executed_tick": getattr(self, 'global_tick', -1),
        }

    def _set_temp_vars(self, vars_dict: Dict[str, Any]) -> None:
        """Restore temporary variables from checkpoint."""
        serialized_queue = vars_dict.get("priority_queue", [])
        self.priority_queue = []
        for item in serialized_queue:
            if isinstance(item, dict):
                message_data = item.get("message", {})
                message = Message(**message_data) if isinstance(message_data, dict) else message_data
                self.priority_queue.append((
                    item.get("tick", 0),
                    item.get("priority_class", 1),
                    item.get("count", 0),
                    message
                ))
            else:
                self.priority_queue.append(item)

        self._patient_chat_history = vars_dict.get("patient_chat_history", {})
        self._doctor_consultation_history = vars_dict.get("doctor_consultation_history", {})
        self._perception = vars_dict.get("perception")
        self.global_tick = vars_dict.get("last_executed_tick", -1)

    async def load_from_db(self) -> None:
        """Load temporary variables from Redis before execute()."""
        redis_key = f"{self.agent_id}:temp_vars:DoctorPerceptionPlugin"
        try:
            vars_dict = await self.redis.get(redis_key)
            if vars_dict:
                self._set_temp_vars(vars_dict)
                logger.debug(f"[{self.agent_id}] Loaded temp vars from Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to load temp vars from Redis: {e}")

    async def save_to_db(self) -> None:
        """Save temporary variables to Redis after execute()."""
        vars_dict = self._get_temp_vars()
        if vars_dict is None:
            return

        redis_key = f"{self.agent_id}:temp_vars:DoctorPerceptionPlugin"
        try:
            await self.redis.set(redis_key, vars_dict)
            logger.debug(f"[{self.agent_id}] Saved temp vars to Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to save temp vars to Redis: {e}")
