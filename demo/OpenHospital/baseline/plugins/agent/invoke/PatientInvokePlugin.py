"""
Patient Invoke Plugin for Hospital Simulation.
Executes single action per tick for patient agents.
"""

from typing import Any, Dict, Optional

from agentkernel_distributed.mas.agent.base.plugin_base import InvokePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.types.schemas.action import ActionResult, CallStatus

from baseline.simulation_types.action_types import CurrentAction

logger = get_logger(__name__)


class PatientInvokePlugin(InvokePlugin):
    """
    Action execution plugin for patient agents.
    Executes single action per tick, all actions consume 1 tick.
    """

    def __init__(self, redis: RedisKVAdapter):
        super().__init__()
        self.redis = redis

    async def init(self):
        """Initialize invoke plugin."""
        self.controller = self._component.agent.controller
        self.agent_id = self._component.agent.agent_id
        self._current_action: Optional[CurrentAction] = None
        self._action_counter = 0
        await self.load_from_db()

    def _get_plan_plugin(self):
        """Get plan plugin using peer_plugin."""
        from baseline.plugins.agent.plan.PatientPlannerPlugin import PatientPlannerPlugin
        return self.peer_plugin("plan", PatientPlannerPlugin)

    @property
    def current_action(self) -> Optional[CurrentAction]:
        """Get current action being executed."""
        return self._current_action

    async def execute(self, current_tick: int):
        """Execute the current action from the planner."""

        self.global_tick = current_tick

        plan_plugin = self._get_plan_plugin()
        if not plan_plugin:
            return

        current_tool_call = plan_plugin.current_plan
        if not current_tool_call:
            return

        method_name = current_tool_call.get("action_name")
        component_name = current_tool_call.get("component_name")
        parameters = current_tool_call.get("parameters", {})

        if not all([component_name, method_name]):
            return
        logger.info(f"\n{'─'*50}")
        logger.info(f"🧑 [Tick {current_tick}] PATIENT ACTION: {self.agent_id}")
        logger.info(f"{'─'*50}")
        logger.info(f"  Action: {component_name}.{method_name}")
        if parameters:
            logger.info(f"  Parameters:")
            for key, value in parameters.items():
                value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                logger.info(f"    • {key}: {value_str}")
        try:
            result = await self.controller.run_action(component_name, method_name, **parameters)
            status_icon = "✅" if result.status == CallStatus.SUCCESS else "❌"
            logger.info(f"  Result: {status_icon} {result.status.value}")
            if result.message:
                msg_preview = result.message[:150] + "..." if len(result.message) > 150 else result.message
                logger.info(f"  Message: {msg_preview}")
            logger.info(f"{'─'*50}\n")
            self._set_current_action(method_name, result)
        except Exception as e:
            logger.info(f"  Result: ❌ ERROR")
            logger.info(f"  Error: {str(e)}")
            logger.info(f"{'─'*50}\n")
            error_result = ActionResult(
                status=CallStatus.ERROR,
                method_name=method_name,
                message=str(e),
                data={}
            )
            self._set_current_action(method_name, error_result)
        finally:
            await self.save_to_db()

    def _set_current_action(self, method_name: str, result: ActionResult):
        """Set current action with result for planner to check."""
        self._action_counter += 1
        self._current_action = CurrentAction(
            description=method_name,
            total_ticks=1,
            remaining_ticks=0,
            result=result,
            id=f"{self.agent_id}_{self._action_counter}",
        )

    def _get_temp_vars(self) -> Optional[Dict[str, Any]]:
        """Get temporary variables for checkpoint/resume."""
        current_action_dict = None
        if self._current_action:
            current_action_dict = {
                "description": self._current_action.description,
                "total_ticks": self._current_action.total_ticks,
                "remaining_ticks": self._current_action.remaining_ticks,
                "id": self._current_action.id,
                "result": {
                    "status": self._current_action.result.status.value if self._current_action.result else None,
                    "method_name": self._current_action.result.method_name if self._current_action.result else None,
                    "message": self._current_action.result.message if self._current_action.result else None,
                    "data": self._current_action.result.data if self._current_action.result else None,
                } if self._current_action.result else None,
            }

        return {
            "current_action": current_action_dict,
            "action_counter": self._action_counter,
            "last_executed_tick": getattr(self, 'global_tick', -1),
        }

    def _set_temp_vars(self, vars_dict: Dict[str, Any]) -> None:
        """Restore temporary variables from checkpoint."""
        from typing import Dict, Any
        self._action_counter = vars_dict.get("action_counter", 0)
        current_action_dict = vars_dict.get("current_action")
        if current_action_dict:
            result_dict = current_action_dict.get("result")
            result = None
            if result_dict:
                result = ActionResult(
                    status=CallStatus(result_dict.get("status")) if result_dict.get("status") else CallStatus.ERROR,
                    method_name=result_dict.get("method_name", ""),
                    message=result_dict.get("message", ""),
                    data=result_dict.get("data", {}),
                )

            self._current_action = CurrentAction(
                description=current_action_dict.get("description", ""),
                total_ticks=current_action_dict.get("total_ticks", 1),
                remaining_ticks=current_action_dict.get("remaining_ticks", 0),
                result=result,
                id=current_action_dict.get("id", ""),
            )
        else:
            self._current_action = None

        self.global_tick = vars_dict.get("last_executed_tick", -1)

    async def load_from_db(self) -> None:
        """Load temporary variables from Redis before execute()."""
        redis_key = f"{self.agent_id}:temp_vars:PatientInvokePlugin"
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

        redis_key = f"{self.agent_id}:temp_vars:PatientInvokePlugin"
        try:
            await self.redis.set(redis_key, vars_dict)
            logger.debug(f"[{self.agent_id}] Saved temp vars to Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to save temp vars to Redis: {e}")

    async def clear(self) -> None:
        """Clear all Redis data for this patient when being cleaned up."""
        try:
            await self.redis.delete(f"{self.agent_id}:temp_vars:PatientInvokePlugin")
            logger.info(f"[{self.agent_id}] Cleared PatientInvokePlugin Redis data")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to clear PatientInvokePlugin Redis data: {e}")
