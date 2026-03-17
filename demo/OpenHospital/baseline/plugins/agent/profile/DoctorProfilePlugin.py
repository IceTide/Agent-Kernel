"""
Doctor Profile Plugin for Hospital Simulation.
Manages doctor profile data without checkpoint/resume support.
"""

from typing import Dict, Any, Optional

from agentkernel_distributed.mas.agent.base.plugin_base import ProfilePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.toolkit.storages.vectordb_adapters.base import BaseVectorDBAdapter

logger = get_logger(__name__)


class DoctorProfilePlugin(ProfilePlugin):
    """
    Profile plugin specifically for doctor agents.
    Stores doctor profile data (name, department, specialties, etc.) in Redis.
    Does not require checkpoint/resume support as profile data is static.
    """

    def __init__(
        self,
        redis: RedisKVAdapter,
        milvus: Optional[BaseVectorDBAdapter] = None,
        profile_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.redis = redis
        self.milvus = milvus
        self._profile_data: Dict[str, Any] = profile_data if profile_data is not None else {}

    async def init(self):
        """Initialize plugin and persist profile to Redis."""
        self.agent_id = self._component.agent.agent_id
        if self._profile_data:
            await self.redis.set(f"{self.agent_id}:profile", self._profile_data)
            logger.debug(f"[{self.agent_id}] Initialized doctor profile: {self._profile_data.get('name', 'Unknown')}")

    async def execute(self, current_tick: int):
        """Profile data is static, no execution needed."""
        pass

    async def get_profile(self, key: str = None) -> Any:
        """
        Get profile field or entire profile dict if key is None.

        Args:
            key: Optional field name to retrieve

        Returns:
            Profile field value or entire profile dict
        """
        if key is None:
            return self._profile_data
        return self._profile_data.get(key)

    async def set_profile(self, key: str, value: Any):
        """
        Set a specific profile field.

        Args:
            key: Field name
            value: Field value
        """
        self._profile_data[key] = value
        await self.redis.set(f"{self.agent_id}:profile", self._profile_data, field=key)

    @property
    def profile_data(self) -> Dict[str, Any]:
        """Get entire profile data."""
        return self._profile_data

    @property
    def name(self) -> str:
        """Get doctor name."""
        return self._profile_data.get("name", "")

    @property
    def department(self) -> str:
        """Get doctor department."""
        return self._profile_data.get("department", "")

    @property
    def specialties(self) -> list:
        """Get doctor specialties."""
        return self._profile_data.get("specialties", [])
