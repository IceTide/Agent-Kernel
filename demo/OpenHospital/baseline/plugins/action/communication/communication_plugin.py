"""
Communication Plugin for Hospital Simulation.
Handles messaging between patients and doctors following Baseline_instruction.md.
"""

import json
import inspect
from typing import List, Dict, Any

from agentkernel_distributed.mas.action.base.plugin_base import CommunicationPlugin
from agentkernel_distributed.types.schemas.message import Message, MessageKind
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.types.schemas.action import ActionResult
from agentkernel_distributed.toolkit.storages.kv_adapters import RedisKVAdapter
from agentkernel_distributed.mas.interface.protocol import EventCategory

from baseline.utils.annotation import AgentCall

logger = get_logger(__name__)


class HospitalCommunicationPlugin(CommunicationPlugin):
    """
    Communication plugin for hospital agent interactions.

    Following Baseline_instruction.md specification:
    - send_message: Universal message sending for both doctors and patients
    """

    def __init__(self, redis: RedisKVAdapter):
        """
        Initialize communication plugin with Redis adapter.

        Args:
            redis: Redis KV adapter for persistence
        """
        super().__init__()
        self.redis = redis

    async def init(self, model_router: Any, controller: Any):
        """Initialize with model router and controller."""
        self.model = model_router
        self.controller = controller

    async def prepare(self, annotation_type: str) -> List[Dict[str, Any]]:
        """Build list of annotated methods with metadata."""
        methods: List[Dict[str, Any]] = []
        for method_name in dir(self):
            method = getattr(self, method_name)
            is_annotated = callable(method) and getattr(method, "_annotation", None) == annotation_type
            if not is_annotated:
                continue

            description = inspect.getdoc(method) or ""
            metadata = getattr(method, "_metadata", None)

            method_info = {
                "name": method_name,
                "description": description.strip(),
                "metadata": metadata.to_dict() if metadata else None,
            }
            methods.append(method_info)

        return methods

    async def _log_action(self, agent_id: str, action: str, status: str, extra: Dict = None):
        """Log an action for trajectory recording and publish to frontend."""
        current_tick = await self.controller.run_system("timer", "get_tick")

        action_log = {
            "tick": current_tick,
            "event_type": action.upper(),
            "agent_id": agent_id,
            "status": status,
            "payload": extra or {},
        }

        logger.debug(f"[{agent_id}] Action Log: {json.dumps(action_log)}")
        try:
            await self.controller.run_system(
                "recorder",
                "record_event",
                tick=current_tick,
                event_type=action.upper(),
                agent_id=agent_id,
                payload=extra or {},
            )
        except Exception as e:
            logger.error(f"Failed to record event: {e}", exc_info=True)
        try:
            event_payload = {"agent_id": agent_id, "status": status, **(extra or {})}
            await self.controller.publish_event(
                category=EventCategory.AGENT, name=action.upper(), payload=event_payload
            )
        except Exception as e:
            logger.debug(f"Failed to publish event to frontend: {e}")

    def _get_agent_role(self, agent_name: str) -> str:
        """Determine if agent is a doctor or patient based on name."""
        if agent_name.startswith("Doctor_"):
            return "doctor"
        elif agent_name.startswith("Patient_"):
            return "patient"
        return "unknown"

    @AgentCall()
    async def send_message(
        self, agent_name: str, target_agent: str, message_content: str, metadata: Dict[str, Any] = None
    ) -> ActionResult:
        """Send a message from one agent to another during consultation.

        Args:
            agent_name (str): Name of the agent sending the message.
            target_agent (str): Name of the agent receiving the message.
            message_content (str): Content of the message.
            metadata (Dict[str, Any], optional): Additional metadata (e.g., patient_id for doctor consultations).
        """
        current_tick = await self.controller.run_system("timer", "get_tick")
        sender_role = self._get_agent_role(agent_name)
        receiver_role = self._get_agent_role(target_agent)


        if sender_role == "doctor" and receiver_role == "patient":
            message_type = "doctor_to_patient"
        elif sender_role == "patient" and receiver_role == "doctor":
            message_type = "patient_to_doctor"
        elif sender_role == "doctor" and receiver_role == "doctor":
            message_type = "agent_to_agent"
        else:
            message_type = "agent_to_agent"
        message_extra = {"type": message_type}
        if metadata:
            message_extra["metadata"] = metadata

        message = Message(
            from_id=agent_name,
            to_id=target_agent,
            kind=MessageKind.FROM_AGENT_TO_AGENT,
            content=message_content,
            created_at=current_tick,
            extra=message_extra,
        )


        try:
            await self.controller.run_system("messager", "send_message", message=message)

            action_payload = {
                "target": target_agent,
                "content_preview": message_content[:100],
                "content": message_content,          
                "message_type": message_type,
            }
            if metadata:
                action_payload["metadata"] = metadata

            await self._log_action(
                agent_name,
                "SEND_MESSAGE",
                "success",
                action_payload,
            )

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            await self._log_action(agent_name, "SEND_MESSAGE", "failed")
            return ActionResult.error(method_name="send_message", message=f"Failed: {e}")

        return ActionResult.success(method_name="send_message", message=f"{agent_name} sent message to {target_agent}.")
