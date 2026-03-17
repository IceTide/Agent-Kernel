"""
Relation Basic Operations Plugin for Hospital Simulation.
Manages relationships between agents (patient-doctor, nurse-patient, etc.).
"""

import math
import numpy as np
from typing import Dict, Any, List, Optional, Callable

from agentkernel_distributed.mas.environment.base.plugin_base import RelationPlugin
from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)


class HospitalRelationPlugin(RelationPlugin):
    """
    Relation plugin for managing hospital agent relationships.
    Handles patient-doctor assignments, nurse-patient interactions, etc.
    """

    def __init__(
        self,
        redis: Callable = None,
        nodes: Optional[Dict[str, Any]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize relation plugin.

        Args:
            redis: Redis graph adapter for persistence
            nodes: Initial node data (agent profiles)
            edges: Initial edge data (relationships)
        """
        super().__init__()
        self.redis = redis
        self.nodes = [{"id": node_id, "properties": props} for node_id, props in nodes.items()] if nodes else []
        self.edges = []
        if edges:
            for edge in edges:
                new_edge = {}
                new_edge["source_id"] = edge.get("source_id", edge.get("source"))
                new_edge["target_id"] = edge.get("target_id", edge.get("target"))
                properties = edge.get("properties", {}).copy()
                for k, v in edge.items():
                    if k not in ["source", "target", "source_id", "target_id", "properties"]:
                        properties[k] = v

                new_edge["properties"] = properties
                self.edges.append(new_edge)

    async def init(self):
        """Initialize plugin."""
        pass

    async def save_to_db(self):
        """Save current state to database."""
        logger.info(f"Saving relation data: {len(self.nodes)} nodes, {len(self.edges)} edges.")
        if self.nodes or self.edges:
            data = {"nodes": self.nodes, "edges": self.edges}
            await self.import_data(data)

    async def get_agent_relationships(
        self,
        agent_id: str,
        relation: Optional[str] = None,
        edge_type: Optional[str] = None,
        top_k: Optional[int] = None,
        temperature: Optional[float] = 0.2,
    ) -> Dict[str, Any]:
        """Get agent's relationships with optional filtering and sampling.

        Args:
            agent_id: Agent to query relationships for
            relation: Filter by direction ('in' or 'out')
            edge_type: Filter by edge property 'relation_type' (e.g., 'colleague')
            top_k: Maximum number of relationships to return
            temperature: Temperature for softmax sampling (higher = more random)

        Returns:
            Dict with 'edges' and 'nodes' containing relationship data
        """
        logger.debug(f"get_agent_relationships called for {agent_id}, edge_type={edge_type}")
        
        if relation == "in":
            edges = await self.redis.get_node_in_edges(agent_id)
        elif relation == "out":
            edges = await self.redis.get_node_out_edges(agent_id)
        else:
            in_edges = await self.redis.get_node_in_edges(agent_id)
            out_edges = await self.redis.get_node_out_edges(agent_id)
            edges = in_edges + out_edges
        
        logger.debug(f"Retrieved {len(edges)} total edges for {agent_id}")
        if edges and len(edges) > 0:
            logger.debug(f"Sample edge structure: {edges[0]}")
        if edge_type:
            logger.debug(f"Filtering edges by edge_type='{edge_type}'")
            edges = [
                e for e in edges 
                if e.get("relation_type") == edge_type
            ]
            logger.debug(f"After filtering by edge_type={edge_type}: {len(edges)} edges")
        if top_k is not None and len(edges) > top_k:
            weights = np.array([math.exp(e.get("strength", 0) / temperature) for e in edges], dtype=np.float64)
            probs = weights / weights.sum()
            probs = np.clip(probs, 0, 1)
            probs = probs / probs.sum()

            k = min(top_k, len(edges))
            sampled_indices = np.random.choice(len(edges), size=k, replace=False, p=probs)
            edges = [edges[i] for i in sampled_indices]
        node_ids = set()
        for edge in edges:
            source_id = edge.get("source_id")
            target_id = edge.get("target_id")
            if source_id and source_id != agent_id:
                node_ids.add(source_id)
            if target_id and target_id != agent_id:
                node_ids.add(target_id)
        nodes: Dict[str, Any] = {}
        for node_id in node_ids:
            node_payload = await self.redis.get_node(node_id)
            if node_payload is not None:
                nodes[node_id] = node_payload
        
        logger.debug(f"Returning {len(edges)} edges and {len(nodes)} nodes for {agent_id}")
        return {"edges": edges, "nodes": nodes}

    async def get_patients_of_doctor(self, doctor_id: str) -> List[str]:
        """Get all patients assigned to a doctor."""
        edges = await self.redis.get_node_in_edges(doctor_id)
        patients = []
        for edge in edges:
            if edge.get("type") == "patient_of":
                patients.append(edge.get("source_id"))
        return patients

    async def get_doctor_of_patient(self, patient_id: str) -> Optional[str]:
        """Get the doctor assigned to a patient."""
        edges = await self.redis.get_node_out_edges(patient_id)
        for edge in edges:
            if edge.get("type") == "patient_of":
                return edge.get("target_id")
        return None

    async def import_data(self, data: Dict[str, Any]) -> None:
        """Import relationship data."""
        return await self.redis.import_data(data)

    async def export_data(self) -> Dict[str, Any]:
        """Export relationship data."""
        return await self.redis.export_data()
