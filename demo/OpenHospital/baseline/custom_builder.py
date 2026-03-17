"""Custom Builder with patient queue management support."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from agentkernel_distributed.mas.builder import Builder
from agentkernel_distributed.mas.system import System
from agentkernel_distributed.mas.pod import BasePodManager
from agentkernel_distributed.toolkit.logger import get_logger

from baseline.queue_manager import PatientQueueManager
from baseline.utils.ray_runtime import build_ray_runtime_env

logger = get_logger(__name__)


class CustomBuilder(Builder):
    """Builder extension that supports batch loading of patients."""

    def __init__(self, *args, resume_mode: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._queue_manager: Optional[PatientQueueManager] = None
        self._resume_mode = resume_mode
        logger.info(f"CustomBuilder initialized with resume_mode={resume_mode}")

    async def init(self) -> Tuple[Optional[BasePodManager], System]:
        """
        Override init to add queue manager initialization before pod manager.

        Returns:
            Tuple[Optional[BasePodManager], System]: A tuple containing the
            initialized PodManager actor handle and the System object.
        """
        import ray
        if not ray.is_initialized():
            ray.init(
                runtime_env=build_ray_runtime_env(self._project_path)
            )
        logger.info("Ray is initialized.")

        models_configs = self.config.models or []
        models_configs_dict = [m.model_dump() for m in models_configs]
        self._model_router_config = models_configs_dict
        logger.info("ModelRouter Actor and Proxy are created.")
        self._load_data_into_config()
        await self._init_queue_manager()
        await self._init_pod_manager()
        self._configure_recorder_for_resume()
        await self._init_system()
        await self.post_init()

        return self._pod_manager, self._system

    async def _init_queue_manager(self) -> None:
        """
        Initialize queue manager and determine which agents to load.

        This method:
        1. Uses already generated agent configs from self._config.agents
        2. Separates patients from other agents
        3. Initializes Redis adapter
        4. Creates queue manager Ray Actor with Redis adapter
        5. Determines which patient configs to load based on resume_mode
        6. Updates self._config.agents with the appropriate agent configs
        """
        logger.info("Initializing queue manager...")
        if not self._config.agents:
            logger.info("No agent configs found, skipping queue manager initialization")
            return

        all_agent_configs = self._config.agents
        patient_configs = []
        other_agent_configs = []

        for config in all_agent_configs:
            agent_id = config.get("id", "")
            if agent_id.startswith("Patient_"):
                patient_configs.append(config)
            else:
                other_agent_configs.append(config)

        logger.info(
            f"Found {len(patient_configs)} patients and {len(other_agent_configs)} other agents"
        )
        if not patient_configs:
            logger.info("No patients found, skipping queue manager initialization")
            return
        max_active_patients = getattr(self._config.simulation, 'max_active_patients', 30)
        redis_config = self._get_redis_config()
        if not redis_config:
            logger.warning("Redis config not available, queue manager will work without persistence")
        self._queue_manager = PatientQueueManager.options(
            name="patient_queue_manager",
            lifetime="detached"
        ).remote(
            max_active_patients=max_active_patients,
            redis_config=redis_config
        )
        logger.info("PatientQueueManager Ray Actor created")
        initial_patient_batch = await self._queue_manager.initialize_queue.remote(
            all_patient_configs=patient_configs,
            resume_mode=self._resume_mode
        )
        if self._resume_mode and not initial_patient_batch:
            active_patient_configs = await self._queue_manager.get_active_patient_configs.remote()
            self._config.agents = other_agent_configs + active_patient_configs
            logger.info(
                f"Resume mode: loaded {len(active_patient_configs)} active patients from checkpoint"
            )
        else:
            self._config.agents = other_agent_configs + initial_patient_batch
            waiting_queue_length = await self._queue_manager.get_waiting_queue_length.remote()
            logger.info(
                f"Fresh start: loaded {len(initial_patient_batch)} patients initially, "
                f"{waiting_queue_length} patients waiting in queue"
            )

    def _get_redis_config(self) -> Optional[Dict[str, Any]]:
        """
        Get Redis configuration from db_config.yaml.

        Returns:
            Redis config dict or None if not available
        """
        try:
            db_config_path = Path(self._project_path) / "configs" / "db_config.yaml"
            if not db_config_path.exists():
                logger.warning(f"Database config not found: {db_config_path}")
                return None

            with open(db_config_path, "r", encoding="utf-8") as f:
                db_config = yaml.safe_load(f)

            redis_pool_config = db_config.get("pools", {}).get("default_redis", {})
            redis_settings = redis_pool_config.get("settings", {})

            if not redis_settings:
                logger.warning("Redis settings not found in db_config.yaml")
                return None

            logger.info("Redis config loaded successfully")
            return redis_settings
        except Exception as e:
            logger.error(f"Failed to load Redis config: {e}", exc_info=True)
            return None

    async def _init_pod_manager(self) -> None:
        """
        Override to inject queue manager after pod manager initialization.
        """
        await super()._init_pod_manager()
        if self._queue_manager and self._pod_manager:
            logger.info("Injecting queue manager into all pod controllers...")
            try:
                await self._pod_manager.inject_queue_manager_to_controllers.remote(
                    self._queue_manager
                )
                logger.info("Queue manager injected successfully")
            except Exception as e:
                logger.error(f"Failed to inject queue manager: {e}", exc_info=True)

    def _configure_recorder_for_resume(self) -> None:
        """
        Configure recorder's clear_on_init based on resume_mode.

        If resume_mode is True, set clear_on_init to False (keep existing data).
        If resume_mode is False, set clear_on_init to True (clear database).
        """
        if not self.config.system or not self.config.system.components:
            logger.warning("System configuration not found, cannot configure recorder")
            return

        if "recorder" not in self.config.system.components:
            logger.warning("Recorder configuration not found in system components")
            return
        clear_on_init = not self._resume_mode
        self.config.system.components["recorder"]["clear_on_init"] = clear_on_init

        logger.info(
            f"Configured recorder: clear_on_init={clear_on_init} "
            f"(resume_mode={self._resume_mode})"
        )

    def get_queue_manager(self) -> Optional[PatientQueueManager]:
        """
        Get the queue manager instance.

        Returns:
            PatientQueueManager instance or None if not initialized
        """
        return self._queue_manager
