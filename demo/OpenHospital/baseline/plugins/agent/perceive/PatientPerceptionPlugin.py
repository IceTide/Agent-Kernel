"""
Patient Perception Plugin for Hospital Simulation.
Handles message reception and conversation history for patient agents.
"""

from typing import Dict, Any, List, Tuple, Optional
import heapq
import itertools

from agentkernel_distributed.types.schemas.message import Message
from agentkernel_distributed.mas.agent.base.plugin_base import PerceivePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter

logger = get_logger(__name__)


class PatientPerceptionPlugin(PerceivePlugin):
    """
    Perception plugin for patient agents.
    Manages message queue and conversation history.
    """

    def __init__(self, redis: RedisKVAdapter):
        super().__init__()
        self.redis = redis
        self.priority_queue: List[Tuple[float, int, Message]] = []
        self.counter = itertools.count()

    async def init(self):
        """Initialize perception plugin."""
        self.agent_id = self._component.agent.agent_id
        self.global_tick = 0
        self._chat_history: List[Dict[str, Any]] = []
        self._perception: Optional[Dict[str, Any]] = None
        await self.load_from_db()

    @property
    def perception(self) -> Optional[Dict[str, Any]]:
        """Get current perception data."""
        return self._perception

    async def execute(self, current_tick: int):
        """Execute perception logic each tick, get one message from queue."""
        if hasattr(self, "global_tick") and self.global_tick == current_tick:
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
            entry = (self.global_tick, count, message)
            heapq.heappush(self.priority_queue, entry)
        message_tick = message.created_at if isinstance(message.created_at, (int, float)) else self.global_tick
        self._chat_history.append({
            "speaker": message.from_id,
            "content": message.content,
            "tick": int(message_tick),
        })
        if len(self._chat_history) > 20:
            self._chat_history = self._chat_history[-20:]

    def _get_one_message(self) -> Optional[Dict[str, Any]]:
        """Retrieve one message from the queue."""
        if not self.priority_queue:
            return None
        _, _, raw_message = heapq.heappop(self.priority_queue)
        return {
            "speaker": raw_message.from_id,
            "content": raw_message.content,
        }

    def get_chat_history(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent chat history.

        Args:
            count: Number of recent messages to retrieve

        Returns:
            List of recent messages
        """
        return self._chat_history[-count:]

    def _get_temp_vars(self) -> Optional[Dict[str, Any]]:
        """Get temporary variables for checkpoint/resume."""
        serialized_queue = []
        for tick, count, message in self.priority_queue:
            serialized_queue.append(
                {
                    "tick": tick,
                    "count": count,
                    "message": message.model_dump() if hasattr(message, "model_dump") else message,
                }
            )

        return {
            "priority_queue": serialized_queue,
            "chat_history": self._chat_history,
            "perception": self._perception,
            "last_executed_tick": getattr(self, "global_tick", -1),
        }

    def _set_temp_vars(self, vars_dict: Dict[str, Any]) -> None:
        """Restore temporary variables from checkpoint."""
        serialized_queue = vars_dict.get("priority_queue", [])
        self.priority_queue = []
        for item in serialized_queue:
            if isinstance(item, dict):
                message_data = item.get("message", {})
                message = Message(**message_data) if isinstance(message_data, dict) else message_data
                self.priority_queue.append((item.get("tick", 0), item.get("count", 0), message))
            else:
                self.priority_queue.append(item)

        self._chat_history = vars_dict.get("chat_history", [])
        self._perception = vars_dict.get("perception")
        self.global_tick = vars_dict.get("last_executed_tick", -1)

    async def load_from_db(self) -> None:
        """Load temporary variables from Redis before execute()."""
        redis_key = f"{self.agent_id}:temp_vars:PatientPerceptionPlugin"
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

        redis_key = f"{self.agent_id}:temp_vars:PatientPerceptionPlugin"
        try:
            await self.redis.set(redis_key, vars_dict)
            logger.debug(f"[{self.agent_id}] Saved temp vars to Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to save temp vars to Redis: {e}")

    async def clear(self) -> None:
        """Clear all Redis data for this patient when being cleaned up."""
        try:
            await self.redis.delete(f"{self.agent_id}:perception")
            await self.redis.delete(f"{self.agent_id}:temp_vars:PatientPerceptionPlugin")
            logger.info(f"[{self.agent_id}] Cleared PatientPerceptionPlugin Redis data")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to clear PatientPerceptionPlugin Redis data: {e}")
