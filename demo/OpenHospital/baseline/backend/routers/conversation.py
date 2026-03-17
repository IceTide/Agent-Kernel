"""Conversation API routes - using EventStore as data source."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..services import get_event_store

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def build_conversation_summary(participants: List[str], messages: List[dict]) -> dict:
    """构建 ConversationSummary 格式的响应。"""
    sorted_participants = sorted(participants)
    conv_id = f"{sorted_participants[0]}-{sorted_participants[1]}"

    last_tick = max((m.get("tick", 0) for m in messages), default=0) if messages else None

    return {
        "id": conv_id,
        "participants": sorted_participants,
        "message_count": len(messages),
        "last_message_tick": last_tick,
    }


def build_conversation(participants: List[str], messages: List[dict]) -> dict:
    """构建 Conversation 格式的响应。"""
    sorted_participants = sorted(participants)
    conv_id = f"{sorted_participants[0]}-{sorted_participants[1]}"
    sorted_messages = sorted(messages, key=lambda m: (m.get("tick", 0), m.get("timestamp", "")))
    seen = set()
    unique_messages = []
    for msg in sorted_messages:
        tick = msg.get("tick", 0)
        sender = msg.get("sender", "")
        content = msg.get("full_content") or msg.get("content", "")
        key = (tick, sender, content[:100])                      
        if key not in seen:
            seen.add(key)
            unique_messages.append(msg)

    formatted_messages = []
    for idx, msg in enumerate(unique_messages):
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")
        if sender.startswith("Doctor_") and receiver.startswith("Patient_"):
            msg_type = "doctor_to_patient"
        elif sender.startswith("Patient_") and receiver.startswith("Doctor_"):
            msg_type = "patient_to_doctor"
        else:
            msg_type = "agent_to_agent"
        formatted_messages.append(
            {
                "id": idx + 1,
                "sender": sender,
                "content": msg.get("full_content") or msg.get("content", ""),
                "created_at": msg.get("tick", 0),
                "extra": {"type": msg_type},
            }
        )

    return {
        "id": conv_id,
        "type": "consultation",
        "participants": sorted_participants,
        "messages": formatted_messages,
    }


@router.get("", summary="获取所有对话摘要")
async def get_all_conversations(
    patient_id: Optional[str] = Query(None, description="按患者ID过滤"),
    doctor_id: Optional[str] = Query(None, description="按医生ID过滤"),
) -> List[dict]:
    """
    获取对话摘要列表 (ConversationSummary[])。

    返回所有唯一医患对的对话摘要。
    """
    store = get_event_store()
    agent_id = patient_id or doctor_id
    messages = store.get_messages(agent_id)
    conversations_map = {}
    for msg in messages:
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")

        if not sender or not receiver:
            continue
        pair = tuple(sorted([sender, receiver]))

        if pair not in conversations_map:
            conversations_map[pair] = []

        conversations_map[pair].append(msg)
    result = []
    for (p1, p2), msgs in conversations_map.items():
        if patient_id and patient_id not in (p1, p2):
            continue
        if doctor_id and doctor_id not in (p1, p2):
            continue

        result.append(build_conversation_summary([p1, p2], msgs))
    result.sort(key=lambda x: x.get("last_message_tick", 0) or 0, reverse=True)

    return result


@router.get("/{conversation_id}", summary="获取对话详情")
async def get_conversation(conversation_id: str) -> dict:
    """
    获取对话详情 (Conversation)。

    conversation_id 格式: "{agent1_id}-{agent2_id}" (按字母序排列)
    """
    parts = conversation_id.split("-", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format. Expected: agent1-agent2")

    agent1_id, agent2_id = parts

    store = get_event_store()
    messages = store.get_conversation(agent1_id, agent2_id)

    if not messages:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")

    return build_conversation([agent1_id, agent2_id], messages)


@router.get("/between/{agent1_id}/{agent2_id}", summary="获取两个 agent 之间的对话")
async def get_conversation_between(agent1_id: str, agent2_id: str) -> dict:
    """
    获取两个 agent 之间的对话 (Conversation)。
    """
    store = get_event_store()
    messages = store.get_conversation(agent1_id, agent2_id)

    return build_conversation([agent1_id, agent2_id], messages)


@router.get("/agent/{agent_id}", summary="获取 agent 的所有对话")
async def get_agent_conversations(agent_id: str) -> dict:
    """
    获取某个 agent 的所有对话，按对话对象分组。
    """
    store = get_event_store()
    messages = store.get_messages(agent_id)
    conversations = {}
    for msg in messages:
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")
        other_agent = receiver if sender == agent_id else sender

        if not other_agent:
            continue

        if other_agent not in conversations:
            conversations[other_agent] = []

        conversations[other_agent].append(msg)
    conversation_list = []
    for other_agent, msgs in conversations.items():
        conversation_list.append(build_conversation([agent_id, other_agent], msgs))

    return {
        "agent_id": agent_id,
        "conversations": conversation_list,
        "total_messages": len(messages),
        "conversation_partners": list(conversations.keys()),
    }


@router.get("/recent", summary="获取最近的对话消息")
async def get_recent_conversations(
    limit: int = Query(20, description="返回数量"),
) -> List[dict]:
    """
    获取最近的对话消息（原始消息格式）。
    """
    store = get_event_store()
    messages = store.get_messages()
    messages = sorted(messages, key=lambda m: (m.get("tick", 0), m.get("timestamp", "")), reverse=True)

    return messages[:limit]
