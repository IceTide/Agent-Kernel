"""
Doctor Invoke Plugin for Hospital Simulation.
Executes multiple actions per tick for doctor agents.
"""

from typing import List, Optional, Dict, Any

from agentkernel_distributed.mas.agent.base.plugin_base import InvokePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.types.schemas.action import ActionResult, CallStatus

from baseline.simulation_types.action_types import CurrentAction, ActionRecord, ActionOutcome

logger = get_logger(__name__)


class DoctorInvokePlugin(InvokePlugin):
    """
    Action execution plugin for doctor agents.
    Can execute multiple actions in the same tick (e.g., order exam + send message).
    Stores action results for context retrieval by planner.
    """

    MAX_ACTION_HISTORY = 10

    def __init__(self, redis: RedisKVAdapter):
        super().__init__()
        self.redis = redis

    async def init(self):
        """Initialize invoke plugin."""
        self.controller = self._component.agent.controller
        self.agent_id = self._component.agent.agent_id
        self._current_action: Optional[CurrentAction] = None
        self._action_history: List[ActionRecord] = []
        self._action_counter = 0
        await self.load_from_db()

    def _get_plan_plugin(self):
        """Get plan plugin using peer_plugin."""
        from baseline.plugins.agent.plan.DoctorPlannerPlugin import DoctorPlannerPlugin
        return self.peer_plugin("plan", DoctorPlannerPlugin)

    @property
    def current_action(self) -> Optional[CurrentAction]:
        """Get current action being executed."""
        return self._current_action

    @property
    def action_history(self) -> List[ActionRecord]:
        """Return action history."""
        return self._action_history

    def _trim_action_history(self) -> None:
        """Keep only the most recent action history entries."""
        if len(self._action_history) > self.MAX_ACTION_HISTORY:
            self._action_history = self._action_history[-self.MAX_ACTION_HISTORY:]

    @property
    def last_action_result(self) -> Optional[Dict[str, Any]]:
        """
        Get the last action result for planner context.
        Derived from current_action to avoid redundant storage.
        """
        if not self._current_action or not self._current_action.result:
            return None
        
        result = self._current_action.result
        return {
            "action_name": self._current_action.description,
            "status": result.status.value if result.status else "unknown",
            "data": result.data if hasattr(result, 'data') else None,
            "message": result.message if hasattr(result, 'message') else "",
        }

    async def execute(self, current_tick: int):
        """Execute the current action from the planner's action queue."""

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

        if parameters:
            logger.info(f"  Parameters:")
            for key, value in parameters.items():
                value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                logger.info(f"    • {key}: {value_str}")
        try:
            result = await self.controller.run_action(component_name, method_name, **parameters)
            status_icon = "✅" if result.status == CallStatus.SUCCESS else "❌"
            logger.info(f"  Result: {status_icon} {result.status.value}")
            await self._record_action(method_name, result)
        except Exception as e:
            logger.error(f"  Error: {str(e)}")
            error_result = ActionResult(
                status=CallStatus.ERROR,
                method_name=method_name,
                message=str(e),
                data={}
            )
            await self._record_action(method_name, error_result)
        finally:
            await self.save_to_db()

    async def _record_action(self, method_name: str, result: ActionResult):
        """Record action to history and set current action for planner."""
        self._action_counter += 1
        self._current_action = CurrentAction(
            description=method_name,
            total_ticks=1,
            remaining_ticks=0,
            result=result,
            id=f"{self.agent_id}_{self._action_counter}",
        )
        outcome = ActionOutcome.COMPLETED if result.status == CallStatus.SUCCESS else ActionOutcome.FAILED
        self._action_history.append(ActionRecord(
            description=method_name,
            duration_ticks=1,
            outcome=outcome,
            result=result,
        ))
        self._trim_action_history()
        await self._persist_action()

    async def _persist_action(self):
        """Persist action history to Redis."""
        if self.redis:
            self._trim_action_history()
            history = [action.to_dict() for action in self._action_history]
            await self.redis.set(f"{self.agent_id}:actions_history", history)

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
            "action_history": [action.to_dict() for action in self._action_history],
            "action_counter": self._action_counter,
            "last_executed_tick": getattr(self, 'global_tick', -1),
        }

    def _set_temp_vars(self, vars_dict: Dict[str, Any]) -> None:
        """Restore temporary variables from checkpoint."""
        self._action_counter = vars_dict.get("action_counter", 0)
        history_dicts = vars_dict.get("action_history", [])
        self._action_history = [ActionRecord.from_dict(d) for d in history_dicts]
        self._trim_action_history()
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
        redis_key = f"{self.agent_id}:temp_vars:DoctorInvokePlugin"
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

        redis_key = f"{self.agent_id}:temp_vars:DoctorInvokePlugin"
        try:
            await self.redis.set(redis_key, vars_dict)
            logger.debug(f"[{self.agent_id}] Saved temp vars to Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to save temp vars to Redis: {e}")
