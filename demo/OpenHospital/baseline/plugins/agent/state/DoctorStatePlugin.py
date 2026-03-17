"""
Doctor State Plugin for Hospital Simulation.
Manages doctor runtime state with Redis persistence and checkpoint/resume support.
"""

from typing import Dict, Any, Optional

from agentkernel_distributed.mas.agent.base.plugin_base import StatePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter

logger = get_logger(__name__)


class DoctorStatePlugin(StatePlugin):
    """
    State plugin specifically for doctor agents.
    Tracks doctor workflow state and supports checkpoint/resume.
    """

    def __init__(self, redis: RedisKVAdapter, state_data: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.redis = redis
        self._state_data: Dict[str, Any] = state_data if state_data is not None else {}
        self.global_tick = 0

    async def init(self):
        """Initialize plugin and load state from Redis for checkpoint/resume."""
        self.agent_id = self._component.agent.agent_id
        await self.load_from_db()
        if not self._state_data and self._state_data is not None:
            await self.redis.set(f"{self.agent_id}:state", self._state_data)

    async def execute(self, current_tick: int):
        """Persist state data to Redis each tick."""
        if hasattr(self, 'global_tick') and self.global_tick == current_tick:
            logger.debug(f"[{self.agent_id}] Already executed in tick {current_tick}, skipping")
            return

        self.global_tick = current_tick
        await self._persist_state()
        await self.save_to_db()

    async def set_state(self, key: str, value: Any):
        """Set a specific state field."""
        self._state_data[key] = value
        await self.redis.set(f"{self.agent_id}:state", self._state_data, field=key)

    async def get_state(self, key: str = None) -> Any:
        """Get state field or entire state dict if key is None."""
        if key is None:
            return self._state_data
        return self._state_data.get(key)

    async def _persist_state(self):
        """Persist current state to Redis."""
        if self.redis:
            await self.redis.set(f"{self.agent_id}:state", self._state_data)

    def _get_temp_vars(self) -> Optional[Dict[str, Any]]:
        """Get temporary variables for checkpoint/resume."""
        return {
            "state_data": self._state_data,
            "last_executed_tick": getattr(self, 'global_tick', -1),
        }

    def _set_temp_vars(self, vars_dict: Dict[str, Any]) -> None:
        """Restore temporary variables from checkpoint."""
        self._state_data = vars_dict.get("state_data", {})
        self.global_tick = vars_dict.get("last_executed_tick", -1)

    async def load_from_db(self) -> None:
        """Load temporary variables from Redis before execute()."""
        redis_key = f"{self.agent_id}:temp_vars:DoctorStatePlugin"
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

        redis_key = f"{self.agent_id}:temp_vars:DoctorStatePlugin"
        try:
            await self.redis.set(redis_key, vars_dict)
            logger.debug(f"[{self.agent_id}] Saved temp vars to Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to save temp vars to Redis: {e}")
