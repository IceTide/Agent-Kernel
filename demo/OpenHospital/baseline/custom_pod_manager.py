"""Example custom pod manager with convenience helpers."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable, List, Optional

import ray

from agentkernel_distributed.mas.pod import PodManagerImpl
from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)


@ray.remote
class CustomPodManager(PodManagerImpl):
    """Pod manager extension that exposes broadcast helpers for examples."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def step_agent(self):
        """Execute one tick with global tick recording at the beginning."""
        current_tick = None
        if self._system_handle:
            try:
                current_tick = await self._system_handle.run("timer", "get_tick")
            except Exception as e:
                logger.warning(f"Failed to get current tick: {e}")
        if current_tick is not None and self._adapters:
            try:
                redis_kv_adapter = self._adapters.get("RedisKVAdapter")
                if redis_kv_adapter:
                    await redis_kv_adapter.set("simulation:current_tick", current_tick)
                    logger.debug(f"Recorded global tick {current_tick} to Redis")
            except Exception as e:
                logger.warning(f"Failed to record global tick to Redis: {e}")
        await super().step_agent()

    async def inject_queue_manager_to_controllers(self, queue_manager: Any) -> None:
        """
        Inject queue manager Ray Actor into all pod controllers.

        Args:
            queue_manager: PatientQueueManager Ray Actor handle to inject
        """
        logger.info("Injecting queue manager Ray Actor into all pod controllers...")
        for pod_id, pod_handle in self._pod_id_to_pod.items():
            try:
                await pod_handle.forward.remote(
                    "set_queue_manager",
                    queue_manager
                )
                logger.info(f"Injected queue manager into pod {pod_id}")
            except Exception as e:
                logger.warning(f"Failed to inject queue manager into pod {pod_id}: {e}")
        logger.info("Queue manager Ray Actor injected successfully into all pods")
