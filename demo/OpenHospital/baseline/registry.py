"""
Registry for Hospital Simulation.
Maps plugin names to their implementations.
Following Baseline_instruction.md: Only Patient and Doctor agents.
"""
from agentkernel_distributed.mas.agent.components import (
    ProfileComponent,
    StateComponent,
    PlanComponent,
    PerceiveComponent,
    ReflectComponent,
    InvokeComponent,
)
from baseline.plugins.agent.profile.DoctorProfilePlugin import DoctorProfilePlugin
from baseline.plugins.agent.plan.DoctorPlannerPlugin import DoctorPlannerPlugin
from baseline.plugins.agent.perceive.DoctorPerceptionPlugin import DoctorPerceptionPlugin
from baseline.plugins.agent.reflect.DoctorReflectPlugin import DoctorReflectPlugin
from baseline.plugins.agent.invoke.DoctorInvokePlugin import DoctorInvokePlugin
from baseline.plugins.agent.state.DoctorStatePlugin import DoctorStatePlugin
from baseline.plugins.agent.plan.PatientPlannerPlugin import PatientPlannerPlugin
from baseline.plugins.agent.perceive.PatientPerceptionPlugin import PatientPerceptionPlugin
from baseline.plugins.agent.invoke.PatientInvokePlugin import PatientInvokePlugin
from baseline.plugins.agent.profile.PatientProfilePlugin import PatientProfilePlugin
from baseline.plugins.agent.state.PatientStatePlugin import PatientStatePlugin
from agentkernel_distributed.mas.action.components import CommunicationComponent, ToolsComponent, OtherActionsComponent

from baseline.plugins.action.communication.communication_plugin import HospitalCommunicationPlugin
from baseline.plugins.action.tools.tools_plugin import HospitalToolsPlugin
from baseline.plugins.action.otheractions.other_actions_plugin import HospitalOtherActionsPlugin
from agentkernel_distributed.mas.environment.components import (
    RelationComponent,
    get_or_create_component_class,
)
from baseline.plugins.environment.relation.hospital_relation_plugin import HospitalRelationPlugin
from baseline.plugins.environment.hospital_system.hospital_system_plugin import HospitalSystemPlugin
from baseline.plugins.environment.examination_room.examination_room_plugin import (
    ExaminationRoomPlugin,
)
from agentkernel_distributed.toolkit.storages.graph_adapters.redis import RedisGraphAdapter
from agentkernel_distributed.toolkit.storages.kv_adapters.redis import RedisKVAdapter
from agentkernel_distributed.toolkit.storages.vectordb_adapters.milvus import MilvusVectorAdapter
from agentkernel_distributed.toolkit.models.api.openai import OpenAIProvider
from agentkernel_distributed.mas.system.components import Messager, Recorder, Timer
from baseline.custom_controller import CustomController
from baseline.custom_pod_manager import CustomPodManager
from baseline.custom_builder import CustomBuilder

agent_plugin_class_map = {
    "DoctorProfilePlugin": DoctorProfilePlugin,
    "DoctorPlannerPlugin": DoctorPlannerPlugin,
    "DoctorInvokePlugin": DoctorInvokePlugin,
    "DoctorPerceptionPlugin": DoctorPerceptionPlugin,
    "DoctorReflectPlugin": DoctorReflectPlugin,
    "DoctorStatePlugin": DoctorStatePlugin,
    "PatientPlannerPlugin": PatientPlannerPlugin,
    "PatientInvokePlugin": PatientInvokePlugin,
    "PatientPerceptionPlugin": PatientPerceptionPlugin,
    "PatientProfilePlugin": PatientProfilePlugin,
    "PatientStatePlugin": PatientStatePlugin,
}

agent_component_class_map = {
    "profile": ProfileComponent,
    "state": StateComponent,
    "plan": PlanComponent,
    "perceive": PerceiveComponent,
    "reflect": ReflectComponent,
    "invoke": InvokeComponent,
}

action_component_class_map = {
    "communication": CommunicationComponent,
    "tools": ToolsComponent,
    "otheractions": OtherActionsComponent,
}

action_plugin_class_map = {
    "HospitalCommunicationPlugin": HospitalCommunicationPlugin,
    "HospitalToolsPlugin": HospitalToolsPlugin,
    "HospitalOtherActionsPlugin": HospitalOtherActionsPlugin,
}

HospitalSystemComponent = get_or_create_component_class("hospital_system")
ExaminationRoomComponent = get_or_create_component_class("examination_room")

environment_component_class_map = {
    "relation": RelationComponent,
    "hospital_system": HospitalSystemComponent,
    "examination_room": ExaminationRoomComponent,
}

environment_plugin_class_map = {
    "HospitalRelationPlugin": HospitalRelationPlugin,
    "HospitalSystemPlugin": HospitalSystemPlugin,
    "ExaminationRoomPlugin": ExaminationRoomPlugin,
}

system_component_class_map = {
    "messager": Messager,
    "recorder": Recorder,
    "timer": Timer,
}

adapter_class_map = {
    "RedisKVAdapter": RedisKVAdapter,
    "RedisGraphAdapter": RedisGraphAdapter,
    "MedicalVectorAdapter": MilvusVectorAdapter,
    "ReflectionVectorAdapter": MilvusVectorAdapter,
    "ExaminationsVectorAdapter": MilvusVectorAdapter,
    "PatientVectorAdapter": MilvusVectorAdapter,
}

model_class_map = {
    "OpenAIProvider": OpenAIProvider,
}

from agentkernel_distributed.toolkit.models.router import model_hook, ChatCompleteEvent


@model_hook("post_chat")
async def record_llm_inference(event: ChatCompleteEvent, system) -> None:
    """
    Record LLM token usage to the recorder.
    
    This hook is called after each successful LLM chat request.
    
    Args:
        event: ChatCompleteEvent containing response and token usage info.
        system: System handle for accessing timer, recorder, etc.
    """
    if event.token_usage is None:
        return
        
    try:
        current_tick = await system.run("timer", "get_tick")
        await system.run(
            "recorder", "record_event",
            tick=current_tick,
            event_type="LLM_INFERENCE",
            payload={
                "prompt_tokens": event.token_usage.prompt_tokens,
            },
        )
    except Exception:
        pass                                      

RESOURCE_MAPS = {
    "agent_components": agent_component_class_map,
    "agent_plugins": agent_plugin_class_map,
    "action_components": action_component_class_map,
    "action_plugins": action_plugin_class_map,
    "environment_components": environment_component_class_map,
    "environment_plugins": environment_plugin_class_map,
    "system_components": system_component_class_map,
    "adapters": adapter_class_map,
    "models": model_class_map,
    "model_hooks": record_llm_inference,
    "controller": CustomController,
    "pod_manager": CustomPodManager,
    "builder": CustomBuilder,
}
