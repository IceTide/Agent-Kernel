"""
Tools Plugin for Hospital Simulation.
Provides tool-based actions following Baseline_instruction.md.

Patient Tools:
- do_examination: Perform examination in examination room
- receive_treatment: Complete treatment and get medication

Doctor Tools:
- schedule_examination: Order examinations for patient
- prescribe_treatment: Prescribe medication/treatment
- search_medical_knowledge: Search medical knowledge base for relevant information
"""

import json
import inspect
from typing import List, Dict, Any, Optional, Union

from agentkernel_distributed.mas.action.base.plugin_base import FunctionToolPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages.kv_adapters import RedisKVAdapter
from agentkernel_distributed.toolkit.storages.vectordb_adapters.base import BaseVectorDBAdapter
from agentkernel_distributed.types.schemas.action import ActionResult
from agentkernel_distributed.types.schemas.vectordb import VectorSearchRequest
from agentkernel_distributed.mas.interface.protocol import EventCategory

from baseline.utils.annotation import AgentCall

logger = get_logger(__name__)
DEFAULT_KNOWLEDGE_TOP_K = 5


class HospitalToolsPlugin(FunctionToolPlugin):
    """
    Tools plugin providing medical operations for hospital simulation.
    Following Baseline_instruction.md specification.
    """

    def __init__(self, redis: RedisKVAdapter, vectordb: Optional[BaseVectorDBAdapter] = None):
        """
        Initialize tools plugin with Redis adapter and optional vector database.

        Args:
            redis: Redis KV adapter for persistence
            vectordb: Optional vector database adapter for knowledge retrieval
        """
        super().__init__()
        self.redis = redis
        self.vectordb = vectordb

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
        """Log action for trajectory recording and publish to frontend via Redis Pub/Sub."""
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
    async def do_examination(self, agent_name: str) -> ActionResult:
        """Perform examination. Patient must be in examination room with pending orders.

        This action:
        1. Queries HospitalSystem for pending examination orders
        2. Gets results from ExaminationRoom (ground truth)
        3. Updates order status to completed
        4. Stores examination results in HospitalSystem for doctor to retrieve

        Args:
            agent_name (str): Name of the patient doing the examination.
        """
        current_tick = await self.controller.run_system("timer", "get_tick")

        try:
            pending_exams = await self.controller.run_environment(
                "hospital_system", "get_pending_examinations", patient_id=agent_name
            )

            if not pending_exams:
                await self._log_action(agent_name, "DO_EXAMINATION", "no_pending")
                return ActionResult.error(
                    method_name="do_examination",
                    message="No pending examination orders. Please ask your doctor to order examinations first.",
                )
            all_items = []
            exam_records = []
            for exam in pending_exams:
                items = exam.get("examination_items", [])
                all_items.extend(items)
                exam_records.append(exam)
            results = await self.controller.run_environment(
                "examination_room", "generate_report", patient_id=agent_name, requested_items=all_items
            )
            current_tick = await self.controller.run_system("timer", "get_tick")

            for exam in exam_records:
                await self.controller.run_environment(
                    "hospital_system",
                    "complete_examination",
                    record_id=exam.get("id"),
                    results=results,
                    completed_tick=current_tick,
                )

            await self._log_action(
                agent_name,
                "DO_EXAMINATION",
                "success",
                {
                    "items": all_items,
                    "results_count": len(results),
                    "results": results,
                },
            )

            return ActionResult.success(
                method_name="do_examination",
                message=f"Examination completed. {len(all_items)} item(s) processed. Please return to your doctor to get the results.",
                data={"items": all_items, "completed": True},
            )

        except Exception as e:
            logger.error(f"Failed to do examination: {e}")
            await self._log_action(agent_name, "DO_EXAMINATION", "failed", {"error": str(e)})
            return ActionResult.error(method_name="do_examination", message=f"Failed to complete examination: {e}")

    @AgentCall()
    async def receive_treatment(self, agent_name: str) -> ActionResult:
        """Receive treatment and medication. Patient must be in treatment room with prescription.

        This action:
        1. Queries HospitalSystem for pending prescriptions
        2. Marks prescription as completed
        3. Patient workflow ends (doctor gets ground_truth via reflection)

        Args:
            agent_name (str): Name of the patient receiving treatment.
        """
        current_tick = await self.controller.run_system("timer", "get_tick")

        try:
            prescription = await self.controller.run_environment(
                "hospital_system", "get_pending_prescription", patient_id=agent_name
            )

            if not prescription:
                await self._log_action(agent_name, "RECEIVE_TREATMENT", "no_pending")
                return ActionResult.error(
                    method_name="receive_treatment",
                    message="No pending prescriptions. Please consult with your doctor first.",
                )
            await self.controller.run_environment(
                "hospital_system",
                "complete_prescription",
                record_id=prescription.get("id"),
                completed_tick=current_tick,
            )

            await self._log_action(
                agent_name,
                "RECEIVE_TREATMENT",
                "success",
                {"prescription_id": prescription.get("id")},
            )

            return ActionResult.success(
                method_name="receive_treatment",
                message="Treatment completed. Patient workflow finished.",
                data={
                    "prescription_id": prescription.get("id"),
                    "instructions": "Take medications as prescribed. Return if symptoms worsen.",
                },
            )

        except Exception as e:
            logger.error(f"Failed to receive treatment: {e}")
            await self._log_action(agent_name, "RECEIVE_TREATMENT", "failed", {"error": str(e)})
            return ActionResult.error(method_name="receive_treatment", message=f"Failed to receive treatment: {e}")

    @AgentCall()
    async def schedule_examination(
        self, agent_name: str, patient_id: str, examination_items: List[str], reason: str = ""
    ) -> ActionResult:
        """Schedule examinations for a patient. Creates examination orders in HospitalSystem.

        Args:
            agent_name (str): Name of the doctor ordering the examination.
            patient_id (str): ID of the patient.
            examination_items (List[str]): List of examination items to order (e.g., ["血常规", "胸部CT"]).
            reason (str): Clinical reason for ordering the examinations.
        """
        current_tick = await self.controller.run_system("timer", "get_tick")

        try:
            current_tick = await self.controller.run_system("timer", "get_tick")
            record_id = await self.controller.run_environment(
                "hospital_system",
                "add_examination",
                patient_id=patient_id,
                doctor_id=agent_name,
                current_tick=current_tick,
                examination_items=examination_items,
            )

            await self._log_action(
                agent_name,
                "SCHEDULE_EXAMINATION",
                "success",
                {"patient_id": patient_id, "record_id": record_id, "items": examination_items, "reason": reason},
            )

            return ActionResult.success(
                method_name="schedule_examination",
                message=f"Examination ordered successfully. Order ID: {record_id}. Patient should proceed to examination room.",
                data={"record_id": record_id, "items": examination_items, "patient_id": patient_id},
            )

        except Exception as e:
            logger.error(f"Failed to schedule examination: {e}")
            await self._log_action(agent_name, "SCHEDULE_EXAMINATION", "failed", {"error": str(e)})
            return ActionResult.error(
                method_name="schedule_examination", message=f"Failed to schedule examination: {e}"
            )

    @AgentCall()
    async def prescribe_treatment(
        self, agent_name: str, patient_id: str, diagnosis: Union[str, List[str]], treatment_plan: str
    ) -> ActionResult:
        """Prescribe treatment for a patient. Creates prescription in HospitalSystem.

        Args:
            agent_name (str): Name of the prescribing doctor.
            patient_id (str): ID of the patient.
            diagnosis (str or List[str]): Clinical diagnosis. Can be a single diagnosis string
                or a list of diagnoses for comorbidity cases.
            treatment_plan (str): Treatment plan including medications and instructions.
        """
        current_tick = await self.controller.run_system("timer", "get_tick")

        try:
            current_tick = await self.controller.run_system("timer", "get_tick")
            diagnosis_display = diagnosis if isinstance(diagnosis, str) else ", ".join(diagnosis)
            treatment_content = f"Diagnosis: {diagnosis_display}. Treatment Plan: {treatment_plan}"
            record_id = await self.controller.run_environment(
                "hospital_system",
                "add_prescription",
                patient_id=patient_id,
                doctor_id=agent_name,
                current_tick=current_tick,
                treatment_content=treatment_content,
            )

            await self._log_action(
                agent_name,
                "PRESCRIBE_TREATMENT",
                "success",
                {
                    "patient_id": patient_id,
                    "record_id": record_id,
                    "diagnosis": diagnosis,
                    "treatment_plan": treatment_plan,
                },
            )

            return ActionResult.success(
                method_name="prescribe_treatment",
                message=f"Prescription created successfully. Order ID: {record_id}. Patient should proceed to treatment room.",
                data={
                    "record_id": record_id,
                    "diagnosis": diagnosis,
                    "treatment_plan": treatment_plan,
                    "patient_id": patient_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to prescribe treatment: {e}")
            await self._log_action(agent_name, "PRESCRIBE_TREATMENT", "failed", {"error": str(e)})
            return ActionResult.error(method_name="prescribe_treatment", message=f"Failed to prescribe treatment: {e}")

    @AgentCall()
    async def search_medical_knowledge(
        self, agent_name: str, query: str, top_k: int = DEFAULT_KNOWLEDGE_TOP_K
    ) -> ActionResult:
        """Search the medical knowledge base for relevant information.

        This tool allows doctors to query the medical knowledge database (Milvus)
        to find relevant medical literature, treatment guidelines, drug information,
        and clinical references based on semantic similarity.

        Args:
            agent_name (str): Name of the doctor performing the search.
            query (str): The search query describing what medical knowledge is needed.
                         Can be symptoms, diseases, treatments, drugs, or any medical topic.
            top_k (int): Number of most relevant results to return. Defaults to 5.
        """
        current_tick = await self.controller.run_system("timer", "get_tick")

        try:
            if self.vectordb is None:
                await self._log_action(agent_name, "SEARCH_MEDICAL_KNOWLEDGE", "not_configured", {"query": query})
                return ActionResult.error(
                    method_name="search_medical_knowledge",
                    message="Medical knowledge base is not configured. Please contact system administrator.",
                )
            search_request = VectorSearchRequest(
                query=query,
                top_k=top_k,
            )

            search_results = await self.vectordb.search(search_request)

            if not search_results:
                await self._log_action(agent_name, "SEARCH_MEDICAL_KNOWLEDGE", "no_results", {"query": query})
                return ActionResult.success(
                    method_name="search_medical_knowledge",
                    message=f"No relevant medical knowledge found for query: '{query}'",
                    data={"query": query, "results": [], "count": 0},
                )
            knowledge_items = []
            for i, result in enumerate(search_results, 1):
                doc = result.document
                knowledge_item = {
                    "rank": i,
                    "content": doc.content,
                    "relevance_score": round(result.score, 4),
                    "source": doc.metadata.get("source", "Unknown") if doc.metadata else "Unknown",
                    "category": doc.metadata.get("category", "General") if doc.metadata else "General",
                }
                knowledge_items.append(knowledge_item)
            formatted_text = f"Medical Knowledge Search Results for: '{query}'\n"
            formatted_text += f"Found {len(knowledge_items)} relevant item(s):\n\n"

            for item in knowledge_items:
                formatted_text += f"--- Result {item['rank']} (Score: {item['relevance_score']}) ---\n"
                formatted_text += f"Source: {item['source']} | Category: {item['category']}\n"
                formatted_text += f"{item['content']}\n\n"

            await self._log_action(
                agent_name,
                "SEARCH_MEDICAL_KNOWLEDGE",
                "success",
                {"query": query, "results_count": len(knowledge_items)},
            )

            return ActionResult.success(
                method_name="search_medical_knowledge",
                message=formatted_text,
                data={
                    "query": query,
                    "results": knowledge_items,
                    "count": len(knowledge_items),
                },
            )

        except Exception as e:
            logger.error(f"Failed to search medical knowledge: {e}")
            await self._log_action(agent_name, "SEARCH_MEDICAL_KNOWLEDGE", "failed", {"query": query, "error": str(e)})
            return ActionResult.error(
                method_name="search_medical_knowledge",
                message=f"Failed to search medical knowledge base: {e}",
            )
