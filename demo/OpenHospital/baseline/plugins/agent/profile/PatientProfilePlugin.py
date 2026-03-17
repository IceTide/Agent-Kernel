"""
Patient Profile Plugin for Hospital Simulation.
Manages patient profile data with Redis persistence and Milvus vector storage for medical history retrieval.
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4

from agentkernel_distributed.mas.agent.base.plugin_base import ProfilePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.types.schemas.vectordb import VectorDocument, VectorSearchRequest

logger = get_logger(__name__)


class PatientProfilePlugin(ProfilePlugin):
    """
    Patient profile plugin with vector storage for medical history.

    Features:
    - Redis storage for basic profile data (inherits from ProfileStoragePlugin)
    - Milvus vector storage for medical history semantic search
    - Automatic deduplication: checks if patient_id exists before inserting
    - Vectorizes present_illness_history, medical_history, personal_history, family_history
    """

    def __init__(
        self,
        redis: RedisKVAdapter,
        milvus: Any,                       
        profile_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.redis = redis
        self.milvus = milvus
        self._profile_data = profile_data if profile_data is not None else {}
        self._patient_id: Optional[str] = None
        self._is_indexed = False

    async def init(self):
        """Initialize plugin, sync data to Redis, and index medical history to Milvus."""
        self.agent_id = self._component.agent.agent_id
        self._patient_id = self._profile_data.get("id", self.agent_id)
        if self._profile_data:
            await self.redis.set(f"{self.agent_id}:profile", self._profile_data)
            logger.info(f"Profile initialized for {self.agent_id}")
        await self._index_medical_history()

    async def execute(self, current_tick: int):
        """Sync profile data to Redis each tick."""
        await self.redis.set(f"{self.agent_id}:profile", self._profile_data)

    async def set_profile(self, key: str, value: Any):
        """Set a specific profile field."""
        self._profile_data[key] = value
        await self.redis.set(f"{self.agent_id}:profile", self._profile_data, key)

    async def get_profile(self, key: Optional[str] = None) -> Any:
        """Get profile data.

        Args:
            key: Optional field name. If None, returns entire profile.

        Returns:
            The specific field value if key is provided, or entire profile dict.
        """
        if key is None:
            return self._profile_data
        return self._profile_data.get(key)

    async def _index_medical_history(self):
        """
        Index patient medical history to Milvus for semantic search.

        Checks if patient_id already exists in Milvus to avoid duplicate indexing.
        Vectorizes: present_illness_history, medical_history, personal_history, family_history
        """
        if self._is_indexed:
            logger.debug(f"Patient {self._patient_id} already indexed, skipping.")
            return
        patient_exists = await self._check_patient_exists()
        if patient_exists:
            logger.info(f"Patient {self._patient_id} already exists in Milvus, skipping indexing.")
            self._is_indexed = True
            return
        all_documents = []
        present_illness = self._profile_data.get("present_illness_history", {})
        if present_illness:
            docs = await self._create_history_documents(
                history_type="present_illness_history",
                history_data=present_illness,
                patient_id=self._patient_id,
            )
            all_documents.extend(docs)
        medical_history = self._profile_data.get("medical_history", {})
        if medical_history:
            docs = await self._create_history_documents(
                history_type="medical_history",
                history_data=medical_history,
                patient_id=self._patient_id,
            )
            all_documents.extend(docs)
        personal_history = self._profile_data.get("personal_history", {})
        if personal_history:
            docs = await self._create_history_documents(
                history_type="personal_history",
                history_data=personal_history,
                patient_id=self._patient_id,
            )
            all_documents.extend(docs)
        family_history = self._profile_data.get("family_history", {})
        if family_history:
            docs = await self._create_history_documents(
                history_type="family_history",
                history_data=family_history,
                patient_id=self._patient_id,
            )
            all_documents.extend(docs)
        if all_documents:
            await self.milvus.upsert(all_documents)
            self._is_indexed = True
            logger.info(f"Indexed {len(all_documents)} field-level documents for patient {self._patient_id}")
        else:
            logger.warning(f"No medical history data to index for patient {self._patient_id}")

    async def _check_patient_exists(self) -> bool:
        """
        Check if patient already exists in Milvus by searching for patient_id.

        Returns:
            True if patient_id exists in Milvus, False otherwise.
        """
        try:
            filter_expr = f"patient_id == '{self._patient_id}'"
            results = await self.milvus.client.query(
                collection_name=self.milvus._config.get("collection_name"),
                filter=filter_expr,
                limit=1,
            )
            return len(results) > 0
        except Exception as e:
            logger.warning(f"Error checking if patient exists: {e}, assuming patient doesn't exist.")
            return False

    async def _create_history_documents(
        self,
        history_type: str,
        history_data: Dict[str, Any],
        patient_id: str,
    ) -> List[VectorDocument]:
        """
        Create multiple VectorDocuments from history data, one per field.

        This enables fine-grained retrieval where each field can be matched independently.

        Args:
            history_type: Type of history (e.g., 'medical_history', 'present_illness_history')
            history_data: Dictionary containing history information
            patient_id: Patient identifier

        Returns:
            List of VectorDocuments, one for each field in the history data.
        """
        documents = []

        def flatten_to_documents(data: Dict[str, Any], prefix: str = "") -> None:
            """
            Recursively flatten nested dictionaries and create documents for each field.

            Args:
                data: Dictionary containing field data
                prefix: Field path prefix (e.g., "present_illness_history_current_general_status")
            """
            for key, value in data.items():
                full_key = f"{prefix}_{key}" if prefix else key
                field_path = f"{history_type}.{full_key}"

                if isinstance(value, dict):
                    flatten_to_documents(value, full_key)
                else:
                    if isinstance(value, list):
                        value_str = ', '.join(str(v) for v in value) if value else "None"
                    else:
                        value_str = str(value) if value else "None"
                    content = f"Field: {field_path}\nValue: {value_str}"
                    metadata = {
                        "patient_id": patient_id,
                        "history_type": history_type,
                        "field_name": full_key,                                                         
                        "field_path": field_path,                               
                        "agent_id": self.agent_id,
                    }
                    doc = VectorDocument(
                        id=f"{patient_id}_{field_path}_{uuid4().hex[:8]}",
                        tick=0,
                        content=content,
                        metadata=metadata,
                    )
                    documents.append(doc)
        flatten_to_documents(history_data)

        return documents

    async def search_medical_history(
        self,
        query: str,
        top_k: int = 5,
        history_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search patient's medical history by semantic similarity.

        Args:
            query: Search query (e.g., "allergies", "previous surgeries")
            top_k: Number of results to return
            history_type: Optional filter by history type
                (e.g., 'medical_history', 'present_illness_history')

        Returns:
            List of search results with document content and scores.
        """
        filter_expr = f"patient_id == '{self._patient_id}'"
        if history_type:
            filter_expr += f" && history_type == '{history_type}'"
        search_request = VectorSearchRequest(
            query=query,
            top_k=top_k,
            filter=filter_expr,
        )
        results = await self.milvus.search(search_request)
        formatted_results = []
        for result in results:
            formatted_results.append({
                "content": result.document.content,
                "metadata": result.document.metadata,
                "score": result.score,
            })

        logger.debug(f"Found {len(formatted_results)} results for query: {query}")
        return formatted_results

    async def get_all_history_types(self) -> List[str]:
        """
        Get all history types available for this patient in Milvus.

        Returns:
            List of history types (e.g., ['medical_history', 'present_illness_history'])
        """
        try:
            filter_expr = f"patient_id == '{self._patient_id}'"
            results = await self.milvus.client.query(
                collection_name=self.milvus._config.get("collection_name"),
                filter=filter_expr,
                output_fields=["history_type"],
                limit=100,                                      
            )
            history_types = list(set(r.get("history_type", "") for r in results if r.get("history_type")))
            return history_types
        except Exception as e:
            logger.warning(f"Error getting history types: {e}")
            return []

    async def clear(self) -> None:
        """Clear all Redis data for this patient when being cleaned up.

        Note: Milvus data is NOT deleted as it may be needed for post-simulation analysis.
        """
        try:
            await self.redis.delete(f"{self.agent_id}:profile")
            logger.info(f"[{self.agent_id}] Cleared PatientProfilePlugin Redis data")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to clear PatientProfilePlugin Redis data: {e}")
