"""
Other Actions Plugin for Hospital Simulation.
Handles movement and registration following Baseline_instruction.md.

Patient Actions:
- move: Move to different locations (tracked in patient state)
- registration: Register at registration desk and get assigned to a doctor
- idle: Wait or remain idle
"""

import inspect
import json
from typing import Any, Optional, List, Dict

from agentkernel_distributed.mas.action.base.plugin_base import OtherActionsPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages.kv_adapters import RedisKVAdapter
from agentkernel_distributed.types.schemas.action import ActionResult
from agentkernel_distributed.mas.interface.protocol import EventCategory

from baseline.utils.annotation import AgentCall

logger = get_logger(__name__)


class HospitalOtherActionsPlugin(OtherActionsPlugin):
    """
    Plugin for movement and registration actions.
    Following Baseline_instruction.md specification.
    """

    def __init__(self, redis: RedisKVAdapter):
        """
        Initialize other actions plugin with Redis adapter.

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

    async def _log_action(self, agent_id: str, event_type: str, status: str, payload: Dict = None):
        """Log action for trajectory recording and publish to frontend."""
        current_tick = await self.controller.run_system("timer", "get_tick")

        action_log = {
            "tick": current_tick,
            "event_type": event_type,
            "agent_id": agent_id,
            "status": status,
            "payload": payload or {},
        }

        logger.debug(f"[{agent_id}] Action Log: {json.dumps(action_log)}")
        try:
            await self.controller.run_system(
                "recorder",
                "record_event",
                tick=current_tick,
                event_type=event_type,
                agent_id=agent_id,
                payload=payload or {},
            )
        except Exception as e:
            logger.error(f"Failed to record event: {e}", exc_info=True)
        try:
            event_payload = {"agent_id": agent_id, "status": status, **(payload or {})}
            await self.controller.publish_event(category=EventCategory.AGENT, name=event_type, payload=event_payload)
        except Exception as e:
            logger.debug(f"Failed to publish event to frontend: {e}")

    @AgentCall()
    async def move(self, agent_name: str, target_location: str) -> ActionResult:
        """Move patient to a specific location in the hospital.

        Location is tracked in patient state, no space plugin needed.

        Args:
            agent_name (str): Name of the patient performing the move.
            target_location (str): Target location ID (e.g., "registration_desk", "examination_room", "treatment_room", "consultation_*").
        """
        logger.info(f"Patient {agent_name} moving to {target_location}")

        try:
            await self.controller.run_agent_method(
                agent_name, "state", "set_state", "current_location", target_location
            )

            await self._log_action(agent_name, "PATIENT_MOVE", "success", {"target": target_location})

            return ActionResult.success(
                method_name="move",
                message=f"{agent_name} has arrived at {target_location}.",
                data={"location": target_location},
            )

        except Exception as e:
            logger.error(f"Failed to move {agent_name}: {e}", exc_info=True)
            await self._log_action(agent_name, "PATIENT_MOVE", "failed", {"error": str(e)})
            return ActionResult.error(method_name="move", message=f"Move failed: {e}")

    @AgentCall()
    async def registration(self, agent_name: str) -> ActionResult:
        """Register at the hospital registration desk. Patient profile is analyzed by LLM to determine appropriate department, then a doctor is assigned.

        Args:
            agent_name (str): Name of the patient registering.
        """
        current_tick = await self.controller.run_system("timer", "get_tick")

        try:
            patient_profile = await self.controller.run_agent_method(agent_name, "profile", "get_profile")

            if not patient_profile:
                return ActionResult.error(method_name="registration", message="Patient profile not found")

            demographics = patient_profile.get("demographics", {})
            present_illness = patient_profile.get("present_illness_history", {}) or {}
            initial_complaint = present_illness.get("chief_complaint", "")
            symptoms = present_illness.get("symptoms_and_progression", [])
            valid_departments = await self.redis.get("hospital:departments")
            if not valid_departments:
                logger.warning("Departments not found in Redis, using fallback list")
                valid_departments = [
                    "Cardiology Department",
                    "Dentistry Department",
                    "Dermatology Department",
                    "Endocrinology Department",
                    "Gastroenterology Department",
                    "General Surgery Department",
                    "Hematology Department",
                    "Immunology Department",
                    "Infectious Department",
                    "Nephrology Department",
                    "Neurology Department",
                    "Obstetrics and Gynecology Department",
                    "Oncology Department",
                    "Ophthalmology Department",
                    "Orthopedics Department",
                    "Otolaryngology Department",
                    "Pediatrics Department",
                    "Respiratory Department",
                    "Urology Department",
                ]
            departments_list = "\n".join(f"- {dept}" for dept in valid_departments)

            system_prompt = f"""You are a hospital triage assistant. Select the most appropriate department for this patient.
{departments_list}

