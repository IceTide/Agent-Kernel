"""
Doctor Reflect Plugin for Hospital Simulation.
Generates reflections for doctor agents after completing patient consultations.
"""

import hashlib
import json
import os
import textwrap
from pathlib import Path
from typing import Dict, Any, Optional, List

from agentkernel_distributed.mas.agent.base.plugin_base import ReflectPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.utils import clean_json_response
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.toolkit.storages.vectordb_adapters.base import BaseVectorDBAdapter
from agentkernel_distributed.types.schemas.vectordb import VectorDocument, VectorSearchRequest

from baseline.plugins.agent.plan.DoctorPlannerPlugin import DoctorPlannerPlugin
from baseline.plugins.agent.perceive.DoctorPerceptionPlugin import DoctorPerceptionPlugin
from baseline.plugins.agent.profile.DoctorProfilePlugin import DoctorProfilePlugin
from baseline.utils.prompt_utils import save_prompt

logger = get_logger(__name__)


class DoctorReflectPlugin(ReflectPlugin):
    """
    Reflection plugin for doctor agents.
    Generates reflections after completing each patient consultation.
    Ground truth data is read from Redis on-demand using patient-specific keys.
    Redis key format: "hospital:ground_truth:{patient_id}"
    """

    GROUND_TRUTH_KEY_PREFIX = "hospital:ground_truth:"
    MAX_REFLECTIONS_IN_MEMORY = 20                                          
    COMPRESSION_THRESHOLD = 10                                        
    DEFAULT_REFLECTION_MODE = "write"
    MAX_SEARCH_QUERY_CACHE = 100

    def __init__(self, redis: RedisKVAdapter, vectordb: Optional[BaseVectorDBAdapter] = None):
        super().__init__()
        self.redis = redis
        self.vectordb = vectordb

    async def init(self):
        """Initialize reflection plugin."""
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        self.global_tick = 0

        self.reflection_mode = self._resolve_reflection_mode(os.environ.get("HOSPITAL_REFLECTION_MODE", ""))
        namespace = os.environ.get("HOSPITAL_REFLECTION_NAMESPACE", "default").strip()
        self.reflection_namespace = namespace or "default"

        default_store_dir = os.path.join(
            os.environ.get("MAS_PROJECT_ABS_PATH", "."),
            "decoupling_output",
            "reflection_store",
        )
        self.reflection_store_dir = os.environ.get("HOSPITAL_REFLECTION_STORE_DIR", default_store_dir).strip()
        self._reflection_store_file = self._build_reflection_store_file()

        logger.info(
            "[%s] Reflection mode=%s, namespace=%s, store=%s",
            self.agent_id,
            self.reflection_mode,
            self.reflection_namespace,
            self._reflection_store_file,
        )
        self._diagnosis_reflections: List[Dict[str, Any]] = []
        self._examination_reflections: List[Dict[str, Any]] = []
        self._treatment_reflections: List[Dict[str, Any]] = []
        self._search_query_cache: Dict[str, str] = {}
        self._total_reflection_count = 0
        await self.load_from_db()
        await self._load_persistent_store()

    def _build_reflection_store_file(self) -> Path:
        namespace_safe = self.reflection_namespace.replace(" ", "_").replace(":", "_")
        return Path(self.reflection_store_dir) / namespace_safe / f"{self.agent_id}.json"

    async def _load_persistent_store(self) -> None:
        """Load persistent reflections from local file for cross-run continuity."""
        store_file = self._reflection_store_file
        if not store_file.exists():
            return

        try:
            with open(store_file, "r", encoding="utf-8") as f:
                payload = json.load(f)

            if not isinstance(payload, dict):
                return

            diagnosis = payload.get("diagnosis_reflections", [])
            examination = payload.get("examination_reflections", [])
            treatment = payload.get("treatment_reflections", [])
            total_count = payload.get("total_reflection_count")

            if isinstance(diagnosis, list):
                self._diagnosis_reflections = diagnosis[-self.MAX_REFLECTIONS_IN_MEMORY :]
            if isinstance(examination, list):
                self._examination_reflections = examination[-self.MAX_REFLECTIONS_IN_MEMORY :]
            if isinstance(treatment, list):
                self._treatment_reflections = treatment[-self.MAX_REFLECTIONS_IN_MEMORY :]
            if isinstance(total_count, int) and total_count >= 0:
                self._total_reflection_count = max(self._total_reflection_count, total_count)

            logger.info(
                "[%s] Loaded persistent reflections: diagnosis=%d, examination=%d, treatment=%d",
                self.agent_id,
                len(self._diagnosis_reflections),
                len(self._examination_reflections),
                len(self._treatment_reflections),
            )
        except Exception as e:
            logger.warning("[%s] Failed to load persistent reflections: %s", self.agent_id, e)

    async def _save_persistent_store(self) -> None:
        """Persist recent reflections to local file for cross-run continuity."""
        if not self._reflection_writable():
            return

        try:
            self._reflection_store_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "namespace": self.reflection_namespace,
                "agent_id": self.agent_id,
                "diagnosis_reflections": self._diagnosis_reflections,
                "examination_reflections": self._examination_reflections,
                "treatment_reflections": self._treatment_reflections,
                "total_reflection_count": self._total_reflection_count,
            }
            with open(self._reflection_store_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("[%s] Failed to save persistent reflections: %s", self.agent_id, e)

    @classmethod
    def _resolve_reflection_mode(cls, raw_mode: str) -> str:
        """Normalize reflection mode from environment value."""
        mode = (raw_mode or "").strip().lower()
        alias_map = {
            "write": "write",
            "train": "write",
            "default": "write",
            "read_only": "read_only",
            "readonly": "read_only",
            "eval": "read_only",
            "off": "off",
            "none": "off",
            "disabled": "off",
        }
        return alias_map.get(mode, cls.DEFAULT_REFLECTION_MODE)

    def _reflection_writable(self) -> bool:
        return self.reflection_mode == "write"

    def _reflection_enabled(self) -> bool:
        return self.reflection_mode != "off"

    async def _load_ground_truth(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Load ground truth data for a specific patient from Redis.

        Args:
            patient_id: Patient ID

        Returns:
            Ground truth data for the patient, or None if not found
        """
        try:
            if self.redis:
                redis_key = f"{self.GROUND_TRUTH_KEY_PREFIX}{patient_id}"
                data = await self.redis.get(redis_key)
                if data and isinstance(data, dict):
                    logger.debug(f"Loaded ground truth for patient {patient_id} from Redis")
                    return data
                else:
                    logger.debug(f"No ground truth found for patient {patient_id} in Redis")
                    return None
        except Exception as e:
            logger.error(f"Failed to load ground truth for patient {patient_id} from Redis: {e}")
            return None

    def _get_plan_plugin(self) -> Optional[DoctorPlannerPlugin]:
        """Get plan plugin using peer_plugin."""
        return self.peer_plugin("plan", DoctorPlannerPlugin)

    def _get_perceive_plugin(self) -> Optional[DoctorPerceptionPlugin]:
        """Get perceive plugin using peer_plugin."""
        return self.peer_plugin("perceive", DoctorPerceptionPlugin)

    def _get_profile_plugin(self) -> Optional[DoctorProfilePlugin]:
        """Get profile plugin using peer_plugin."""
        return self.peer_plugin("profile", DoctorProfilePlugin)

    @property
    def diagnosis_reflections(self) -> List[Dict[str, Any]]:
        """Get diagnosis reflections."""
        return self._diagnosis_reflections

    @property
    def examination_reflections(self) -> List[Dict[str, Any]]:
        """Get examination reflections."""
        return self._examination_reflections

    @property
    def treatment_reflections(self) -> List[Dict[str, Any]]:
        """Get treatment reflections."""
        return self._treatment_reflections

    async def _generate_search_query(self, clinical_text: str) -> str:
        """
        Use LLM to extract clinical key features from clinical conversation text
        and generate a concise clinical search query for vector retrieval.
        The input may be patient messages, doctor-patient dialogue, or consultation notes.
        Uses hashlib-based caching to avoid redundant LLM calls.

        Args:
            clinical_text: Clinical conversation text (may include multiple messages)

        Returns:
            Optimized clinical search query string (max 30 words)
        """
        if not clinical_text or not clinical_text.strip():
            return clinical_text
        msg_hash = hashlib.md5(clinical_text.encode("utf-8")).hexdigest()
        if msg_hash in self._search_query_cache:
            return self._search_query_cache[msg_hash]

        try:
            system_prompt = textwrap.dedent("""\
                Extract the clinical key features from this clinical conversation and generate a concise search query.
                The input may contain patient-doctor dialogue, consultation notes, or examination discussions.
                Focus on: primary symptoms, duration, severity, affected body systems, key clinical findings.
                Ignore greetings, pleasantries, and non-clinical content.
                Output ONLY the search query text, nothing else. Maximum 30 words.""")

            response = await self.model.chat(clinical_text, system_prompt=system_prompt)
            save_prompt(
                agent_id=self.agent_id,
                tick=self.global_tick,
                context_id="search_query",
                stage="reflect_generate_search_query",
                system_prompt=system_prompt,
                user_prompt=clinical_text,
                response=response,
                plugin_logger=logger,
            )
            query = response.strip().strip('"').strip("'")
            words = query.split()
            if len(words) > 30:
                query = " ".join(words[:30])
            if len(self._search_query_cache) >= self.MAX_SEARCH_QUERY_CACHE:
                keys = list(self._search_query_cache.keys())
                for k in keys[: len(keys) // 2]:
                    del self._search_query_cache[k]
            self._search_query_cache[msg_hash] = query

            logger.debug(f"Generated search query: {query[:80]}")
            return query

        except Exception as e:
            logger.debug(f"Failed to generate search query, using raw text: {e}")
            return clinical_text

    async def get_relevant_reflections(self, query: str, top_k: int = 2) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve relevant reflections from past cases.
        Called by planner to include relevant experience in context.
        Uses vector search if available, otherwise returns recent reflections.
        Retrieves diagnosis, examination, and treatment reflections separately.

        Args:
            query: Current patient symptoms/message to match against
            top_k: Number of reflections to retrieve per type

        Returns:
            Dict with three keys:
            - "diagnosis": List of diagnosis reflections (structured)
            - "examination": List of examination reflections (structured)
            - "treatment": List of treatment reflections (structured)
        """
        empty_result = {"diagnosis": [], "examination": [], "treatment": []}

        if not self._reflection_enabled():
            return empty_result
        search_query = await self._generate_search_query(query)

        result: Dict[str, List[Dict[str, Any]]] = {"diagnosis": [], "examination": [], "treatment": []}
        if self.vectordb:
            try:
                filter_expr = (
                    f'agent_id == "{self.agent_id}" and namespace == "{self.reflection_namespace}"'
                )

                for rtype in ("diagnosis", "examination", "treatment"):
                    type_filter = f'{filter_expr} and reflection_type == "{rtype}"'
                    request = VectorSearchRequest(query=search_query, top_k=top_k, filter=type_filter)
                    search_results = await self.vectordb.search(request)

                    for sr in search_results:
                        metadata = sr.document.metadata if sr.document else {}
                        if metadata:
                            result[rtype].append(dict(metadata))

                has_any = any(result[k] for k in result)
                if has_any:
                    logger.debug(
                        f"Retrieved reflections via vector search: "
                        f"diagnosis={len(result['diagnosis'])}, "
                        f"examination={len(result['examination'])}, "
                        f"treatment={len(result['treatment'])}"
                    )
                    return result

            except Exception as e:
                logger.debug(f"Vector search for reflections failed: {e}, falling back to recent reflections")
        for ref in self._diagnosis_reflections[-top_k:]:
            result["diagnosis"].append(dict(ref))
        for ref in self._examination_reflections[-top_k:]:
            result["examination"].append(dict(ref))
        for ref in self._treatment_reflections[-top_k:]:
            result["treatment"].append(dict(ref))

        return result

    async def execute(self, current_tick: int):
        """Execute reflection logic each tick."""
        if hasattr(self, 'global_tick') and self.global_tick == current_tick:
            logger.debug(f"[{self.agent_id}] Already executed in tick {current_tick}, skipping")
            return

        self.global_tick = current_tick
        plan_plugin = self._get_plan_plugin()
        if not plan_plugin:
            return
        patient_id = plan_plugin.pop_patient_for_reflection()
        if patient_id:
            if self._reflection_writable():
                await self._generate_diagnosis_reflection(patient_id)
                await self._generate_examination_reflection(patient_id)
                await self._generate_treatment_reflection(patient_id)
            await self._cleanup_patient_data(patient_id)
        await self.save_to_db()

    def _get_consultation_record(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Helper to find a consultation record for a patient."""
        plan_plugin = self._get_plan_plugin()
        if not plan_plugin:
            return None
        for record in plan_plugin.completed_consultations:
            if record.get("patient_id") == patient_id:
                return record
        return None

    async def _generate_diagnosis_reflection(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate structured diagnosis reflection by comparing doctor's diagnosis with ground truth.

        Structured output:
        - symptoms_pattern, your_diagnosis, correct_diagnosis, diagnosis_correct,
          error_type, key_clues, lesson_learned
        """
        perceive_plugin = self._get_perceive_plugin()
        consultation_record = self._get_consultation_record(patient_id)
        if not consultation_record or not perceive_plugin:
            return None

        diagnosis = consultation_record.get("diagnosis", "")
        if not diagnosis:
            return None
        ground_truth_info = await self._load_ground_truth(patient_id)
        if not ground_truth_info:
            logger.debug(f"No ground truth found for patient {patient_id}, skipping diagnosis reflection")
            return None

        ground_truth_diagnosis = ground_truth_info.get("final_diagnosis", "")
        if isinstance(ground_truth_diagnosis, list):
            ground_truth_diagnosis = ", ".join(ground_truth_diagnosis)
        chat_history = perceive_plugin.get_patient_chat_history(patient_id, count=20)

        system_prompt = textwrap.dedent("""\
            You are reflecting on a diagnosis case. Compare your diagnosis with the correct diagnosis.
            Respond with **valid JSON only**.
            {
                "symptoms_pattern": "(key symptoms from the patient, max 30 words)",
                "your_diagnosis": "(your diagnosis)",
                "correct_diagnosis": "(the correct diagnosis)",
                "diagnosis_correct": true or false,
                "error_type": "missed_diagnosis" or "wrong_diagnosis" or "incomplete_diagnosis" or "none",
                "key_clues": "(key differentiating clues that should have led to correct diagnosis, max 50 words)",
                "lesson_learned": "(specific actionable lesson for future similar cases, max 80 words)"
            }""")

        user_prompt = json.dumps(
            {
                "patient_id": patient_id,
                "chat_history_summary": chat_history[-5:] if len(chat_history) > 5 else chat_history,
                "your_diagnosis": diagnosis,
                "correct_diagnosis": ground_truth_diagnosis,
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
                stage="reflect_diagnosis",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                plugin_logger=logger,
            )
            reflection = json.loads(clean_json_response(response))
            reflection["your_diagnosis"] = diagnosis
            reflection["correct_diagnosis"] = ground_truth_diagnosis
            reflection["tick"] = self.global_tick
            reflection["patient_id"] = patient_id

            self._diagnosis_reflections.append(reflection)
            await self._persist_reflection("diagnosis")

            logger.debug(f"Generated diagnosis reflection for patient {patient_id}: correct={reflection.get('diagnosis_correct')}")
            return reflection
        except Exception as e:
            logger.error(f"Failed to generate diagnosis reflection: {e}")
            return None

    async def _generate_examination_reflection(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate structured examination reflection comparing ordered vs necessary examinations.
        Computes precision_score, unnecessary_exams, missed_exams deterministically,
        then asks LLM for symptoms_pattern and lesson_learned.

        Structured output:
        - symptoms_pattern, ordered_examinations, necessary_examinations,
          unnecessary_exams, missed_exams, precision_score, lesson_learned
        """
        perceive_plugin = self._get_perceive_plugin()
        consultation_record = self._get_consultation_record(patient_id)
        if not consultation_record or not perceive_plugin:
            return None

        ordered_exams = consultation_record.get("examination_items", [])
        ground_truth_info = await self._load_ground_truth(patient_id)
        if not ground_truth_info:
            logger.debug(f"No ground truth found for patient {patient_id}, skipping examination reflection")
            return None

        necessary_exams = ground_truth_info.get("necessary_examinations", [])
        ordered_set = set(str(e).lower().strip() for e in ordered_exams if e)
        necessary_set = set(str(e).lower().strip() for e in necessary_exams if e)

        correct_exams = ordered_set & necessary_set
        unnecessary = ordered_set - necessary_set
        missed = necessary_set - ordered_set

        precision_score = len(correct_exams) / len(ordered_set) if ordered_set else 0.0
        chat_history = perceive_plugin.get_patient_chat_history(patient_id, count=20)

        system_prompt = textwrap.dedent("""\
            You are reflecting on the examination choices for a patient case.
            The precision metrics are already computed for you. Focus on understanding WHY
            certain examinations were missed or unnecessary, and what lesson to learn.
            Respond with **valid JSON only**.
            {
                "symptoms_pattern": "(key symptoms from the patient, max 30 words)",
                "lesson_learned": "(specific actionable lesson about examination selection for similar cases, max 80 words)"
            }""")

        user_prompt = json.dumps(
            {
                "patient_id": patient_id,
                "chat_history_summary": chat_history[-5:] if len(chat_history) > 5 else chat_history,
                "ordered_examinations": ordered_exams,
                "necessary_examinations": necessary_exams,
                "unnecessary_exams": list(unnecessary),
                "missed_exams": list(missed),
                "precision_score": round(precision_score, 4),
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
                stage="reflect_examination",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                plugin_logger=logger,
            )
            llm_output = json.loads(clean_json_response(response))
            reflection = {
                "symptoms_pattern": llm_output.get("symptoms_pattern", ""),
                "ordered_examinations": ordered_exams,
                "necessary_examinations": necessary_exams,
                "unnecessary_exams": list(unnecessary),
                "missed_exams": list(missed),
                "precision_score": round(precision_score, 4),
                "lesson_learned": llm_output.get("lesson_learned", ""),
                "tick": self.global_tick,
                "patient_id": patient_id,
            }

            self._examination_reflections.append(reflection)
            await self._persist_reflection("examination")

            logger.debug(f"Generated examination reflection for patient {patient_id}: precision={precision_score:.4f}")
            return reflection
        except Exception as e:
            logger.error(f"Failed to generate examination reflection: {e}")
            return None

    async def _generate_treatment_reflection(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate structured treatment reflection comparing doctor's treatment with reference.

        Structured output:
        - diagnosis, your_treatment, reference_treatment, safety_concerns,
          effectiveness_gap, lesson_learned
        """
        consultation_record = self._get_consultation_record(patient_id)
        if not consultation_record:
            return None

        diagnosis = consultation_record.get("diagnosis", "")
        treatment_plan = consultation_record.get("treatment_plan", "")
        if not treatment_plan:
            return None
        ground_truth_info = await self._load_ground_truth(patient_id)
        if not ground_truth_info:
            logger.debug(f"No ground truth found for patient {patient_id}, skipping treatment reflection")
            return None

        ground_truth_treatment = ground_truth_info.get("treatment_plan", "")
        ground_truth_diagnosis = ground_truth_info.get("final_diagnosis", "")
        if isinstance(ground_truth_diagnosis, list):
            ground_truth_diagnosis = ", ".join(ground_truth_diagnosis)

        system_prompt = textwrap.dedent("""\
            You are reflecting on a treatment case by comparing your treatment plan with the reference treatment.
            Respond with **valid JSON only**.
            {
                "diagnosis": "(the diagnosis for this case)",
                "your_treatment": "(summary of your treatment plan, max 50 words)",
                "reference_treatment": "(summary of the reference treatment plan, max 50 words)",
                "safety_concerns": "(any safety issues with your treatment, or 'none')",
                "effectiveness_gap": "(main differences affecting treatment effectiveness, max 50 words)",
                "lesson_learned": "(specific actionable lesson about treatment planning, max 80 words)"
            }""")

        user_prompt = json.dumps(
            {
                "patient_id": patient_id,
                "diagnosis": diagnosis,
                "correct_diagnosis": ground_truth_diagnosis,
                "your_treatment_plan": treatment_plan,
                "reference_treatment_plan": ground_truth_treatment,
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
                stage="reflect_treatment",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                plugin_logger=logger,
            )
            reflection = json.loads(clean_json_response(response))

            reflection["tick"] = self.global_tick
            reflection["patient_id"] = patient_id

            self._treatment_reflections.append(reflection)
            await self._persist_reflection("treatment")

            logger.debug(f"Generated treatment reflection for patient {patient_id}")
            return reflection
        except Exception as e:
            logger.error(f"Failed to generate treatment reflection: {e}")
            return None

    async def _persist_reflection(self, reflection_type: str):
        """Persist reflection to Redis and Vector DB."""
        if not self.redis:
            return

        key_prefix = f"{self.reflection_namespace}:{self.agent_id}"

        key_map = {
            "diagnosis": f"{key_prefix}:diagnosis_reflections",
            "examination": f"{key_prefix}:examination_reflections",
            "treatment": f"{key_prefix}:treatment_reflections",
        }

        data_map = {
            "diagnosis": self._diagnosis_reflections,
            "examination": self._examination_reflections,
            "treatment": self._treatment_reflections,
        }

        key = key_map.get(reflection_type)
        data = data_map.get(reflection_type, [])

        if key:
            recent_data = data[-self.MAX_REFLECTIONS_IN_MEMORY :]
            await self.redis.set(key, recent_data)
        if data:
            latest_reflection = data[-1]
            await self._store_reflection_in_vectordb(latest_reflection, reflection_type)
        self._total_reflection_count += 1
        if self._total_reflection_count % self.COMPRESSION_THRESHOLD == 0:
            await self._compress_reflections()

        await self._save_persistent_store()

    async def _store_reflection_in_vectordb(self, reflection: Dict[str, Any], reflection_type: str):
        """
        Store a reflection in the vector database for semantic retrieval.
        Builds type-specific search_text for better matching.

        Args:
            reflection: The reflection data to store
            reflection_type: Type of reflection ("diagnosis", "examination", or "treatment")
        """
        if not self.vectordb:
            return

        try:
            namespace_safe = self.reflection_namespace.replace(" ", "_").replace(":", "_")
            if reflection_type == "diagnosis":
                search_text = (
                    f"Symptoms: {reflection.get('symptoms_pattern', '')}. "
                    f"Correct diagnosis: {reflection.get('correct_diagnosis', '')}. "
                    f"Error: {reflection.get('error_type', 'none')}. "
                    f"Lesson: {reflection.get('lesson_learned', '')}"
                )
            elif reflection_type == "examination":
                search_text = (
                    f"Symptoms: {reflection.get('symptoms_pattern', '')}. "
                    f"Missed exams: {', '.join(reflection.get('missed_exams', []))}. "
                    f"Lesson: {reflection.get('lesson_learned', '')}"
                )
            else:             
                search_text = (
                    f"Diagnosis: {reflection.get('diagnosis', '')}. "
                    f"Effectiveness gap: {reflection.get('effectiveness_gap', '')}. "
                    f"Lesson: {reflection.get('lesson_learned', '')}"
                )
            doc_id = (
                f"ref_{namespace_safe}_{reflection_type}_{self.agent_id}"
                f"_{reflection.get('patient_id', '')}_{reflection.get('tick', 0)}"
            )
            metadata = {
                "agent_id": self.agent_id,
                "namespace": self.reflection_namespace,
                "reflection_type": reflection_type,
                "patient_id": reflection.get("patient_id", ""),
                "lesson_learned": reflection.get("lesson_learned", ""),
            }

            if reflection_type == "diagnosis":
                metadata["symptoms_pattern"] = reflection.get("symptoms_pattern", "")
                metadata["your_diagnosis"] = reflection.get("your_diagnosis", "")
                metadata["correct_diagnosis"] = reflection.get("correct_diagnosis", "")
                metadata["diagnosis_correct"] = str(reflection.get("diagnosis_correct", ""))
                metadata["error_type"] = reflection.get("error_type", "none")
                metadata["key_clues"] = reflection.get("key_clues", "")
            elif reflection_type == "examination":
                metadata["symptoms_pattern"] = reflection.get("symptoms_pattern", "")
                metadata["ordered_examinations"] = ", ".join(
                    str(e) for e in reflection.get("ordered_examinations", [])
                )
                metadata["necessary_examinations"] = ", ".join(
                    str(e) for e in reflection.get("necessary_examinations", [])
                )
                metadata["unnecessary_exams"] = ", ".join(
                    str(e) for e in reflection.get("unnecessary_exams", [])
                )
                metadata["missed_exams"] = ", ".join(
                    str(e) for e in reflection.get("missed_exams", [])
                )
                metadata["precision_score"] = str(reflection.get("precision_score", 0.0))
            else:             
                metadata["diagnosis"] = reflection.get("diagnosis", "")
                metadata["your_treatment"] = reflection.get("your_treatment", "")
                metadata["reference_treatment"] = reflection.get("reference_treatment", "")
                metadata["safety_concerns"] = reflection.get("safety_concerns", "none")
                metadata["effectiveness_gap"] = reflection.get("effectiveness_gap", "")

            doc = VectorDocument(
                id=doc_id,
                tick=reflection.get("tick", 0),
                content=search_text,
                metadata=metadata,
            )

            await self.vectordb.upsert([doc])
            logger.debug(f"Stored {reflection_type} reflection in vectordb: {doc.id}")

        except Exception as e:
            logger.warning(f"Failed to store {reflection_type} reflection in vectordb: {e}")

    async def _compress_reflections(self):
        """
        Compress old reflections to reduce memory usage.
        Uses LLM to summarize multiple reflections into key insights.
        """
        for rtype, rlist in [
            ("diagnosis", self._diagnosis_reflections),
            ("examination", self._examination_reflections),
            ("treatment", self._treatment_reflections),
        ]:
            if len(rlist) >= self.COMPRESSION_THRESHOLD:
                await self._compress_typed_reflections(rtype, rlist)

    async def _compress_typed_reflections(self, reflection_type: str, reflections_list: List[Dict[str, Any]]):
        """Compress reflections of a specific type, keeping 5 most recent."""
        try:
            to_compress = reflections_list[:-5]
            if len(to_compress) < 3:
                return

            system_prompt = textwrap.dedent(f"""\
                Summarize these {reflection_type} reflections into 3-5 key insights.
                Focus on: recurring patterns, common mistakes, and actionable lessons.
                Respond with valid JSON only.
                {{
                    "key_insights": [
                        {{"pattern": "brief pattern description", "lesson": "actionable lesson"}},
                        ...
                    ],
                    "cases_summarized": (number)
                }}""")

            user_prompt = json.dumps(
                {"reflections": [
                    {k: v for k, v in r.items() if k not in ("tick", "patient_id")}
                    for r in to_compress
                ]},
                ensure_ascii=False,
            )

            response = await self.model.chat(user_prompt, system_prompt=system_prompt)
            save_prompt(
                agent_id=self.agent_id,
                tick=self.global_tick,
                context_id=reflection_type,
                stage="reflect_compress",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response=response,
                plugin_logger=logger,
            )
            compressed = json.loads(clean_json_response(response))
            compressed_key = (
                f"{self.reflection_namespace}:{self.agent_id}:compressed_{reflection_type}_reflections"
            )
            existing_compressed = await self.redis.get(compressed_key) or []
            existing_compressed.append(
                {
                    "tick": self.global_tick,
                    "insights": compressed.get("key_insights", []),
                    "cases_count": compressed.get("cases_summarized", len(to_compress)),
                }
            )
            await self.redis.set(compressed_key, existing_compressed)
            del reflections_list[:-5]

            logger.info(f"Compressed {len(to_compress)} {reflection_type} reflections into key insights")

        except Exception as e:
            logger.warning(f"Failed to compress {reflection_type} reflections: {e}")

    async def _cleanup_patient_data(self, patient_id: str):
        """
        Clean up all data related to a completed patient after reflection.
        This prevents memory explosion by removing:
        - Chat history with the patient and related consultations
        - Patient tracking data in plan plugin

        Args:
            patient_id: Patient ID to clean up
        """
        try:
            plan_plugin = self._get_plan_plugin()
            perceive_plugin = self._get_perceive_plugin()

            if plan_plugin:
                plan_plugin.cleanup_patient_data(patient_id)

            if perceive_plugin:
                perceive_plugin.cleanup_patient_data(patient_id)

            logger.info(f"[{self.agent_id}] Successfully cleaned up data for patient {patient_id}")

        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to clean up patient data for {patient_id}: {e}")

    def _get_temp_vars(self) -> Optional[Dict[str, Any]]:
        """Get temporary variables for checkpoint/resume."""
        return {
            "diagnosis_reflections": self._diagnosis_reflections,
            "examination_reflections": self._examination_reflections,
            "treatment_reflections": self._treatment_reflections,
            "total_reflection_count": self._total_reflection_count,
            "last_executed_tick": getattr(self, 'global_tick', -1),
        }

    def _set_temp_vars(self, vars_dict: Dict[str, Any]) -> None:
        """Restore temporary variables from checkpoint."""
        self._diagnosis_reflections = vars_dict.get("diagnosis_reflections", [])
        self._examination_reflections = vars_dict.get("examination_reflections", [])
        self._treatment_reflections = vars_dict.get("treatment_reflections", [])
        self._total_reflection_count = vars_dict.get("total_reflection_count", 0)
        self.global_tick = vars_dict.get("last_executed_tick", -1)

    async def load_from_db(self) -> None:
        """Load temporary variables from Redis before execute()."""
        redis_key = f"{self.reflection_namespace}:{self.agent_id}:temp_vars:DoctorReflectPlugin"
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

        redis_key = f"{self.reflection_namespace}:{self.agent_id}:temp_vars:DoctorReflectPlugin"
        try:
            await self.redis.set(redis_key, vars_dict)
            logger.debug(f"[{self.agent_id}] Saved temp vars to Redis")
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Failed to save temp vars to Redis: {e}")
