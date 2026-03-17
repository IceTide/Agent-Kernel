"""
Patient Planner Plugin for Hospital Simulation.
Implements the patient workflow:
1. Start at home
2. Register at hospital
3. Move to required locations for actions
4. Consult with doctor via messages
5. If examination ordered: do_examination
6. Report results to doctor
7. Receive treatment
8. Finish (feedback is skipped, doctor gets ground_truth via reflection)
"""

import json
from typing import Dict, Any, Optional, List

from agentkernel_distributed.mas.agent.base.plugin_base import PlanPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.types.schemas.action import CallStatus

from baseline.plugins.agent.perceive.PatientPerceptionPlugin import PatientPerceptionPlugin
from baseline.plugins.agent.profile.PatientProfilePlugin import PatientProfilePlugin
from baseline.plugins.agent.state.PatientStatePlugin import PatientStatePlugin
from baseline.plugins.agent.invoke.PatientInvokePlugin import PatientInvokePlugin
from baseline.utils.prompt_utils import save_prompt

logger = get_logger(__name__)
ACTION_LOCATION_MAP = {
    "registration": "registration_desk",
    "do_examination": "examination_room",
    "receive_treatment": "treatment_room",
}
NO_REPLY_RESEND_TICK_THRESHOLD = 50


class PatientPlannerPlugin(PlanPlugin):
    """
    Planner plugin for patient agents.
    Uses rule-based decision for actions and LLM for message generation.
    """

    def __init__(self, redis: RedisKVAdapter):
        super().__init__()
        self.redis = redis

    async def init(self):
        """Initialize planner plugin."""
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        self.controller = self._component.agent.controller

        self.global_tick = 0
        self._current_action: Optional[Dict[str, Any]] = None
        self._has_reported_exam_completion = False
        await self.load_from_db()

    def _get_perceive_plugin(self) -> Optional[PatientPerceptionPlugin]:
        """Get perceive plugin using peer_plugin."""
        return self.peer_plugin("perceive", PatientPerceptionPlugin)

    def _get_profile_plugin(self) -> Optional[PatientProfilePlugin]:
        """Get profile plugin using peer_plugin."""
        return self.peer_plugin("profile", PatientProfilePlugin)

    def _get_state_plugin(self) -> Optional[PatientStatePlugin]:
        """Get state plugin using peer_plugin."""
        return self.peer_plugin("state", PatientStatePlugin)

    def _get_invoke_plugin(self) -> Optional[PatientInvokePlugin]:
        """Get invoke plugin using peer_plugin."""
        return self.peer_plugin("invoke", PatientInvokePlugin)

    @property
    def current_plan(self) -> Dict[str, Any]:
        """Get current action to execute."""
        return self._current_action or {}

    @property
    def current_step_index(self) -> int:
        """Get current step index (always 0 for single action)."""
        return 0 if self._current_action else -1

    async def execute(self, current_tick: int):
        """Main planner execution called every tick."""
        if hasattr(self, 'global_tick') and self.global_tick == current_tick:
            logger.debug(f"[{self.agent_id}] Already executed in tick {current_tick}, skipping")
            return

        self.global_tick = current_tick

        try:
            invoke_plugin = self._get_invoke_plugin()
            if invoke_plugin and self._current_action:
                current_action = invoke_plugin.current_action
                if current_action and current_action.result:
                    if current_action.result.status in [CallStatus.SUCCESS, CallStatus.ERROR]:
                        if current_action.result.status == CallStatus.SUCCESS:
                            await self._update_phase_from_action(current_action.description)
                        self._current_action = None
            if not self._current_action:
                self._current_action = await self._generate_next_action()

        except Exception as e:
            logger.error(f"Error in patient planner: {e}", exc_info=True)
        finally:
            await self.save_to_db()

    async def _update_phase_from_action(self, method_name: str):
        """Update patient phase based on completed action."""
        state_plugin = self._get_state_plugin()
        if not state_plugin:
            return

        if method_name == "registration":
            await state_plugin.set_state("current_phase", "registered")
        elif method_name == "do_examination":
            await state_plugin.set_state("current_phase", "examined")
            self._has_reported_exam_completion = False
            logger.debug(f"[{self.agent_id}] Entered examined phase, reset report flag")
        elif method_name == "receive_treatment":
            await state_plugin.set_state("current_phase", "treated")
            logger.info(f"[{self.agent_id}] Treatment received, will send thank you message")

    async def _get_context(self) -> Dict[str, Any]:
        """Gather all context needed for decision making."""
        state_plugin = self._get_state_plugin()
        profile_plugin = self._get_profile_plugin()
        perceive_plugin = self._get_perceive_plugin()
        current_phase = await state_plugin.get_state("current_phase") if state_plugin else "home"
        assigned_doctor = await state_plugin.get_state("assigned_doctor") if state_plugin else None
        consultation_room = await state_plugin.get_state("consultation_room") if state_plugin else None
        treatment_result = await state_plugin.get_state("treatment_result") if state_plugin else None
        current_location = await state_plugin.get_state("current_location") if state_plugin else "community"
        profile = {}
        if profile_plugin:
            profile = await profile_plugin.get_profile() or {}
        chat_history = perceive_plugin.get_chat_history(count=10) if perceive_plugin else []
        pending_exams = await self._check_pending_examinations()
        pending_prescriptions = await self._check_pending_prescriptions()
        should_wait_for_doctor = self._should_wait_for_doctor_response(chat_history, assigned_doctor)
        should_resend_last_message = self._should_resend_last_message(chat_history, assigned_doctor)

        return {
            "current_phase": current_phase or "home",
            "current_location": current_location,
            "assigned_doctor": assigned_doctor,
            "consultation_room": consultation_room,
            "treatment_result": treatment_result,
            "demographics": profile.get("demographics", {}),
            "persona": profile.get("persona", ""),
            "chat_history": chat_history,
            "has_pending_examinations": len(pending_exams) > 0,
            "has_pending_prescriptions": len(pending_prescriptions) > 0,
            "should_wait_for_doctor": should_wait_for_doctor,
            "should_resend_last_message": should_resend_last_message,
        }

    async def _generate_next_action(self) -> Dict[str, Any]:
        """Generate next action using rule-based decision."""
        context = await self._get_context()
        action_decision = self._decide_action_by_rules(context)
        action_name = action_decision.get("action")
        required_location = self._get_required_location(action_name, context)
        if required_location and context["current_location"] != required_location:
            return self._make_move_action(required_location)
        if action_name in ["send_message", "resend_last_message"]:
            is_resend = action_name == "resend_last_message"

            if is_resend:
                last_patient_message = self._get_last_patient_message(context.get("chat_history", []))
                message_content = last_patient_message.get("content", "") if last_patient_message else ""
                target = context.get("assigned_doctor", "")
                logger.info(f"[{self.agent_id}] No reply for >{NO_REPLY_RESEND_TICK_THRESHOLD} ticks, resending last message")
            else:
                message_content = await self._generate_message(context)
                target = context.get("assigned_doctor", "")

            if message_content and target:
                state_plugin = self._get_state_plugin()
                if state_plugin and not is_resend:
                    current_phase = context["current_phase"]
                    if current_phase == "registered":
                        await state_plugin.set_state("current_phase", "consulting")
                    elif current_phase == "examined":
                        self._has_reported_exam_completion = True
                        logger.info(f"[{self.agent_id}] Marked exam completion as reported")
                    elif current_phase == "treated":
                        await state_plugin.set_state("current_phase", "finish")
                        logger.info(f"[{self.agent_id}] Sent thank you message, workflow complete")
                return self._make_send_message_action(target, message_content)
            else:
                return self._make_idle_action()
        return self._make_action(action_name)

    def _decide_action_by_rules(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rule-based action decision for patient workflow.

        Workflow:
        1. home -> registration
        2. registered -> send_message (start consultation)
        3. consulting -> do_examination (if pending) / receive_treatment (if prescription) / idle (wait) / send_message
        4. examined -> do_examination (if more pending) / receive_treatment (if prescription) / send_message / idle
        5. treated -> send_message (thank doctor and say goodbye)
        6. finish -> idle (workflow complete)
        """
        phase = context["current_phase"]
        should_wait = context.get("should_wait_for_doctor", False)
        has_pending_exams = context.get("has_pending_examinations", False)
        has_pending_prescriptions = context.get("has_pending_prescriptions", False)
        chat_history = context.get("chat_history", [])
        should_resend_last_message = context.get("should_resend_last_message", False)
        doctor_awaiting_response = False
        if chat_history and context.get("assigned_doctor"):
            last_message = chat_history[-1]
            last_speaker = last_message.get("speaker", "")
            if last_speaker == context.get("assigned_doctor"):
                doctor_awaiting_response = True
        logger.debug(
            f"[{self.agent_id}] Decision context - phase: {phase}, "
            f"pending_exams: {has_pending_exams}, pending_rx: {has_pending_prescriptions}, "
            f"should_wait: {should_wait}, doctor_awaiting_response: {doctor_awaiting_response}, "
            f"should_resend: {should_resend_last_message}"
        )

        if phase == "home":
            return {"action": "registration", "reason": "need to register"}
        elif phase == "registered":
            return {"action": "send_message", "reason": "start consultation"}
        elif phase == "consulting":
            if has_pending_exams:
                logger.info(f"[{self.agent_id}] Has pending examinations, going to do_examination")
                return {"action": "do_examination", "reason": "has pending exam"}
            elif has_pending_prescriptions:
                return {"action": "receive_treatment", "reason": "has prescription"}
            elif should_wait:
                if should_resend_last_message:
                    return {"action": "resend_last_message", "reason": "no doctor reply for over 50 ticks"}
                return {"action": "idle", "reason": "waiting for doctor's response"}
            else:
                return {"action": "send_message", "reason": "continue consultation"}
        elif phase == "examined":
            if has_pending_exams:
                logger.info(f"[{self.agent_id}] Still has pending examinations in examined phase, continuing")
                return {"action": "do_examination", "reason": "has more pending exams"}
            elif has_pending_prescriptions:
                return {"action": "receive_treatment", "reason": "has prescription after exam"}
            elif not self._has_reported_exam_completion:
                logger.info(f"[{self.agent_id}] Examinations completed, will report results to doctor")
                return {"action": "send_message", "reason": "report examination results to doctor"}
            elif doctor_awaiting_response:
                logger.info(f"[{self.agent_id}] Doctor asked follow-up questions, responding")
                return {"action": "send_message", "reason": "respond to doctor's follow-up questions"}
            elif should_resend_last_message:
                return {"action": "resend_last_message", "reason": "no doctor reply for over 50 ticks"}
            else:
                logger.debug(f"[{self.agent_id}] Already reported exam completion, waiting for doctor")
                return {"action": "idle", "reason": "waiting for doctor after reporting exam completion"}
        elif phase == "treated":
            return {"action": "send_message", "reason": "thank doctor and say goodbye"}
        elif phase == "finish":
            return {"action": "idle", "reason": "workflow complete"}

        return {"action": "idle", "reason": "default"}

    def _get_required_location(self, action: str, context: Dict[str, Any]) -> Optional[str]:
        """Get required location for an action."""
        if action in ACTION_LOCATION_MAP:
            return ACTION_LOCATION_MAP[action]
        elif action in ["send_message", "resend_last_message"]:
            if context.get("current_phase") == "treated":
                return None                                                 
            return context.get("consultation_room")
        elif action == "move":
            return None                                           
        return None

    async def _generate_message(self, context: Dict[str, Any]) -> str:
        """Use LLM to generate message content for doctor.

        Retrieval strategy:
        - Fixed: demographics, persona, and chief_complaint
        - Retrieved: top 3 medical history based on conversation context
        """
        profile_plugin = self._get_profile_plugin()
        demographics = context.get("demographics", {})
        persona = context.get("persona", "")
        chat_history = context.get("chat_history", [])
        current_phase = context.get("current_phase", "home")
        chief_complaint = ""
        if profile_plugin:
            try:
                profile = await profile_plugin.get_profile()
                present_illness = profile.get("present_illness_history", {})
                chief_complaint = present_illness.get("chief_complaint", "")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Failed to get chief complaint: {e}")
        search_query = await self._generate_search_query(chat_history, current_phase)
        relevant_history = []
        if profile_plugin and search_query:
            try:
                search_results = await profile_plugin.search_medical_history(
                    query=search_query,
                    top_k=3,
                )
                for result in search_results[:3]:
                    history_type = result.get("metadata", {}).get("history_type", "")
                    content = result.get("content", "")
                    relevant_history.append(
                        {
                            "type": history_type,
                            "content": content,
                        }
                    )
                logger.debug(f"[{self.agent_id}] Retrieved {len(relevant_history)} relevant history items")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Failed to retrieve medical history: {e}")
        system_prompt = """You are a patient talking to your doctor. Generate an appropriate message based on:
1. Your demographics and persona (who you are)
2. Your chief complaint (main reason for visit)
3. Relevant medical history retrieved from your records
4. The conversation history with the doctor

Rules:
1. If no conversation yet, introduce yourself briefly and state your main concern (chief complaint)
2. Answer ONLY what the doctor asks. Do not provide information beyond the scope of the question.
3. Base your response on retrieved medical history. DO NOT fabricate information not present in the retrieved history.
4. If you just completed examination (phase=examined), simply inform the doctor that you've completed the examinations (do NOT report the actual results)
5. If you just received treatment (phase=treated), thank the doctor and say goodbye briefly
6. Be cooperative, clear, and concise
7. Stay in character as described in your persona (e.g., if you cannot speak, respond from a caregiver's perspective)

Output ONLY the message content, nothing else."""
        user_prompt_data = {
            "demographics": demographics,
            "persona": persona,
            "current_phase": current_phase,
            "chat_history": chat_history,
        }
        if not chat_history:
            user_prompt_data["chief_complaint"] = chief_complaint
        if relevant_history:
            user_prompt_data["relevant_medical_history"] = relevant_history
        else:
            user_prompt_data["relevant_medical_history"] = "No specific medical history retrieved"

        user_prompt = json.dumps(user_prompt_data, ensure_ascii=False, indent=2)

        try:
            response = await self.model.chat(user_prompt, system_prompt=system_prompt, capability="patient")
            save_prompt(
                agent_id=self.agent_id,
                tick=self.global_tick,
                context_id="generate_message",
                stage="generate_message",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                plugin_logger=logger,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate message: {e}")
            if not chat_history:
                return (
                    f"Hello doctor, {chief_complaint}"
                    if chief_complaint
                    else "Hello doctor, I'm here for a consultation."
                )
            elif current_phase == "examined":
                return "Doctor, I've completed the examinations you ordered."
            elif current_phase == "treated":
                return "Thank you for your care, doctor. We appreciate your help."
            return "I'm here for my consultation."

    async def _generate_search_query(self, chat_history: List[Dict[str, Any]], current_phase: str) -> str:
        """Generate a search query based on conversation context.

        Args:
            chat_history: Recent conversation messages
            current_phase: Current consultation phase

        Returns:
            Search query string for medical history retrieval
        """
        if not chat_history:
            return "present illness symptoms chief complaint current condition"
        doctor_messages = []
        for msg in reversed(chat_history[-5:]):                   
            speaker = msg.get("speaker", "")
            content = msg.get("content", "")
            if speaker != self.agent_id and content:                    
                doctor_messages.append(content)
                if len(doctor_messages) >= 2:                                      
                    break

        if doctor_messages:
            return " ".join(doctor_messages)
        phase_queries = {
            "consulting": "symptoms complaints present illness",
            "examined": "examination results medical history",
            "treated": "treatment medication follow-up",
        }
        return phase_queries.get(current_phase, "medical history condition")

    def _should_wait_for_doctor_response(
        self, chat_history: List[Dict[str, Any]], assigned_doctor: Optional[str]
    ) -> bool:
        """
        Check if patient should wait for doctor's response before sending another message.

        Patient should wait if:
        1. Has sent at least one message to the doctor
        2. The last message in chat history is from the patient (not the doctor)
        3. Patient hasn't sent too many consecutive messages (max 2)

        Args:
            chat_history: Recent chat history
            assigned_doctor: Assigned doctor ID

        Returns:
            True if patient should wait for doctor's reply
        """
        if not chat_history or not assigned_doctor:
            return False
        last_message = chat_history[-1]
        last_speaker = last_message.get("speaker", "")
        if last_speaker == self.agent_id:
            consecutive_patient_messages = 0
            for msg in reversed(chat_history):
                if msg.get("speaker") == self.agent_id:
                    consecutive_patient_messages += 1
                else:
                    break
            if consecutive_patient_messages >= 3:
                logger.debug(f"[{self.agent_id}] Sent {consecutive_patient_messages} messages without reply, waiting")

            return True

        return False

    def _should_resend_last_message(
        self, chat_history: List[Dict[str, Any]], assigned_doctor: Optional[str]
    ) -> bool:
        """Check if last patient message should be resent due to long no-reply wait."""
        if not chat_history or not assigned_doctor:
            return False
        if chat_history[-1].get("speaker", "") != self.agent_id:
            return False

        last_patient_message = self._get_last_patient_message(chat_history)
        if not last_patient_message:
            return False

        last_patient_tick = last_patient_message.get("tick")
        if not isinstance(last_patient_tick, (int, float)):
            return False

        waited_ticks = self.global_tick - int(last_patient_tick)
        return waited_ticks > NO_REPLY_RESEND_TICK_THRESHOLD

    def _get_last_patient_message(self, chat_history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Get the latest patient message from chat history."""
        for message in reversed(chat_history):
            if message.get("speaker", "") == self.agent_id:
                return message
        return None

    async def _check_pending_examinations(self) -> list:
        """Check if patient has pending examinations."""
        try:
            pending = await self.controller.run_environment(
                "hospital_system", "get_pending_examinations", patient_id=self.agent_id
            )
            if pending:
                logger.debug(f"[{self.agent_id}] Found {len(pending)} pending examinations")
            return pending or []
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to check pending examinations: {e}")
            return []

    async def _check_pending_prescriptions(self) -> list:
        """Check if patient has pending prescriptions."""
        try:
            pending = await self.controller.run_environment(
                "hospital_system", "get_pending_prescription", patient_id=self.agent_id
            )
            return [pending] if pending else []
        except Exception:
            return []

    def _make_action(self, action_name: str, **extra_params) -> Dict[str, Any]:
        """Create an action dict for tools or otheractions."""
        component = "tools" if action_name in ["do_examination", "receive_treatment"] else "otheractions"
        params = {"agent_name": self.agent_id}
        params.update(extra_params)
        return {
            "action_name": action_name,
            "component_name": component,
            "parameters": params,
            "tick_consumption": 1,
        }

    def _make_move_action(self, target_location: str) -> Dict[str, Any]:
        """Create a move action."""
        return {
            "action_name": "move",
            "component_name": "otheractions",
            "parameters": {"agent_name": self.agent_id, "target_location": target_location},
            "tick_consumption": 1,
        }

    def _make_send_message_action(self, target: str, content: str) -> Dict[str, Any]:
        """Create a send_message action."""
        return {
            "action_name": "send_message",
            "component_name": "communication",
            "parameters": {"agent_name": self.agent_id, "target_agent": target, "message_content": content},
            "tick_consumption": 1,
        }

    def _make_idle_action(self) -> Dict[str, Any]:
        """Create an idle action."""
        return {
            "action_name": "idle",
            "component_name": "otheractions",
            "parameters": {"agent_name": self.agent_id},
            "tick_consumption": 1,
        }

    def _get_temp_vars(self) -> Optional[Dict[str, Any]]:
        """Get temporary variables for checkpoint/resume."""
        return {
            "current_action": self._current_action,
            "has_reported_exam_completion": self._has_reported_exam_completion,
            "last_executed_tick": getattr(self, 'global_tick', -1),
        }

    def _set_temp_vars(self, vars_dict: Dict[str, Any]) -> None:
        """Restore temporary variables from checkpoint."""
        self._current_action = vars_dict.get("current_action")
        self._has_reported_exam_completion = vars_dict.get("has_reported_exam_completion", False)
        self.global_tick = vars_dict.get("last_executed_tick", -1)

    async def load_from_db(self) -> None:
        """Load temporary variables from Redis before execute()."""
        redis_key = f"{self.agent_id}:temp_vars:PatientPlannerPlugin"
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

        redis_key = f"{self.agent_id}:temp_vars:PatientPlannerPlugin"
        try:
            await self.redis.set(redis_key, vars_dict)
            logger.debug(f"[{self.agent_id}] Saved temp vars to Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to save temp vars to Redis: {e}")

    async def clear(self) -> None:
        """Clear all Redis data for this patient when being cleaned up."""
        try:
            await self.redis.delete(f"{self.agent_id}:temp_vars:PatientPlannerPlugin")
            logger.info(f"[{self.agent_id}] Cleared PatientPlannerPlugin Redis data")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to clear PatientPlannerPlugin Redis data: {e}")
