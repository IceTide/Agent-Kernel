"""Conversation schemas."""

from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel


MessageType = Literal["doctor_to_patient", "patient_to_doctor", "agent_to_agent"]


class MessageExtra(BaseModel):
    """Message extra info."""
    type: Optional[MessageType] = None


class ConversationMessage(BaseModel):
    """A single message in conversation."""
    id: int
    sender: str
    content: str
    created_at: int
    extra: Optional[MessageExtra] = None


class Conversation(BaseModel):
    """Full conversation."""
    id: str
    type: str = "consultation"
    participants: List[str]
    messages: List[ConversationMessage] = []


class ConversationSummary(BaseModel):
    """Conversation summary for list view."""
    id: str
    participants: List[str]
    message_count: int = 0
    last_message_tick: Optional[int] = None

