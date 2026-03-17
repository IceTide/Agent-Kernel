"""Custom controller for Hospital Simulation that publishes events via Redis."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import ray

from agentkernel_distributed.mas.controller.controller import ControllerImpl
from agentkernel_distributed.mas.interface.protocol import EventCategory, SimulationEvent
from agentkernel_distributed.toolkit.logger import get_logger

from baseline.utils.file_event_logger import file_event_logger

logger = get_logger(__name__)

REDIS_CHANNEL_PREFIX = "sim_events"


class CustomController(ControllerImpl):
    """Controller extension that provides event publishing for frontend communication."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._finished_agents: set = set()
        self._queue_manager: Optional[ray.actor.ActorHandle] = None

    @staticmethod
    def _is_patient_id(agent_id: str) -> bool:
        """Support both Patient_ and Patient- ID formats."""
        if not agent_id:
            return False
        return agent_id.startswith("Patient_") or agent_id.startswith("Patient-")

    async def step_agent(self) -> None:
        """
        Advance the agent manager by one tick, skipping finished agents.

        This optimizes resource usage by not running agents that have
        completed their workflow (current_phase == "finish").
        """
        if not self._agent_manager:
            raise RuntimeError("AgentManager is not initialized in the System.")

        current_tick = await self.run_system("timer", "get_tick")
        agents_to_run = []
        finished_patients_to_cleanup = []

        for agent_id, agent in self._agent_manager._agents.items():
            if agent_id in self._finished_agents:
                continue
            if self._is_patient_id(agent_id):
                try:
                    state_component = agent.get_component("state")
                    if state_component and state_component.has_plugin():
                        current_phase = await state_component.get_plugin().get_state("current_phase")
                        if current_phase == "finish":
                            self._finished_agents.add(agent_id)
                            finished_patients_to_cleanup.append(agent_id)
                            logger.info(f"[{agent_id}] Patient finished treatment, will cleanup data")
                            continue
                except Exception as e:
                    logger.warning(f"Error checking agent {agent_id} state: {e}")

            agents_to_run.append(agent)
        if agents_to_run:
            tasks = [agent.run(current_tick) for agent in agents_to_run]
            await asyncio.gather(*tasks)
        for patient_id in finished_patients_to_cleanup:
            await self._cleanup_patient_data(patient_id)
        if current_tick % 50 == 0:
            total = len(self._agent_manager._agents)
            finished = len(self._finished_agents)
            logger.info(f"[Tick {current_tick}] Active agents: {total - finished}/{total}, Finished: {finished}")

    async def _cleanup_patient_data(self, patient_id: str) -> None:
        """
        Remove finished patient agent from memory and clear Redis data.

        Args:
            patient_id: ID of the patient to remove
        """
        try:
            logger.info(f"[{patient_id}] Cleaning up patient data and removing from memory")
            success = await self.remove_agent(patient_id)
            if success:
                logger.info(f"[{patient_id}] ✓ Successfully removed patient agent from memory")
                if self._queue_manager:
                    await self._queue_manager.mark_patient_finished.remote(patient_id)
                    logger.info(f"[{patient_id}] Marked as finished in queue manager")
                    logger.info(f"[{patient_id}] Attempting to load next patient from queue...")
                    await self._load_next_patient_from_queue()
                else:
                    logger.warning(f"[{patient_id}] Queue manager not available, cannot load new patient")
            else:
                logger.warning(f"[{patient_id}] Failed to remove patient agent")

        except Exception as e:
            logger.error(f"[{patient_id}] Error removing patient agent: {e}", exc_info=True)

    async def _load_next_patient_from_queue(self) -> None:
        """
        Load the next patient from the waiting queue if available.
        """
        if not self._queue_manager:
            logger.warning("Queue manager not set, cannot load new patients")
            return
        has_capacity = await self._queue_manager.has_capacity.remote()
        if not has_capacity:
            logger.info("No capacity for new patients (max active patients reached)")
            return

        is_empty = await self._queue_manager.is_queue_empty.remote()
        if is_empty:
            status = await self._queue_manager.get_status.remote()
            logger.info(
                f"Patient queue is empty. "
                f"Finished: {status['finished_count']}/{status['total_patients']}"
            )
            return
        logger.info("Getting next patient config from queue...")
        patient_config = await self._queue_manager.get_next_patient_config.remote()
        if not patient_config:
            logger.warning("Failed to get next patient config from queue")
            return

        patient_id = patient_config.get("id")
        if not patient_id:
            logger.error("Patient config missing 'id' field")
            return

        try:
            profile_data = {}
            components = patient_config.get("components", {})
            if not components:
                logger.error(f"No components found in patient config for {patient_id}")
                return
            profile_component = components.get("profile") if isinstance(components, dict) else getattr(components, "profile", None)
            if not profile_component:
                logger.error(f"No profile component found for {patient_id}")
                return
            if isinstance(profile_component, dict):
                plugin_dict = profile_component.get("plugin", {})
            else:
                plugin_dict = getattr(profile_component, "plugin", {})

            if not plugin_dict:
                logger.error(f"No plugin found in profile component for {patient_id}")
                return
            if "PatientProfilePlugin" in plugin_dict:
                profile_plugin = plugin_dict["PatientProfilePlugin"]
                if isinstance(profile_plugin, dict):
                    if "profile_data" in profile_plugin:
                        profile_data = {"patient_profiles": profile_plugin["profile_data"]}
                else:
                    plugin_profile_data = getattr(profile_plugin, "profile_data", None)
                    if plugin_profile_data is not None:
                        profile_data = {"patient_profiles": plugin_profile_data}

                if profile_data:
                    pd = profile_data.get("patient_profiles", {})
                    keys = list(pd.keys()) if isinstance(pd, dict) else "non-dict"
                    logger.info(f"Extracted profile_data for {patient_id}: {keys}")
                else:
                    logger.warning(f"No profile_data found in PatientProfilePlugin for {patient_id}")
            else:
                logger.error(f"PatientProfilePlugin not found in plugin_dict for {patient_id}")

            if not profile_data:
                logger.error(f"Failed to extract profile_data for {patient_id}, cannot load patient")
                return
            if self._pod_manager:
                logger.info(f"Adding patient {patient_id} to pod manager with profile_data")
                success = await self._pod_manager.add_agent.remote(
                    patient_id,
                    "PatientAgent",                 
                    profile_data                                                
                )
                if success:
                    logger.info(f"✓ Successfully loaded new patient {patient_id} from queue")
                else:
                    logger.error(f"Failed to load patient {patient_id} from queue")
                    if self._queue_manager:
                        await self._queue_manager.mark_patient_finished.remote(patient_id)
            else:
                logger.error("PodManager not available, cannot load new patient")
        except Exception as e:
            logger.error(f"Error loading patient {patient_id} from queue: {e}", exc_info=True)
            if self._queue_manager:
                await self._queue_manager.mark_patient_finished(patient_id)

    def set_queue_manager(self, queue_manager: ray.actor.ActorHandle) -> None:
        """
        Set the patient queue manager Ray Actor for batch loading.

        Args:
            queue_manager: PatientQueueManager Ray Actor handle
        """
        self._queue_manager = queue_manager
        logger.info("Patient queue manager Ray Actor set in controller")

    async def publish_event(self, category: EventCategory, name: str, payload: Dict[str, Any]) -> None:
        """
        Publish a simulation event to the Redis pub/sub channel.

        Args:
            category: Event category used to build the channel name.
            name: Event name that further scopes the channel.
            payload: JSON-serializable event payload.
        """
        current_tick = await self.run_system("timer", "get_tick")
        event = SimulationEvent(category=category, name=name, payload=payload, tick=current_tick)
        await file_event_logger.log_event(event.model_dump())
        channel = f"{REDIS_CHANNEL_PREFIX}:{event.category.value}:{event.name}"
        message = event.model_dump_json()

        try:
            redis_kv_adapter = self._adapters.get("RedisKVAdapter")
            if not redis_kv_adapter:
                logger.warning("RedisKVAdapter not found in controller. Event will not be published.")
                return

            await redis_kv_adapter.publish_event(channel, message)
            logger.debug("Published event to channel '%s': %s", channel, message)
        except Exception as exc:
            logger.error("Failed to publish event: %s", exc, exc_info=True)
