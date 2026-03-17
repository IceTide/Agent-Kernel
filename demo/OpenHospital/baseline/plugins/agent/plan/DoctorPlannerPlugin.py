"""
Doctor Planner Plugin for Hospital Simulation.
Implements the doctor workflow:
1. Stay in consultation room
2. Receive patient messages and respond
3. Ask questions to gather information
4. Order examinations when needed
5. Review examination results
6. Make diagnosis and prescribe treatment plan
7. Consult with other doctors (Collaborative diagnosis)
"""

import json
import re
import heapq
import itertools
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Tuple

from agentkernel_distributed.mas.agent.base.plugin_base import PlanPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.toolkit.storages.vectordb_adapters.base import BaseVectorDBAdapter
from agentkernel_distributed.toolkit.utils.commons import clean_json_response
from agentkernel_distributed.types.schemas.action import CallStatus
from agentkernel_distributed.types.schemas.vectordb import VectorSearchRequest

from baseline.plugins.agent.perceive.DoctorPerceptionPlugin import DoctorPerceptionPlugin
from baseline.plugins.agent.profile.DoctorProfilePlugin import DoctorProfilePlugin
from baseline.plugins.agent.state.DoctorStatePlugin import DoctorStatePlugin
from baseline.plugins.agent.invoke.DoctorInvokePlugin import DoctorInvokePlugin
from baseline.utils.prompt_utils import save_prompt

logger = get_logger(__name__)