IMPORTANT: If the ideal specialty is not listed, choose the closest alternative. For example:
- Rheumatology → Immunology Department
- Psychiatry → Neurology Department

Respond with ONLY the exact department name, nothing else."""

            user_prompt = f"""Patient Information:
Demographics: {demographics}
Chief Complaint: {initial_complaint}
Symptoms and Progression: {symptoms}

What department should this patient be referred to?"""
            
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
                from difflib import SequenceMatcher
                best_match = None
                best_ratio = 0.0
                for dept in valid_departments:
                    ratio = SequenceMatcher(None, response_lower, dept.lower()).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = dept
                if best_match and best_ratio > 0.5:
                    logger.info(f"Fuzzy matched '{response_clean}' to '{best_match}' (similarity: {best_ratio:.2f})")
                    return best_match

                return None
            department = None
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    response = await self.model.chat(user_prompt, system_prompt=system_prompt)
                    response = response.strip()
                    matched_dept = find_best_matching_department(response, valid_departments)
                    if matched_dept:
                        department = matched_dept
                        if matched_dept != response:
                            logger.info(f"Mapped LLM response '{response}' to valid department '{matched_dept}'")
                        break
                    else:
                        logger.warning(
                            f"LLM returned invalid department '{response}' (attempt {attempt + 1}/{max_retries})"
                        )

                except Exception as e:
                    logger.warning(f"LLM department selection failed (attempt {attempt + 1}/{max_retries}): {e}")
            if department is None:
                logger.warning(f"All {max_retries} attempts failed, using default department")
                department = "General Surgery Department"
            department_to_room_base = {
                "Cardiology Department": "consultation_cardiology",
                "Dentistry Department": "consultation_dentistry",
                "Dermatology Department": "consultation_dermatology",
                "Endocrinology Department": "consultation_endocrinology",
                "Gastroenterology Department": "consultation_gastroenterology",
                "General Surgery Department": "consultation_general_surgery",
                "Hematology Department": "consultation_hematology",
                "Immunology Department": "consultation_immunology",
                "Infectious Department": "consultation_infectious",
                "Nephrology Department": "consultation_nephrology",
                "Neurology Department": "consultation_neurology",
                "Obstetrics and Gynecology Department": "consultation_obstetrics_gynecology",
                "Oncology Department": "consultation_oncology",
                "Ophthalmology Department": "consultation_ophthalmology",
                "Orthopedics Department": "consultation_orthopedics",
                "Otolaryngology Department": "consultation_otolaryngology",
                "Pediatrics Department": "consultation_pediatrics",
                "Respiratory Department": "consultation_respiratory",
                "Urology Department": "consultation_urology",
            }
            import random
            dept_key = department.replace(" Department", "").replace(" ", "_").replace("and_", "")
            doctor_num = random.randint(1, 2)
            doctor_id = f"Doctor_{dept_key}_{doctor_num:03d}"
            room_base = department_to_room_base.get(department, "consultation_general_surgery")
            consultation_room = f"{room_base}_{doctor_num}"
            current_tick = await self.controller.run_system("timer", "get_tick")

            registration_id = await self.controller.run_environment(
                "hospital_system",
                "register_patient",
                patient_id=agent_name,
                department=department,
                doctor_id=doctor_id,
                current_tick=current_tick,
            )
            try:
                await self.controller.run_agent_method(agent_name, "state", "set_state", "assigned_doctor", doctor_id)
                await self.controller.run_agent_method(agent_name, "state", "set_state", "department", department)
                await self.controller.run_agent_method(
                    agent_name, "state", "set_state", "consultation_room", consultation_room
                )
                await self.controller.run_agent_method(agent_name, "state", "set_state", "current_phase", "registered")
            except Exception as e:
                logger.warning(f"Failed to update patient state: {e}")

            await self._log_action(
                agent_name,
                "PATIENT_REGISTER",
                "success",
                {
                    "department": department,
                    "doctor_id": doctor_id,
                    "consultation_room": consultation_room,
                    "registration_id": registration_id,
                },
            )

            return ActionResult.success(
                method_name="registration",
                message=f"Registration successful. Department: {department}. Assigned doctor: {doctor_id}. Please proceed to {consultation_room}.",
                data={
                    "department": department,
                    "doctor_id": doctor_id,
                    "consultation_room": consultation_room,
                    "registration_id": registration_id,
                },
            )

        except Exception as e:
            logger.error(f"Registration failed for {agent_name}: {e}", exc_info=True)
            await self._log_action(agent_name, "PATIENT_REGISTER", "failed", {"error": str(e)})
            return ActionResult.error(method_name="registration", message=f"Registration failed: {e}")

    @AgentCall()
    async def idle(self, agent_name: str) -> ActionResult:
        """Wait or remain idle for the current tick.

        Args:
            agent_name (str): Name of the agent.
        """
        return ActionResult.success(method_name="idle", message=f"{agent_name} is waiting.")
