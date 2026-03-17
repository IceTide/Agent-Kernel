"""
Action-related type definitions for Hospital Simulation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from agentkernel_distributed.types.schemas.action import ActionResult


class ActionOutcome(Enum):
    """Outcome of an action execution."""
    COMPLETED = "completed"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"


@dataclass
class CurrentAction:
    """Represents the currently executing action."""
    description: str
    total_ticks: int
    remaining_ticks: int
    result: Optional[ActionResult] = None
    id: str = ""                                  
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "total_ticks": self.total_ticks,
            "remaining_ticks": self.remaining_ticks,
            "result": self.result.to_dict() if self.result else None,
            "id": self.id,
        }


@dataclass
class ActionRecord:
    """Record of a completed action."""
    description: str
    duration_ticks: int
    outcome: ActionOutcome
    result: Optional[ActionResult] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "duration_ticks": self.duration_ticks,
            "outcome": self.outcome.value,
            "result": self.result.to_dict() if self.result else None,
        }