class DoctorPlannerPlugin(PlanPlugin):
    """
    Planner plugin for doctor agents.
    Doctors stay in their consultation room and interact with patients.
    """

    def __init__(self, redis: RedisKVAdapter, examinations_vectordb: Optional[BaseVectorDBAdapter] = None):
        super().__init__()
        self.redis = redis
        self.examinations_vectordb = examinations_vectordb

    async def init(self):
        """Initialize planner plugin."""
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        self.controller = self._component.agent.controller

        self.global_tick = 0
        self._tool_calls: List[Dict[str, Any]] = []
        self._tool_call_index = 0
        self._pending_messages_pq: List[Tuple[int, int, Dict[str, Any]]] = []
        self._message_counter = itertools.count()
        self._last_processed_action_id: Optional[str] = None
        self._active_patients: Dict[str, Dict] = {}
        self._treated_patients: set = set()
        self._completed_consultations: List[Dict[str, Any]] = []
        self._patients_pending_reflection: List[str] = []
        self._diseases_by_department: Dict[str, List[str]] = {}

        self._current_patient_id: Optional[str] = None
        self._pending_knowledge_query: Optional[Dict[str, Any]] = (
            None                                                    
        )
        self._consecutive_knowledge_searches: Dict[str, int] = {}                                   
        self._consecutive_doctor_replies: Dict[str, int] = {}                                   
        await self.load_from_db()

    async def _load_diseases_by_department(self, department: str) -> List[str]:
        """Load diseases for a department from Redis, with caching."""
        if department in self._diseases_by_department:
            return self._diseases_by_department[department]

        try:
            diseases = await self.redis.get(f"hospital:diseases:{department}")
            if diseases:
                self._diseases_by_department[department] = diseases
                return diseases
        except Exception as e:
            logger.warning(f"Failed to load diseases for department {department}: {e}")

        return []

    async def get_diseases_by_department(self, department: str) -> List[str]:
        """Get diseases for a specific department."""
        return await self._load_diseases_by_department(department)

    def _get_perceive_plugin(self) -> Optional[DoctorPerceptionPlugin]:
        return self.peer_plugin("perceive", DoctorPerceptionPlugin)

    def _get_profile_plugin(self) -> Optional[DoctorProfilePlugin]:
        return self.peer_plugin("profile", DoctorProfilePlugin)

    def _get_state_plugin(self) -> Optional[DoctorStatePlugin]:
        return self.peer_plugin("state", DoctorStatePlugin)

    def _get_invoke_plugin(self) -> Optional[DoctorInvokePlugin]:
        return self.peer_plugin("invoke", DoctorInvokePlugin)

    def _get_reflect_plugin(self):
        from baseline.plugins.agent.reflect.DoctorReflectPlugin import DoctorReflectPlugin

        return self.peer_plugin("reflect", DoctorReflectPlugin)

    @property
    def current_plan(self) -> Dict[str, Any]:
        if 0 <= self._tool_call_index < len(self._tool_calls):
            return self._tool_calls[self._tool_call_index]
        return {}

    @property
    def current_step_index(self) -> int:
        return self._tool_call_index

    @property
    def completed_consultations(self) -> List[Dict[str, Any]]:
        return self._completed_consultations

    @property
    def patients_pending_reflection(self) -> List[str]:
        return self._patients_pending_reflection

    def pop_patient_for_reflection(self) -> Optional[str]:
        if self._patients_pending_reflection:
            return self._patients_pending_reflection.pop(0)
        return None

    def cleanup_patient_data(self, patient_id: str) -> None:
        """
        Clean up patient-related data from planner plugin.
        Called by reflect plugin after reflection is complete.

        Args:
            patient_id: Patient ID to clean up
        """
        if patient_id in self._active_patients:
            del self._active_patients[patient_id]
            logger.debug(f"[{self.agent_id}] Removed {patient_id} from active_patients")
        self._completed_consultations = [
            record for record in self._completed_consultations if record.get("patient_id") != patient_id
        ]
        logger.debug(f"[{self.agent_id}] Removed {patient_id} from completed_consultations")
        if patient_id in self._consecutive_knowledge_searches:
            del self._consecutive_knowledge_searches[patient_id]
            logger.debug(f"[{self.agent_id}] Removed {patient_id} from consecutive_knowledge_searches")
        if patient_id in self._consecutive_doctor_replies:
            del self._consecutive_doctor_replies[patient_id]
            logger.debug(f"[{self.agent_id}] Removed {patient_id} from consecutive_doctor_replies")

    def _get_patient_id_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """
        Safely extract patient_id from message metadata.
        For doctor-to-doctor messages, patient_id should be in metadata.
        For patient messages, speaker IS the patient_id.
        """
        speaker = message.get("speaker", "")
        if speaker.startswith("Patient"):
            return speaker
        if speaker.startswith("Doctor"):
            metadata = message.get("metadata", {})
            patient_id = metadata.get("patient_id")
            if patient_id:
                return patient_id
            else:
                logger.error(f"❌ [{self.agent_id}] Doctor message from {speaker} missing patient_id in metadata!")
                return None

        return None

    def _add_pending_message(self, message: Dict[str, Any]) -> None:
        """Add message to priority queue. Doctor messages get higher priority."""
        speaker = message.get("speaker", "")
        priority_class = 0 if speaker.startswith("Doctor") else 1
        count = next(self._message_counter)
        heapq.heappush(self._pending_messages_pq, (priority_class, count, message))
        logger.debug(
            f"[{self.agent_id}] Added message from {speaker} with priority {priority_class}, queue size: {len(self._pending_messages_pq)}"
        )

    def _pop_pending_message(self) -> Optional[Dict[str, Any]]:
        """Pop highest priority message from queue."""
        if not self._pending_messages_pq:
            return None
        _, _, message = heapq.heappop(self._pending_messages_pq)
        return message

    def _has_pending_messages(self) -> bool:
        """Check if there are pending messages."""
        return len(self._pending_messages_pq) > 0

    def _is_duplicate_message(self, message: Dict[str, Any]) -> bool:
        """Check if message is a duplicate in the queue."""
        speaker = message.get("speaker")
        content = message.get("content")
        for _, _, m in self._pending_messages_pq:
            if m.get("speaker") == speaker and m.get("content") == content:
                return True
        return False

    async def execute(self, current_tick: int):
        if hasattr(self, "global_tick") and self.global_tick == current_tick:
            logger.debug(f"[{self.agent_id}] Already executed in tick {current_tick}, skipping")
            return

        self.global_tick = current_tick

        try:
            perceive_plugin = self._get_perceive_plugin()
            new_message = perceive_plugin.perception if perceive_plugin else None

            if new_message and new_message.get("speaker"):
                if not self._is_duplicate_message(new_message):
                    self._add_pending_message(new_message)

            has_pending_actions = 0 <= self._tool_call_index < len(self._tool_calls)

            if has_pending_actions:
                logger.debug(f"[{self.agent_id}] Has pending actions, checking completion status")
                invoke_plugin = self._get_invoke_plugin()
                if invoke_plugin:
                    current_action = invoke_plugin.current_action
                    if current_action and current_action.result:
                        if current_action.result.status in [CallStatus.SUCCESS, CallStatus.ERROR]:
                            action_id = getattr(current_action, "id", None)
                            if action_id != self._last_processed_action_id:
                                self._last_processed_action_id = action_id
                                action_name = (
                                    current_action.result.action_name
                                    if hasattr(current_action.result, "action_name")
                                    else ""
                                )
                                is_knowledge_search = "search_medical_knowledge" in str(action_name).lower()

                                self._tool_call_index += 1
                                logger.debug(
                                    f"[{self.agent_id}] Action completed ({action_name}), moving to index {self._tool_call_index}"
                                )
                                if is_knowledge_search and self._pending_knowledge_query:
                                    logger.info(
                                        f"[{self.agent_id}] Knowledge search completed, "
                                        f"will prioritize processing results for {self._pending_knowledge_query.get('patient_id')}"
                                    )
                    else:
                        logger.debug(f"[{self.agent_id}] Waiting for action to be executed")
                else:
                    logger.warning(f"[{self.agent_id}] No invoke plugin found, cannot check action status")

            if self._tool_call_index >= len(self._tool_calls):
                if self._pending_knowledge_query:
                    logger.info(
                        f"[{self.agent_id}] Processing pending knowledge query results for "
                        f"{self._pending_knowledge_query.get('patient_id')}"
                    )
                    patient_id = self._pending_knowledge_query.get("patient_id")
                    partner_id = self._pending_knowledge_query.get("partner_id")
                    message_content = self._pending_knowledge_query.get("message_content")
                    old_pending_query = self._pending_knowledge_query
                    synthetic_message = {
                        "speaker": partner_id,
                        "content": message_content,
                        "metadata": {"patient_id": patient_id, "is_from_knowledge_query": True},
                    }

                    self._tool_calls = await self._generate_next_actions(synthetic_message)
                    self._tool_call_index = 0
                    if self._pending_knowledge_query is old_pending_query:
                        self._pending_knowledge_query = None
                        logger.info(f"[{self.agent_id}] Pending knowledge query processed, state cleared")
                    else:
                        logger.info(
                            f"[{self.agent_id}] Pending knowledge query processed, but a new query was initiated "
                            f"(keeping new pending state)"
                        )
                elif self._has_pending_messages():
                    next_message = self._pop_pending_message()

                    self._tool_calls = await self._generate_next_actions(next_message)
                    self._tool_call_index = 0

                    while not self._tool_calls and self._has_pending_messages():
                        next_message = self._pop_pending_message()

                        self._tool_calls = await self._generate_next_actions(next_message)
                        self._tool_call_index = 0

        except Exception as e:
            logger.error(f"Error in doctor planner: {e}", exc_info=True)
        finally:
            await self.save_to_db()
            pass

    async def _generate_next_actions(self, message: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate next actions based on incoming message."""
        actions = []

        if not message:
            return []

        speaker = message.get("speaker", "")
        content = message.get("content", "")

        logger.info(f"🔍 [{self.agent_id}] Processing message from {speaker}")

        if speaker.startswith("Patient"):
            patient_id = speaker
            if patient_id in self._treated_patients:
                logger.info(f"⏭️ [{self.agent_id}] Skipping {patient_id} - already treated")
                return []
            self._ensure_patient_tracked(patient_id)
            self._active_patients[patient_id]["messages_received"] += 1
            if patient_id in self._consecutive_doctor_replies:
                self._consecutive_doctor_replies[patient_id] = 0

            actions = await self._generate_consultation_response(patient_id, content, partner_id=patient_id)
            logger.info(f"✅ [{self.agent_id}] Generated {len(actions)} actions for patient {patient_id}")

        elif speaker.startswith("Doctor"):
            logger.info(f"👨‍⚕️ [{self.agent_id}] Received consultation from {speaker}")
            patient_id = self._get_patient_id_from_message(message)

            if patient_id:
                if patient_id in self._treated_patients:
                    logger.info(
                        f"⏭️ [{self.agent_id}] Skipping consultation from {speaker} about {patient_id} - already treated"
                    )
                    return []

                logger.info(f"✅ [{self.agent_id}] Processing consultation from {speaker} regarding {patient_id}")
                if patient_id in self._active_patients:
                    self._consecutive_doctor_replies[patient_id] = (
                        self._consecutive_doctor_replies.get(patient_id, 0) + 1
                    )
                    logger.info(
                        f"[{self.agent_id}] Consecutive doctor replies for {patient_id}: "
                        f"{self._consecutive_doctor_replies[patient_id]}"
                    )

                actions = await self._generate_consultation_response(patient_id, content, partner_id=speaker)
                logger.info(f"✅ [{self.agent_id}] Generated {len(actions)} actions for consultation")
            else:
                logger.error(
                    f"❌ [{self.agent_id}] Received message from {speaker} but could not identify patient_id from metadata! "
                    f"IGNORING to prevent infinite loop."
                )
                logger.error(f"   Message content: {content[:200]}...")
                logger.error(f"   Message structure: {message}")
                return []

        else:
            logger.warning(f"⚠️ [{self.agent_id}] Unknown speaker type: {speaker}")
            return []

        return actions

    def _ensure_patient_tracked(self, patient_id: str):
        if patient_id not in self._active_patients:
            self._active_patients[patient_id] = {
                "consultation_started": self.global_tick,
                "messages_received": 0,
                "examinations_ordered": False,
                "diagnosis_made": False,
            }

    async def _generate_consultation_response(
        self, patient_id: str, message_content: str, partner_id: str
    ) -> List[Dict[str, Any]]:
        """
        Generate response using multi-stage LLM calls.

        Stage 1: Initial planning - decide action type (simplified prompt, no detailed lists)
        Stage 2: Based on action, call specialized methods:
            - REQUEST_CONSULTATION -> _select_consultant()
            - ORDER_EXAMINATION -> _select_examinations()
            - MAKE_DIAGNOSIS -> _select_diagnosis()
        """
        actions = []
        context = await self._get_basic_consultation_context(patient_id, message_content, partner_id=partner_id)
        department = context["department"]
        chat_history = context["chat_history"]
        exam_results = context["exam_results"]
        optional_sections = []
        formatted_exam_results = self._format_exam_results(exam_results)
        if formatted_exam_results:
            optional_sections.append(formatted_exam_results)
        if context.get("knowledge_results"):
            optional_sections.append(context["knowledge_results"])
        if context.get("reflections"):
            optional_sections.append(context["reflections"])

        optional_context = "\n\n".join(optional_sections) if optional_sections else ""
        is_talking_to_doctor = partner_id.startswith("Doctor")
        is_primary_doctor = partner_id == patient_id
        is_receiving_consultation_reply = False
        if is_talking_to_doctor:
            if patient_id in self._active_patients:
                is_receiving_consultation_reply = True
                is_primary_doctor = True
                logger.info(f"[{self.agent_id}] Receiving consultation reply from {partner_id} for {patient_id}")

        is_consultant = is_talking_to_doctor and not is_primary_doctor
        exam_results_instruction = ""
        if exam_results:
            exam_results_instruction = """
The patient has completed examinations and results are available above.
YOU SHOULD:
1. Review the examination results carefully
2. Analyze findings and correlate with symptoms
3. Consider making a diagnosis based on results"""
        else:
            exam_results_instruction = """
The patient has NOT completed any examinations yet.
YOU MUST:
1. ORDER_EXAMINATION BEFORE MAKING DIAGNOSIS - Do NOT rush to diagnosis without exam results
2. Ensure you have sufficient objective data (lab tests, imaging, etc.) before diagnosing
3. Only consider MAKE_DIAGNOSIS after you have examination results to support your decision"""
        if is_consultant:
            system_prompt = self._build_consultant_prompt_stage1(
                department, partner_id, patient_id, optional_context, exam_results_instruction
            )
        else:
            consultation_reply_instruction = ""
            if is_receiving_consultation_reply:
                consultation_reply_instruction = f"""
You previously requested expert consultation for {patient_id}. The consultant has provided their recommendations.

NOW YOU SHOULD:
1. Review the consultant's advice carefully
2. Integrate their recommendations with your clinical findings
3. Decide your NEXT step - you have MULTIPLE options:
   - **ASK_QUESTION** (to patient) - If you need more information from the patient
   - **ORDER_EXAMINATION** - If you need more objective data before diagnosis (STRONGLY RECOMMENDED if no exams yet)
   - **REPLY_CONSULTATION** (to {partner_id}) - If you need to clarify or follow up with the consultant
   - **MAKE_DIAGNOSIS** - ONLY if you have sufficient information AND examination results to support your diagnosis
   - **REQUEST_CONSULTATION** - If you need advice from another specialist
4. Your message_to_recipient should match your action:
   - For ASK_QUESTION: address to PATIENT ({patient_id})
   - For REPLY_CONSULTATION: address to {partner_id}
   - For MAKE_DIAGNOSIS: omit (message will be generated automatically)
"""
            consecutive_searches = self._consecutive_knowledge_searches.get(patient_id, 0)
            knowledge_search_warning = ""
            if consecutive_searches > 0:
                knowledge_search_warning = f"""
**You have already searched {consecutive_searches} time(s) consecutively for this patient.**
- Maximum allowed: 2 consecutive searches
- If you've searched twice, you MUST choose another action (not SEARCH_KNOWLEDGE)
"""
            consecutive_doctor_replies_count = self._consecutive_doctor_replies.get(patient_id, 0)
            doctor_reply_warning = ""
            if consecutive_doctor_replies_count > 0:
                max_doctor_replies = 3
                doctor_reply_warning = f"""
**You have exchanged {consecutive_doctor_replies_count} consecutive message(s) with colleague(s) for this patient.**
- Maximum allowed: {max_doctor_replies} consecutive doctor-to-doctor exchanges
- {"You MUST now respond to the PATIENT or take a clinical action (ASK_QUESTION, ORDER_EXAMINATION, MAKE_DIAGNOSIS). Do NOT continue chatting with colleagues." if consecutive_doctor_replies_count >= max_doctor_replies else "Consider whether you have enough information to proceed with the patient directly."}
"""

            system_prompt = self._build_primary_doctor_prompt_stage1(
                department,
                partner_id,
                patient_id,
                optional_context,
                consultation_reply_instruction,
                exam_results_instruction,
                knowledge_search_warning,
                doctor_reply_warning,
            )
        is_talking_to_patient = partner_id == patient_id

        if is_talking_to_patient:
            user_prompt_data = {
                "patient_id": patient_id,
                "current_message_to_respond": {
                    "from": patient_id,
                    "content": message_content,
                },
            }
            if context.get("chat_history_with_partner"):
                user_prompt_data["conversation_history"] = context["chat_history_with_partner"]
        else:
            user_prompt_data = {
                "patient_id": patient_id,
                "current_conversation_partner": partner_id,
                "current_message_to_respond": {
                    "from": partner_id,
                    "content": message_content,
                },
            }
            if context.get("chat_history_with_partner"):
                user_prompt_data["conversation_with_current_partner"] = context["chat_history_with_partner"]
            if context.get("chat_history_with_patient"):
                user_prompt_data["direct_conversation_with_patient"] = context["chat_history_with_patient"]
        if context.get("consultation_history"):
            user_prompt_data["consultations_with_colleagues"] = {}
            for consultant_id, consultant_history in context["consultation_history"].items():
                user_prompt_data["consultations_with_colleagues"][consultant_id] = consultant_history

        user_prompt = json.dumps(user_prompt_data, ensure_ascii=False, indent=2)

        try:
            response = await self.model.chat(user_prompt, system_prompt=system_prompt)
            save_prompt(
                agent_id=self.agent_id,
                tick=self.global_tick,
                context_id=patient_id,
                stage="stage1",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                plugin_logger=logger,
            )

            response_clean = clean_json_response(response)
            decision = json.loads(response_clean)

            action_type = decision.get("action", "")
            message_to_recipient = decision.get("message_to_recipient", "")
            message_recipient = decision.get("message_recipient", "")

            logger.info(f"[{self.agent_id}] Stage 1 decision: {action_type}, message_recipient: {message_recipient}")
            def get_target_from_recipient() -> str:
                """Determine target agent based on LLM-specified message_recipient field."""
                if message_recipient == "patient":
                    return patient_id
                elif message_recipient == "doctor":
                    return partner_id
                elif message_recipient and message_recipient.startswith("Doctor_"):
                    consultation_history = context.get("consultation_history", {})
                    if message_recipient in consultation_history:
                        return message_recipient
                    else:
                        logger.warning(
                            f"[{self.agent_id}] LLM 指定的医生 ID {message_recipient} 不在会诊历史中，回退到 partner_id"
                        )
                        return partner_id
                else:
                    if is_consultant:
                        return partner_id                                                
                    elif is_receiving_consultation_reply:
                        return patient_id                                                            
                    else:
                        return partner_id                                                 
            if action_type != "SEARCH_KNOWLEDGE":
                if patient_id in self._consecutive_knowledge_searches:
                    logger.info(
                        f"[{self.agent_id}] Resetting consecutive search counter for {patient_id} "
                        f"(was {self._consecutive_knowledge_searches[patient_id]}, action: {action_type})"
                    )
                    self._consecutive_knowledge_searches[patient_id] = 0

            if action_type == "ASK_QUESTION" or action_type == "REPLY_CONSULTATION":
                if message_to_recipient:
                    target = get_target_from_recipient()
                    logger.info(
                        f"[{self.agent_id}] {action_type} -> sending to {target} (message_recipient={message_recipient})"
                    )

                    action_params = {
                        "agent_name": self.agent_id,
                        "target_agent": target,
                        "message_content": message_to_recipient,
                    }
                    if target.startswith("Doctor"):
                        action_params["metadata"] = {
                            "patient_id": patient_id,
                            "message_type": (
                                "consultation_reply" if action_type == "REPLY_CONSULTATION" else "doctor_message"
                            ),
                        }
                    actions.append(
                        {
                            "action_name": "send_message",
                            "component_name": "communication",
                            "parameters": action_params,
                            "tick_consumption": 1,
                        }
                    )

            elif action_type == "REQUEST_CONSULTATION":
                if is_consultant:
                    logger.warning(
                        f"[{self.agent_id}] Consultant attempted REQUEST_CONSULTATION for {patient_id}. "
                        f"Converting to REPLY_CONSULTATION instead."
                    )
                    if message_to_recipient:
                        action_params = {
                            "agent_name": self.agent_id,
                            "target_agent": partner_id,                             
                            "message_content": message_to_recipient,
                            "metadata": {
                                "patient_id": patient_id,
                                "message_type": "consultation_reply",
                            },
                        }
                        actions.append(
                            {
                                "action_name": "send_message",
                                "component_name": "communication",
                                "parameters": action_params,
                                "tick_consumption": 1,
                            }
                        )
                else:
                    consultation_reason = decision.get("consultation_reason", message_to_recipient)
                    selected_consultant, consultation_message = await self._select_consultant(
                        patient_id, consultation_reason, chat_history, exam_results
                    )

                    if selected_consultant and consultation_message:
                        consultation_metadata = {
                            "patient_id": patient_id,
                            "message_type": "consultation_request",
                        }
                        actions.append(
                            {
                                "action_name": "send_message",
                                "component_name": "communication",
                                "parameters": {
                                    "agent_name": self.agent_id,
                                    "target_agent": selected_consultant,
                                    "message_content": consultation_message,
                                    "metadata": consultation_metadata,
                                },
                                "tick_consumption": 1,
                            }
                        )
                        logger.info(
                            f"[{self.agent_id}] 📤 Sending consultation to {selected_consultant} for {patient_id}"
                        )

            elif action_type == "ORDER_EXAMINATION":
                if is_consultant:
                    logger.warning(f"[{self.agent_id}] Consultant attempted ORDER_EXAMINATION. Ignoring.")
                    if message_to_recipient:
                        actions.append(
                            {
                                "action_name": "send_message",
                                "component_name": "communication",
                                "parameters": {
                                    "agent_name": self.agent_id,
                                    "target_agent": partner_id,
                                    "message_content": message_to_recipient,
                                    "metadata": {
                                        "patient_id": patient_id,
                                        "message_type": "consultation_reply",
                                    },
                                },
                                "tick_consumption": 1,
                            }
                        )
                else:
                    examination_list = decision.get("examination_list", [])
                    selected_exams, exam_message = await self._select_examinations(
                        patient_id, examination_list, chat_history, exam_results
                    )

                    if selected_exams:
                        actions.append(
                            {
                                "action_name": "schedule_examination",
                                "component_name": "tools",
                                "parameters": {
                                    "agent_name": self.agent_id,
                                    "patient_id": patient_id,
                                    "examination_items": selected_exams,
                                    "reason": ", ".join(examination_list) if examination_list else "Doctor decision",
                                },
                                "tick_consumption": 1,
                            }
                        )
                        self._active_patients[patient_id]["examinations_ordered"] = True
                        if "examination_items" not in self._active_patients[patient_id]:
                            self._active_patients[patient_id]["examination_items"] = []
                        self._active_patients[patient_id]["examination_items"].extend(selected_exams)
                    final_message = exam_message
                    if not final_message and selected_exams:
                        final_message = f"I'm ordering the following examinations for you: {', '.join(selected_exams)}. Please wait for the results."

                    if final_message:
                        logger.info(f"[{self.agent_id}] ORDER_EXAMINATION message -> sending to patient {patient_id}")
                        actions.append(
                            {
                                "action_name": "send_message",
                                "component_name": "communication",
                                "parameters": {
                                    "agent_name": self.agent_id,
                                    "target_agent": patient_id,
                                    "message_content": final_message,
                                },
                                "tick_consumption": 1,
                            }
                        )

            elif action_type == "SEARCH_KNOWLEDGE":
                query = decision.get("knowledge_query", "")
                if query:
                    self._consecutive_knowledge_searches[patient_id] = (
                        self._consecutive_knowledge_searches.get(patient_id, 0) + 1
                    )

                    logger.info(
                        f"[{self.agent_id}] Consecutive knowledge search #{self._consecutive_knowledge_searches[patient_id]} "
                        f"for {patient_id}, query: '{query}'"
                    )
                    self._pending_knowledge_query = {
                        "patient_id": patient_id,
                        "partner_id": partner_id,
                        "message_content": message_content,
                        "query": query,
                        "tick_initiated": self.global_tick,
                    }

                    actions.append(
                        {
                            "action_name": "search_medical_knowledge",
                            "component_name": "tools",
                            "parameters": {"agent_name": self.agent_id, "query": query, "top_k": 5},
                            "tick_consumption": 1,
                        }
                    )
                if message_to_recipient:
                    search_message_target = get_target_from_recipient()
                    logger.info(
                        f"[{self.agent_id}] SEARCH_KNOWLEDGE message -> sending to {search_message_target} (message_recipient={message_recipient})"
                    )
                    send_params = {
                        "agent_name": self.agent_id,
                        "target_agent": search_message_target,
                        "message_content": message_to_recipient,
                    }
                    if search_message_target.startswith("Doctor"):
                        send_params["metadata"] = {
                            "patient_id": patient_id,
                            "message_type": "doctor_message",
                        }
                    actions.append(
                        {
                            "action_name": "send_message",
                            "component_name": "communication",
                            "parameters": send_params,
                            "tick_consumption": 1,
                        }
                    )

            elif action_type == "MAKE_DIAGNOSIS":
                if is_consultant:
                    logger.warning(
                        f"[{self.agent_id}] Consultant attempted MAKE_DIAGNOSIS for {patient_id}. "
                        f"Converting to REPLY_CONSULTATION instead."
                    )
                    if message_to_recipient:
                        action_params = {
                            "agent_name": self.agent_id,
                            "target_agent": partner_id,                                          
                            "message_content": message_to_recipient,
                            "metadata": {
                                "patient_id": patient_id,
                                "message_type": "consultation_reply",
                            },
                        }
                        actions.append(
                            {
                                "action_name": "send_message",
                                "component_name": "communication",
                                "parameters": action_params,
                                "tick_consumption": 1,
                            }
                        )
                else:
                    diagnosis_reasoning = decision.get("diagnosis_reasoning", "")
                    is_comorbidity = decision.get("is_comorbidity", False)
                    comorbidity_reason = decision.get("comorbidity_reason", "")

                    if is_comorbidity:
                        logger.info(f"[{self.agent_id}] Comorbidity detected for {patient_id}: {comorbidity_reason}")
                        selected_departments = await self._select_departments_for_comorbidity(
                            patient_id, diagnosis_reasoning, comorbidity_reason
                        )

                        if selected_departments and len(selected_departments) >= 2:
                            diagnosis, treatment_plan, diagnosis_message = await self._select_diagnosis(
                                patient_id,
                                diagnosis_reasoning,
                                chat_history,
                                exam_results,
                                department=None,                                         
                                selected_departments=selected_departments,
                                is_comorbidity=True,
                            )
                        else:
                            logger.warning(
                                f"[{self.agent_id}] Comorbidity department selection failed, falling back to single department"
                            )
                            diagnosis, treatment_plan, diagnosis_message = await self._select_diagnosis(
                                patient_id, diagnosis_reasoning, chat_history, exam_results, department
                            )
                    else:
                        diagnosis, treatment_plan, diagnosis_message = await self._select_diagnosis(
                            patient_id, diagnosis_reasoning, chat_history, exam_results, department
                        )

                    if diagnosis and treatment_plan:
                        actions.append(
                            {
                                "action_name": "prescribe_treatment",
                                "component_name": "tools",
                                "parameters": {
                                    "agent_name": self.agent_id,
                                    "patient_id": patient_id,
                                    "diagnosis": diagnosis,
                                    "treatment_plan": treatment_plan,
                                },
                                "tick_consumption": 1,
                            }
                        )

                        self._active_patients[patient_id]["diagnosis_made"] = True
                        self._active_patients[patient_id]["diagnosis"] = diagnosis
                        self._active_patients[patient_id]["treatment_plan"] = treatment_plan
                        self._active_patients[patient_id]["consultation_ended"] = self.global_tick
                        self._treated_patients.add(patient_id)
                        logger.info(f"[{self.agent_id}] ✅ Completed treatment for {patient_id}")
                        logger.info(f"All treated patients: {self._treated_patients}")
                        self._patients_pending_reflection.append(patient_id)

                        record = {
                            "patient_id": patient_id,
                            "diagnosis": diagnosis,
                            "treatment_plan": treatment_plan,
                            "consultation_ended": self.global_tick,
                            "examination_items": self._active_patients.get(patient_id, {}).get("examination_items", []),
                        }
                        self._completed_consultations.append(record)
                    if diagnosis_message:
                        logger.info(f"[{self.agent_id}] Sending diagnosis to patient {patient_id}")
                        actions.append(
                            {
                                "action_name": "send_message",
                                "component_name": "communication",
                                "parameters": {
                                    "agent_name": self.agent_id,
                                    "target_agent": patient_id,
                                    "message_content": diagnosis_message,
                                },
                                "tick_consumption": 1,
                            }
                        )

            elif action_type:
                logger.warning(f"[{self.agent_id}] Unsupported action from Stage 1: {action_type}")

        except Exception as e:
            logger.error(f"Failed to generate consultation response: {e}", exc_info=True)
            error_params = {
                "agent_name": self.agent_id,
                "target_agent": partner_id,
                "message_content": "I need more time to think.",
            }
            if partner_id.startswith("Doctor"):
                error_params["metadata"] = {
                    "patient_id": patient_id,
                    "message_type": "doctor_message",
                }
            actions.append(
                {
                    "action_name": "send_message",
                    "component_name": "communication",
                    "parameters": error_params,
                    "tick_consumption": 1,
                }
            )

        return actions

    def _build_consultant_prompt_stage1(
        self,
        department: str,
        partner_id: str,
        patient_id: str,
        optional_context: str,
        exam_results_instruction: str,
    ) -> str:
        """Build simplified prompt for consultant (Stage 1)."""
        return f"""You are a doctor in the {department}.

You are currently communicating with: {partner_id} (the PRIMARY doctor who requested your consultation) regarding patient: {patient_id}.
Context: {optional_context}
You are providing consultation to another doctor ({partner_id}). 

**⚠️ CRITICAL RULES:**
- You MUST reply ONLY to {partner_id} (the requesting doctor)
- You CANNOT and MUST NOT communicate directly with the patient ({patient_id})
- Your message_to_recipient will be sent to {partner_id}, NOT to the patient

You can ONLY:
- Provide professional advice and recommendations to {partner_id}
- Suggest examinations or questions the PRIMARY doctor should order/ask
- Share your expert opinion with the PRIMARY doctor

You CANNOT:
- Directly communicate with the patient
- Directly order examinations (only suggest them to the primary doctor)
- Make final diagnosis (only provide consultation opinion to the primary doctor)
1. REPLY_CONSULTATION - Reply to {partner_id}'s consultation request with advice
2. SEARCH_KNOWLEDGE - Search medical knowledge base
As a consultant, you MUST always set "message_recipient": "doctor" because you can ONLY communicate with the requesting doctor ({partner_id}), never the patient.
{{
    "action": "REPLY_CONSULTATION|SEARCH_KNOWLEDGE",
    "message_to_recipient": "Your consultation advice to {partner_id} (the requesting doctor, NOT the patient)",
    "message_recipient": "doctor",
    "knowledge_query": "query (if SEARCH_KNOWLEDGE)"
}}
- **KEEP IT CONCISE**: Maximum 100 words per message.
- **BE NATURAL**: Write like a real doctor colleague.
- **BE HELPFUL**: Give specific, actionable suggestions.
- **BE POLITE & COLLABORATIVE**: Use respectful colleague-to-colleague language.
{exam_results_instruction}
"""

    def _build_primary_doctor_prompt_stage1(
        self,
        department: str,
        partner_id: str,
        patient_id: str,
        optional_context: str,
        consultation_reply_instruction: str,
        exam_results_instruction: str,
        knowledge_search_warning: str = "",
        doctor_reply_warning: str = "",
    ) -> str:
        """Build simplified prompt for primary doctor (Stage 1)."""

        return f"""You are a doctor in the {department}.

You are currently communicating with: {partner_id} regarding patient: {patient_id}.
Context: {optional_context}
{consultation_reply_instruction}
{knowledge_search_warning}
{doctor_reply_warning}
You are the primary doctor for this patient. You have full authority to:
- Order examinations
- Ask the patient questions
- Request consultations from specialists
- Make diagnosis and treatment decisions
1. ASK_QUESTION - Ask the patient for more information
2. ORDER_EXAMINATION - Order medical examinations (message will be generated in next step)
3. SEARCH_KNOWLEDGE - Search medical knowledge base
4. MAKE_DIAGNOSIS - Provide diagnosis and treatment plan (message will be generated in next step)
5. REQUEST_CONSULTATION - Ask a colleague for advice (you will select specific colleague in next step)
6. REPLY_CONSULTATION - Reply to a colleague's consultation request
- For ORDER_EXAMINATION and MAKE_DIAGNOSIS: Do NOT provide "message_to_recipient" or "message_recipient" - the message will be generated in the next step
- For other actions: Specify "message_recipient" to indicate WHO should receive your message:
  - "patient" - Send to the patient ({patient_id}). Use for: asking questions, updating after consultation.
  - "doctor" - Send to the colleague ({partner_id}). Use for: replying to consultation requests.
  - Specific doctor ID (e.g., "Doctor_Dermatology_001") - Send to a specific colleague from consultation history. Use for: forwarding patient info, continuing multi-step consultations.
{{
    "action": "ASK_QUESTION|ORDER_EXAMINATION|SEARCH_KNOWLEDGE|MAKE_DIAGNOSIS|REQUEST_CONSULTATION|REPLY_CONSULTATION",
    "message_to_recipient": "Your message (omit for ORDER_EXAMINATION and MAKE_DIAGNOSIS)",
    "message_recipient": "patient|doctor|specific_doctor_id (omit for ORDER_EXAMINATION and MAKE_DIAGNOSIS)",
    "examination_list": ["exam1", "exam2", "..."] (required for ORDER_EXAMINATION - list of examination types you want to order),
    "diagnosis_reasoning": "Your reasoning for the diagnosis (required for MAKE_DIAGNOSIS)",
    "is_comorbidity": true/false (required for MAKE_DIAGNOSIS - see comorbidity note below),
    "comorbidity_reason": "If is_comorbidity=true, explain why you suspect comorbidity and which other department(s) might be involved",
    "consultation_reason": "Why you need consultation and what specialty (if REQUEST_CONSULTATION)",
    "knowledge_query": "query (if SEARCH_KNOWLEDGE)"
}}
Comorbidity means the patient has MULTIPLE diseases for THIS visit (can be same or different departments).
- ✅ Comorbidity: Patient has both heart palpitations AND respiratory symptoms → two current conditions
- ✅ Comorbidity: Patient has two different heart conditions (e.g., arrhythmia AND heart failure) → same department, two diseases
- ❌ NOT Comorbidity: Patient has diabetes history but comes for a skin rash → only diagnose the current complaint
**When talking to PATIENTS (message_recipient: "patient"):**
- **KEEP IT SIMPLE**: Maximum 100 words. Use everyday language.
- **BE WARM & EMPATHETIC**: Show you care.
- **ONE THING AT A TIME**: Don't overwhelm them.

**GENERAL RULES:**
- **PROACTIVELY REQUEST CONSULTATION**: If the patient's symptoms and descriptions are outside your specialty's scope, actively communicate with doctors from other departments for consultation.
- **MUST CONSULT**: If there is any diagnostic uncertainty or multi-system involvement, you MUST request a consultation from another doctor before making a diagnosis.
- When ordering exams, explain WHY in simple terms to the patient.
- Only diagnose after you have exam results. Don't rush.
{exam_results_instruction}
"""

    async def _select_consultant(
        self, patient_id: str, consultation_reason: str, chat_history: List[Dict], exam_results: List[Dict]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Stage 2: Select a specific consultant from available colleagues.
        Returns (consultant_id, consultation_message).
        """
        colleagues = []
        try:
            relationships = await self.controller.run_environment(
                "relation", "get_agent_relationships", agent_id=self.agent_id, edge_type="colleague"
            )
            if relationships and "nodes" in relationships:
                for node_id, node_data in relationships["nodes"].items():
                    if isinstance(node_data, dict):
                        props = node_data.get("properties", node_data)
                        name = props.get("name", node_id)
                        dept = props.get("department", "Unknown")
                        colleagues.append(f"{node_id}: {name} ({dept})")
        except Exception as e:
            logger.warning(f"Failed to get colleagues: {e}")
            return None, None

        if not colleagues:
            logger.error(f"❌ No colleagues found for {self.agent_id}")
            return None, None

        consultant_ids = [item.split(":", 1)[0].strip() for item in colleagues]
        system_prompt = f"""You need to select a consultant for a patient case.
{consultation_reason}
{chr(10).join(colleagues)}
{chr(10).join(f"- {consultant_id}" for consultant_id in consultant_ids)}

IMPORTANT specialty mapping hints when ideal specialty is unavailable:
- Rheumatology → Immunology
- Psychiatry → Neurology
1. Select the MOST appropriate consultant based on the consultation reason
2. Write a natural consultation request message in normal clinical language (max 120 words)
   - Clearly summarize the key patient context
   - Ask focused consultation question(s) as needed (one or more is allowed)
   - Questions should target consultant input such as: likely diagnosis/differentials, recommended examinations, and treatment or management options
   - Use polite colleague-to-colleague wording
   - Do NOT command the consultant to place urgent orders; ask for recommendations and priorities instead
{{
    "selected_consultant_id": "Doctor_XXX_NNN (exact ID from the list)",
    "consultation_message": "Your consultation request message"
}}

IMPORTANT: Use the EXACT consultant ID from the list above (e.g., "Doctor_Cardiology_001").
"""

        max_attempts = 3
        failed_cases: List[Dict[str, Any]] = []

        for attempt in range(1, max_attempts + 1):
            user_payload: Dict[str, Any] = {
                "patient_id": patient_id,
                "consultation_reason": consultation_reason,
                "available_consultant_ids": consultant_ids,
                "recent_conversation": chat_history[-3:] if chat_history else [],
                "exam_results_summary": (
                    [{"items": e.get("examination_items", []), "status": e.get("status")} for e in exam_results]
                    if exam_results
                    else []
                ),
            }
            if failed_cases:
                user_payload["previous_failed_cases"] = failed_cases
                user_payload["retry_requirement"] = (
                    "Do not repeat invalid consultant IDs from previous_failed_cases. Output valid JSON and pick an exact ID from available_consultant_ids."
                )

            user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)

            try:
                response = await self.model.chat(user_prompt, system_prompt=system_prompt)
                save_prompt(
                    agent_id=self.agent_id,
                    tick=self.global_tick,
                    context_id=patient_id,
                    stage=f"select_consultant_attempt{attempt}",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response=response,
                    plugin_logger=logger,
                )

                response_clean = clean_json_response(response)
                decision = json.loads(response_clean)
            except Exception as e:
                failed_case = {
                    "attempt": attempt,
                    "failure_reason": "invalid_response_format",
                    "error": str(e),
                }
                failed_cases.append(failed_case)
                logger.warning(
                    f"[{self.agent_id}] Consultant selection attempt {attempt}/{max_attempts} failed to parse response: {e}"
                )
                continue

            consultant_id = str(decision.get("selected_consultant_id", "")).strip()
            message = str(decision.get("consultation_message", "")).strip()

            if not consultant_id:
                failed_case = {
                    "attempt": attempt,
                    "failure_reason": "missing_consultant_id",
                    "model_output": decision,
                }
                failed_cases.append(failed_case)
                logger.warning(
                    f"[{self.agent_id}] Consultant selection attempt {attempt}/{max_attempts} missing selected_consultant_id"
                )
                continue

            if consultant_id not in consultant_ids:
                logger.warning(f"Invalid consultant ID '{consultant_id}', attempting to fix...")
                resolved_id = None
                for valid_id in consultant_ids:
                    if consultant_id.lower() in valid_id.lower() or valid_id.lower() in consultant_id.lower():
                        resolved_id = valid_id
                        break

                if resolved_id is None:
                    failed_case = {
                        "attempt": attempt,
                        "failure_reason": "invalid_consultant_id",
                        "selected_consultant_id": consultant_id,
                    }
                    failed_cases.append(failed_case)
                    logger.warning(
                        f"[{self.agent_id}] Consultant selection attempt {attempt}/{max_attempts} produced invalid ID '{consultant_id}'"
                    )
                    continue

                logger.warning(f"Mapped consultant ID '{consultant_id}' -> '{resolved_id}'")
                consultant_id = resolved_id

            if not message:
                failed_case = {
                    "attempt": attempt,
                    "failure_reason": "empty_consultation_message",
                    "selected_consultant_id": consultant_id,
                }
                failed_cases.append(failed_case)
                logger.warning(
                    f"[{self.agent_id}] Consultant selection attempt {attempt}/{max_attempts} returned empty consultation message"
                )
                continue

            return consultant_id, message

        logger.error(
            f"❌ [{self.agent_id}] Failed to select consultant for {patient_id} after {max_attempts} attempts. "
            f"Failed cases: {failed_cases}"
        )
        return None, None

    async def _select_departments_for_comorbidity(
        self,
        patient_id: str,
        diagnosis_reasoning: str,
        comorbidity_reason: str,
    ) -> Optional[List[str]]:
        """
        Stage 2a: Select two departments for comorbidity diagnosis.
        Returns list of 2 department names.
        """
        all_departments = []
        try:
            departments_data = await self.redis.get("hospital:departments")
            if departments_data:
                if isinstance(departments_data, list):
                    all_departments = departments_data
                elif isinstance(departments_data, dict):
                    all_departments = list(departments_data.keys())
        except Exception as e:
            logger.warning(f"Failed to load departments: {e}")

        if not all_departments:
            try:
                relationships = await self.controller.run_environment(
                    "relation", "get_agent_relationships", agent_id=self.agent_id, edge_type="colleague"
                )
                if relationships and "nodes" in relationships:
                    dept_set = set()
                    for _, node_data in relationships["nodes"].items():
                        if isinstance(node_data, dict):
                            props = node_data.get("properties", node_data)
                            dept = props.get("department", "")
                            if dept:
                                dept_set.add(dept)
                    all_departments = list(dept_set)
            except Exception as e:
                logger.warning(f"Failed to get departments from colleagues: {e}")

        if not all_departments:
            logger.error("No departments available for comorbidity selection")
            return None

        system_prompt = f"""Select TWO departments for a patient with comorbidity.
{diagnosis_reasoning}
{comorbidity_reason}
{chr(10).join(f"- {d}" for d in all_departments)}

IMPORTANT: If the ideal specialty is not listed, choose the closest alternative. For example:
- Rheumatology → Immunology Department
- Psychiatry → Neurology Department
{{
    "department_1": "exact name from list",
    "department_2": "exact name from list (can be same)"
}}"""

        user_prompt = json.dumps(
            {
                "patient_id": patient_id,
                "diagnosis_reasoning": diagnosis_reasoning,
                "comorbidity_reason": comorbidity_reason,
            },
            ensure_ascii=False,
            indent=2,
        )

        try:
            response = await self.model.chat(user_prompt, system_prompt=system_prompt)
            save_prompt(
                agent_id=self.agent_id,
                tick=self.global_tick,
                context_id=patient_id,
                stage="select_departments_comorbidity",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                plugin_logger=logger,
            )

            response_clean = clean_json_response(response)
            decision = json.loads(response_clean)

            dept_1 = decision.get("department_1", "")
            dept_2 = decision.get("department_2", "")

            def find_best_matching_department(response: str, valid_departments: List[str]) -> Optional[str]:
                """Find the best matching department using multiple strategies."""
                response_clean = response.strip()
                if response_clean in valid_departments:
                    return response_clean
                response_lower = response_clean.lower()
                for dept in valid_departments:
                    if dept.lower() == response_lower:
                        return dept
                for dept in valid_departments:
                    if response_lower in dept.lower() or dept.lower() in response_lower:
                        return dept
                response_words = set(response_lower.replace(" department", "").replace(" dept", "").split())
                best_match = None
                best_score = 0
                for dept in valid_departments:
                    dept_words = set(dept.lower().replace(" department", "").split())
                    overlap = len(response_words & dept_words)
                    if overlap > best_score:
                        best_score = overlap
                        best_match = dept

                if best_match and best_score > 0:
                    return best_match
                best_match = None
                best_ratio = 0.0
                for dept in valid_departments:
                    ratio = SequenceMatcher(None, response_lower, dept.lower()).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = dept
                if best_match and best_ratio > 0.5:
                    logger.info(
                        f"[{self.agent_id}] Fuzzy matched '{response_clean}' to '{best_match}' (similarity: {best_ratio:.2f})"
                    )
                    return best_match

                return None
            valid_departments = []
            for dept in [dept_1, dept_2]:
                matched = find_best_matching_department(dept, all_departments)
                if matched:
                    if matched != dept:
                        logger.info(f"[{self.agent_id}] Mapped '{dept}' to valid department '{matched}'")
                    valid_departments.append(matched)
                else:
                    logger.warning(f"[{self.agent_id}] Could not match department: {dept}")

            if len(valid_departments) >= 2:
                logger.info(f"[{self.agent_id}] Selected departments for comorbidity: {valid_departments[:2]}")
                return valid_departments[:2]
            else:
                logger.warning(f"[{self.agent_id}] Could not validate 2 departments: {dept_1}, {dept_2}")
                return None

        except Exception as e:
            logger.error(f"Failed to select departments for comorbidity: {e}")
            return None

    async def _select_examinations(
        self,
        patient_id: str,
        examination_list: List[str],
        chat_history: List[Dict],
        exam_results: List[Dict],
    ) -> Tuple[List[str], Optional[str]]:
        """
        Stage 2: Select specific examinations using Milvus vector search.
        Returns (selected_exam_list, message_to_patient).

        For each item in examination_list, performs a vector search to find top 3
        relevant examinations, then has LLM select from the combined candidates.
        This approach provides more accurate matching than a single intent query.
        """
        candidate_exams = []
        seen_exam_names = set()                    

        if self.examinations_vectordb is None:
            logger.error("Examinations vectordb not configured")
            return [], None
        if not examination_list or not isinstance(examination_list, list):
            examination_list = ["general medical examination"]

        try:
            for exam_query in examination_list:
                search_request = VectorSearchRequest(
                    query=exam_query,
                    top_k=3,                            
                )
                search_results = await self.examinations_vectordb.search(search_request)

                if search_results:
                    for result in search_results:
                        metadata = result.document.metadata
                        exam_name = metadata.get("exam_name", "")
                        exam_description = metadata.get("exam_description", "")
                        if exam_name and exam_name not in seen_exam_names:
                            candidate_exams.append(
                                {
                                    "name": exam_name,
                                    "description": exam_description,
                                    "score": result.score,
                                    "matched_query": exam_query,
                                }
                            )
                            seen_exam_names.add(exam_name)

            logger.info(
                f"Retrieved {len(candidate_exams)} candidate examinations via vector search for {len(examination_list)} queries"
            )
        except Exception as e:
            logger.error(f"Vector search failed: {e}")

        if not candidate_exams:
            logger.error("No examination candidates available")
            return [], None
        exam_lines = []
        valid_exam_names = set()
        for exam in candidate_exams:
            name = exam.get("name", "")
            desc = exam.get("description", "")
            exam_lines.append(f"- {name}: {desc}")
            valid_exam_names.add(name)
        examination_list_str = ", ".join(examination_list) if examination_list else "general examination"
        system_prompt = f"""You need to select specific medical examinations for a patient.
{examination_list_str}
{chr(10).join(exam_lines)}
1. Select the MOST appropriate examinations (1-5 items) based on the requested examinations
2. Write a brief, warm message to the patient explaining why you're ordering these tests
{{
    "selected_examinations": ["Exact Exam Name 1", "Exact Exam Name 2"],
    "message_to_patient": "Your warm, simple explanation to the patient (max 100 words)"
}}

CRITICAL RULES:
- You MUST select AT LEAST 1 examination from the list above
- You MUST return ONLY examination NAMES, NOT descriptions (e.g., "Complete Blood Count", not "Complete Blood Count: a test that...")
- You MUST use EXACT examination names from the list (copy and paste)
- Do not make up or modify examination names
"""

        user_prompt = json.dumps(
            {
                "patient_id": patient_id,
                "requested_examinations": examination_list,
                "recent_conversation": chat_history[-3:] if chat_history else [],
                "already_ordered_exams": (
                    [item for e in exam_results for item in e.get("examination_items", [])] if exam_results else []
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = await self.model.chat(user_prompt, system_prompt=system_prompt)
                save_prompt(
                    agent_id=self.agent_id,
                    tick=self.global_tick,
                    context_id=patient_id,
                    stage=f"select_exams_attempt{attempt}",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response=response,
                    plugin_logger=logger,
                )

                response_clean = clean_json_response(response)
                decision = json.loads(response_clean)

                selected_exams = decision.get("selected_examinations", [])
                message = decision.get("message_to_patient", "")
                validated_exams = []
                for valid_exam in valid_exam_names:
                    if valid_exam in selected_exams:
                        validated_exams.append(valid_exam)
                    else:
                        for selected_exam in selected_exams:
                            if valid_exam in selected_exam:
                                validated_exams.append(valid_exam)
                                break

                if not validated_exams:
                    logger.error(
                        f"Attempt {attempt}: None of the selected exams matched candidates. "
                        f"Selected: {selected_exams}, Valid candidates: {valid_exam_names}"
                    )
                    if attempt < max_retries:
                        system_prompt += (
                            f"\n\nERROR: Your selected examinations must be EXACTLY from the list above. "
                            f"Invalid names: {set(selected_exams) - valid_exam_names}. "
                            f"Please copy names EXACTLY from the list."
                        )
                        continue

                logger.info(f"Successfully selected {len(validated_exams)} examinations: {validated_exams}")
                return validated_exams, message

            except Exception as e:
                logger.error(f"Attempt {attempt}: Failed to select examinations: {e}")
                if attempt == max_retries:
                    return [], None

        return [], None

    async def _select_diagnosis(
        self,
        patient_id: str,
        diagnosis_reasoning: str,
        chat_history: List[Dict],
        exam_results: List[Dict],
        department: str,
        selected_departments: Optional[List[str]] = None,
        is_comorbidity: bool = False,
    ) -> Tuple[Optional[Any], Optional[str], Optional[str]]:
        """
        Stage 2/3: Select specific diagnosis from department diseases.
        Returns (diagnosis, treatment_plan, message_to_patient).

        For single disease: diagnosis is a string
        For comorbidity: diagnosis is a list of strings (e.g., ["Disease1", "Disease2"])

        For comorbidity cases:
        - selected_departments: List of 2 departments to select diseases from
        - is_comorbidity: True if this is a comorbidity case
        - diagnosis will be a comma-separated string of 2 diseases
        """
        diseases_by_dept = {}                             
        is_same_department = False                                                   
        if is_comorbidity and selected_departments and len(selected_departments) >= 2:
            is_same_department = selected_departments[0] == selected_departments[1]
            all_diseases = []

            if is_same_department:
                dept_diseases = await self.get_diseases_by_department(selected_departments[0])
                if dept_diseases:
                    diseases_by_dept[selected_departments[0]] = dept_diseases
                    all_diseases = dept_diseases
            else:
                for dept in selected_departments[:2]:
                    dept_diseases = await self.get_diseases_by_department(dept)
                    if dept_diseases:
                        diseases_by_dept[dept] = dept_diseases
                        all_diseases.extend(dept_diseases)

            if not all_diseases:
                all_diseases = ["Condition requiring further evaluation"]
            disease_list_str = ""
            for dept, diseases in diseases_by_dept.items():
                disease_list_str += f"\n### {dept}\n"
                disease_list_str += "\n".join(f"- {d}" for d in diseases)
        else:
            diseases = await self.get_diseases_by_department(department)
            if not diseases:
                diseases = ["Condition requiring further evaluation"]
            all_diseases = diseases
            disease_list_str = "\n".join(f"- {d}" for d in diseases)
        exam_summary = ""
        if exam_results:
            result_lines = []
            for exam in exam_results:
                results = exam.get("results", {})
                for item_name, item_data in results.items():
                    if isinstance(item_data, dict):
                        result_text = item_data.get("result", str(item_data))
                        result_lines.append(f"  - {item_name}: {result_text}")
            exam_summary = "\n".join(result_lines)
        if is_comorbidity and selected_departments:
            if is_same_department:
                task_description = f"""## Task (COMORBIDITY - Select TWO DIFFERENT diseases from the SAME department)
1. Select ONE disease from {selected_departments[0]}
2. Select ANOTHER DIFFERENT disease from {selected_departments[0]}
3. The two diseases MUST be different
4. Create a comprehensive treatment plan addressing BOTH conditions
5. Write a warm, clear message to the patient explaining both diagnoses"""
                response_format = f"""## Response Format (JSON)
{{
    "diagnosis_1": "MUST be exactly one item from {selected_departments[0]} list",
    "diagnosis_2": "MUST be a DIFFERENT item from {selected_departments[0]} list",
    "treatment_plan": "Comprehensive treatment plan addressing BOTH conditions, including medications, lifestyle changes, follow-up",
    "message_to_patient": "Your warm, clear explanation to the patient about both conditions (max 200 words)"
}}

NOTE: You MUST choose TWO DIFFERENT diagnoses from the list above verbatim. Do NOT add extra words, abbreviations, or notes."""
            else:
                task_description = f"""## Task (COMORBIDITY - Select TWO diseases from DIFFERENT departments)
1. Select ONE disease from {selected_departments[0]}
2. Select ONE disease from {selected_departments[1]}
3. Create a comprehensive treatment plan addressing BOTH conditions
4. Write a warm, clear message to the patient explaining both diagnoses"""
                response_format = f"""## Response Format (JSON)
{{
    "diagnosis_1": "MUST be exactly one item from {selected_departments[0]} list",
    "diagnosis_2": "MUST be exactly one item from {selected_departments[1]} list",
    "treatment_plan": "Comprehensive treatment plan addressing BOTH conditions, including medications, lifestyle changes, follow-up",
    "message_to_patient": "Your warm, clear explanation to the patient about both conditions (max 200 words)"
}}

NOTE: You MUST choose diagnoses from the lists above verbatim. Do NOT add extra words, abbreviations, or notes."""

            system_prompt = f"""You need to make a COMORBIDITY diagnosis for a patient with multiple conditions.
{diagnosis_reasoning}
{exam_summary if exam_summary else "No examination results available"}
{disease_list_str}

{task_description}

{response_format}
"""
        else:
            system_prompt = f"""You need to make a diagnosis for a patient.
{diagnosis_reasoning}
{exam_summary if exam_summary else "No examination results available"}
{disease_list_str}
1. Select the MOST appropriate diagnosis based on the reasoning and exam results
2. Create a specific treatment plan
3. Write a warm, clear message to the patient explaining the diagnosis and plan
{{
    "diagnosis": "MUST be exactly one item from the list above",
    "treatment_plan": "Detailed treatment plan including medications, lifestyle changes, follow-up",
    "message_to_patient": "Your warm, clear explanation to the patient (max 150 words)"
}}

NOTE: You MUST choose a diagnosis from the list above verbatim. Do NOT add extra words, abbreviations, or notes.
"""

        user_prompt = json.dumps(
            {
                "patient_id": patient_id,
                "diagnosis_reasoning": diagnosis_reasoning,
                "recent_conversation": chat_history[-5:] if chat_history else [],
                "exam_results": (
                    [{"items": e.get("examination_items", []), "results": e.get("results", {})} for e in exam_results]
                    if exam_results
                    else []
                ),
                "is_comorbidity": is_comorbidity,
                "selected_departments": selected_departments if is_comorbidity else None,
            },
            ensure_ascii=False,
            indent=2,
        )

        try:
            stage_name = "select_diagnosis_comorbidity" if is_comorbidity else "select_diagnosis"
            response = await self.model.chat(user_prompt, system_prompt=system_prompt)
            save_prompt(
                agent_id=self.agent_id,
                tick=self.global_tick,
                context_id=patient_id,
                stage=stage_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                plugin_logger=logger,
            )

            response_clean = clean_json_response(response)
            decision = json.loads(response_clean)

            if is_comorbidity and selected_departments:
                diagnosis_1 = decision.get("diagnosis_1", "")
                diagnosis_2 = decision.get("diagnosis_2", "")
                dept_1_diseases = diseases_by_dept.get(selected_departments[0], [])
                dept_2_diseases = diseases_by_dept.get(
                    selected_departments[1], dept_1_diseases
                )                                          

                if diagnosis_1 and dept_1_diseases:
                    diagnosis_1 = self._normalize_diagnosis_to_list(diagnosis_1, dept_1_diseases)
                if diagnosis_2 and dept_2_diseases:
                    diagnosis_2 = self._normalize_diagnosis_to_list(diagnosis_2, dept_2_diseases)
                if diagnosis_1 and diagnosis_2:
                    diagnosis = [diagnosis_1, diagnosis_2]
                elif diagnosis_1:
                    diagnosis = [diagnosis_1]
                elif diagnosis_2:
                    diagnosis = [diagnosis_2]
                else:
                    diagnosis = []
                treatment_plan = decision.get("treatment_plan", "")
                message = decision.get("message_to_patient", "")

                logger.info(f"[{self.agent_id}] Comorbidity diagnosis (same_dept={is_same_department}): {diagnosis}")
            else:
                diagnosis = decision.get("diagnosis", "")
                if diagnosis and all_diseases:
                    diagnosis = self._normalize_diagnosis_to_list(diagnosis, all_diseases)
                treatment_plan = decision.get("treatment_plan", "")
                message = decision.get("message_to_patient", "")

            return diagnosis, treatment_plan, message

        except Exception as e:
            logger.error(f"Failed to select diagnosis: {e}")
            return None, None, None

    def _normalize_diagnosis_to_list(self, diagnosis: str, diseases: List[str]) -> str:
        """Normalize diagnosis to the closest item in the provided diseases list."""
        if not diagnosis or not diseases:
            return diagnosis

        diagnosis_clean = diagnosis.strip()
        if diagnosis_clean in diseases:
            return diagnosis_clean

        lower_map = {d.lower(): d for d in diseases}
        lower_key = diagnosis_clean.lower()
        if lower_key in lower_map:
            return lower_map[lower_key]

        for d in diseases:
            d_lower = d.lower()
            if lower_key in d_lower or d_lower in lower_key:
                return d

        try:
            return max(
                diseases,
                key=lambda d: SequenceMatcher(None, lower_key, d.lower()).ratio(),
            )
        except Exception:
            return diseases[0]

    def _get_consultation_history_for_patient(
        self, patient_id: str, exclude_partner: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取与特定患者相关的所有会诊对话历史。

        Args:
            patient_id: 患者 ID
            exclude_partner: 要排除的对话伙伴 ID（通常是当前对话伙伴，避免重复）

        Returns:
            Dict: {
                "Doctor_Dermatology_001": [与该会诊医生的对话],
                "Doctor_Endocrinology_002": [与该会诊医生的对话],
                ...
            }
        """
        perceive_plugin = self._get_perceive_plugin()
        if not perceive_plugin:
            return {}

        consultation_history = {}
        if patient_id in perceive_plugin._doctor_consultation_history:
            for doctor_id in perceive_plugin._doctor_consultation_history[patient_id]:
                if doctor_id != exclude_partner and doctor_id != self.agent_id:
                    messages = perceive_plugin.get_doctor_consultation_history(patient_id, doctor_id=doctor_id, count=5)
                    if messages:
                        consultation_history[doctor_id] = messages
                        logger.debug(
                            f"[{self.agent_id}] Found {len(messages)} consultation messages with {doctor_id} for patient {patient_id}"
                        )

        return consultation_history

    async def _get_basic_consultation_context(
        self, patient_id: str, message_content: str, partner_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Gather basic context needed for Stage 1 decision-making.
        Does NOT include detailed lists (colleagues, examinations, diseases).
        """
        if partner_id is None:
            partner_id = patient_id

        context = {}
        profile_plugin = self._get_profile_plugin()
        profile = profile_plugin._profile_data if profile_plugin else {}
        context["department"] = profile.get("department", "")
        perceive_plugin = self._get_perceive_plugin()
        if partner_id.startswith("Doctor_"):
            context["chat_history_with_partner"] = (
                perceive_plugin.get_doctor_consultation_history(patient_id, doctor_id=partner_id, count=10)
                if perceive_plugin
                else []
            )
        else:
            context["chat_history_with_partner"] = (
                perceive_plugin.get_patient_chat_history(partner_id, count=10) if perceive_plugin else []
            )
        context["chat_history_with_patient"] = (
            perceive_plugin.get_patient_chat_history(patient_id, count=10) if perceive_plugin else []
        )
        context["consultation_history"] = self._get_consultation_history_for_patient(
            patient_id, exclude_partner=partner_id
        )
        context["chat_history"] = context["chat_history_with_partner"]
        try:
            context["exam_results"] = await self.controller.run_environment(
                "hospital_system", "get_examination_results", patient_id=patient_id
            )
        except Exception:
            context["exam_results"] = []
        consultation_state = self._active_patients.get(patient_id, {})
        context["messages_received"] = consultation_state.get("messages_received", 1)
        context["examinations_ordered"] = consultation_state.get("examinations_ordered", False)
        invoke_plugin = self._get_invoke_plugin()
        last_result = invoke_plugin.last_action_result if invoke_plugin else None
        if last_result and last_result.get("action_name"):
            action_name = last_result.get("action_name", "")
            if "search" in action_name.lower() or "knowledge" in action_name.lower():
                should_load_knowledge = False
                if self._pending_knowledge_query:
                    pending_patient_id = self._pending_knowledge_query.get("patient_id")
                    if pending_patient_id == patient_id:
                        should_load_knowledge = True
                        logger.debug(
                            f"[{self.agent_id}] Loading knowledge results for pending query of patient {patient_id}"
                        )
                    else:
                        logger.debug(
                            f"[{self.agent_id}] Skipping knowledge results - for different patient {pending_patient_id} vs {patient_id}"
                        )
                else:
                    logger.debug(
                        f"[{self.agent_id}] Skipping knowledge results - no pending query for patient {patient_id}"
                    )

                if should_load_knowledge:
                    data = last_result.get("data", {})
                    if isinstance(data, dict) and data.get("results"):
                        results = data.get("results", [])[:3]
                        knowledge_lines = ["## Recent Knowledge Search Results"]
                        for r in results:
                            if isinstance(r, dict):
                                knowledge_lines.append(f"- {r.get('content', r.get('text', str(r)[:200]))}")
                            else:
                                knowledge_lines.append(f"- {str(r)[:200]}")
                        context["knowledge_results"] = "\n".join(knowledge_lines)
        reflect_plugin = self._get_reflect_plugin()
        if reflect_plugin:
            clinical_msgs = []
            seen_clinical_msgs = set()

            def add_clinical_msg(raw_msg: Any, fallback_speaker: str = "") -> None:
                if isinstance(raw_msg, dict):
                    content_text = str(raw_msg.get("content", raw_msg.get("message", ""))).strip()
                    speaker = str(
                        raw_msg.get("speaker")
                        or raw_msg.get("role")
                        or raw_msg.get("sender")
                        or fallback_speaker
                        or "Unknown"
                    ).strip()
                else:
                    content_text = str(raw_msg).strip()
                    speaker = (fallback_speaker or "Unknown").strip()

                if not content_text:
                    return

                line = f"{speaker}: {content_text}"
                if line in seen_clinical_msgs:
                    return

                seen_clinical_msgs.add(line)
                clinical_msgs.append(line)
            patient_chat = context.get("chat_history_with_patient", [])
            for msg in patient_chat:
                add_clinical_msg(msg)
            partner_chat = context.get("chat_history_with_partner", [])
            if partner_chat and partner_chat != patient_chat:
                for msg in partner_chat:
                    add_clinical_msg(msg)
            consultation_history = context.get("consultation_history", {})
            for doctor_id, messages in consultation_history.items():
                if isinstance(messages, list):
                    for msg in messages:
                        add_clinical_msg(msg, fallback_speaker=doctor_id)
            reflection_query = "\n".join(clinical_msgs[-8:]) if clinical_msgs else message_content
            reflections = await reflect_plugin.get_relevant_reflections(reflection_query, top_k=2)

            ref_sections = []
            diagnosis_refs = reflections.get("diagnosis", [])
            if diagnosis_refs:
                ref_lines = ["## Lessons on Diagnosis"]
                for ref in diagnosis_refs:
                    symptoms = ref.get("symptoms_pattern", "")
                    correct_dx = ref.get("correct_diagnosis", "")
                    error_type = ref.get("error_type", "none")
                    lesson = ref.get("lesson_learned", "")
                    if symptoms or lesson:
                        ref_lines.append(f"- Symptoms: {symptoms}")
                        if correct_dx:
                            ref_lines.append(f"  Correct diagnosis: {correct_dx}")
                        if error_type and error_type != "none":
                            ref_lines.append(f"  Error type: {error_type}")
                        if lesson:
                            ref_lines.append(f"  Lesson: {lesson}")
                ref_sections.append("\n".join(ref_lines))
            examination_refs = reflections.get("examination", [])
            if examination_refs:
                ref_lines = ["## Lessons on Examinations"]
                for ref in examination_refs:
                    symptoms = ref.get("symptoms_pattern", "")
                    missed = ref.get("missed_exams", [])
                    if isinstance(missed, str):
                        missed = [m.strip() for m in missed.split(",") if m.strip()]
                    unnecessary = ref.get("unnecessary_exams", [])
                    if isinstance(unnecessary, str):
                        unnecessary = [u.strip() for u in unnecessary.split(",") if u.strip()]
                    lesson = ref.get("lesson_learned", "")
                    if symptoms or lesson:
                        ref_lines.append(f"- Symptoms: {symptoms}")
                        if missed:
                            ref_lines.append(f"  Missed exams: {', '.join(missed)}")
                        if unnecessary:
                            ref_lines.append(f"  Unnecessary exams: {', '.join(unnecessary)}")
                        if lesson:
                            ref_lines.append(f"  Lesson: {lesson}")
                ref_sections.append("\n".join(ref_lines))
            treatment_refs = reflections.get("treatment", [])
            if treatment_refs:
                ref_lines = ["## Lessons on Treatment"]
                for ref in treatment_refs:
                    dx = ref.get("diagnosis", "")
                    safety = ref.get("safety_concerns", "none")
                    lesson = ref.get("lesson_learned", "")
                    if dx or lesson:
                        ref_lines.append(f"- Diagnosis: {dx}")
                        if safety and safety != "none":
                            ref_lines.append(f"  Safety concerns: {safety}")
                        if lesson:
                            ref_lines.append(f"  Lesson: {lesson}")
                ref_sections.append("\n".join(ref_lines))

            if ref_sections:
                context["reflections"] = "\n\n".join(ref_sections)

        self._current_patient_id = patient_id
        return context

    def _format_exam_results(self, exam_results: List[Dict]) -> str:
        """Format examination results for prompt."""
        if not exam_results:
            return ""

        result_lines = ["## ⚠️ AVAILABLE EXAMINATION RESULTS (review before responding)"]
        for exam in exam_results:
            items = exam.get("examination_items", [])
            results = exam.get("results", {})
            completed_tick = exam.get("completed_tick", "N/A")
            result_lines.append(f"\n### Examination completed at Tick {completed_tick}")
            result_lines.append(f"Items: {', '.join(items)}")
            result_lines.append("Results:")
            for item_name, item_data in results.items():
                if isinstance(item_data, dict):
                    result_text = item_data.get("result", str(item_data))
                    result_lines.append(f"  - {item_name}: {result_text}")
                else:
                    result_lines.append(f"  - {item_name}: {item_data}")
        return "\n".join(result_lines)

    def _get_temp_vars(self) -> Optional[Dict[str, Any]]:
        """Get temporary variables for checkpoint/resume."""
        return {
            "tool_calls": self._tool_calls,
            "tool_call_index": self._tool_call_index,
            "pending_messages_pq": self._pending_messages_pq,
            "last_processed_action_id": self._last_processed_action_id,
            "active_patients": self._active_patients,
            "treated_patients": list(self._treated_patients),
            "completed_consultations": self._completed_consultations,
            "patients_pending_reflection": self._patients_pending_reflection,
            "diseases_by_department": self._diseases_by_department,
            "current_patient_id": self._current_patient_id,
            "pending_knowledge_query": self._pending_knowledge_query,
            "consecutive_knowledge_searches": self._consecutive_knowledge_searches,
            "consecutive_doctor_replies": self._consecutive_doctor_replies,
            "last_executed_tick": getattr(self, "global_tick", -1),
        }

    def _set_temp_vars(self, vars_dict: Dict[str, Any]) -> None:
        """Restore temporary variables from checkpoint."""
        self._tool_calls = vars_dict.get("tool_calls", [])
        self._tool_call_index = vars_dict.get("tool_call_index", 0)
        self._pending_messages_pq = vars_dict.get("pending_messages_pq", [])
        self._last_processed_action_id = vars_dict.get("last_processed_action_id")
        self._active_patients = vars_dict.get("active_patients", {})
        self._treated_patients = set(vars_dict.get("treated_patients", []))
        self._completed_consultations = vars_dict.get("completed_consultations", [])
        self._patients_pending_reflection = vars_dict.get("patients_pending_reflection", [])
        self._diseases_by_department = vars_dict.get("diseases_by_department", {})
        self._current_patient_id = vars_dict.get("current_patient_id")
        self._pending_knowledge_query = vars_dict.get("pending_knowledge_query")
        self._consecutive_knowledge_searches = vars_dict.get("consecutive_knowledge_searches", {})
        self._consecutive_doctor_replies = vars_dict.get("consecutive_doctor_replies", {})
        self.global_tick = vars_dict.get("last_executed_tick", -1)

    async def load_from_db(self) -> None:
        """Load temporary variables from Redis before execute()."""
        redis_key = f"{self.agent_id}:temp_vars:DoctorPlannerPlugin"
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

        redis_key = f"{self.agent_id}:temp_vars:DoctorPlannerPlugin"
        try:
            await self.redis.set(redis_key, vars_dict)
            logger.debug(f"[{self.agent_id}] Saved temp vars to Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to save temp vars to Redis: {e}")
