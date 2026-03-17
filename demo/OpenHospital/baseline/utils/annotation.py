"""
Annotation utilities for hospital simulation.
Extends AgentCall to support role-based action filtering.
"""

from typing import Any, Callable, TypeVar, cast, Dict, List, Optional
from dataclasses import dataclass

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ActionMetadata:
    """Metadata for action functions with role-based filtering."""
    categories: Dict[str, List[str]]
    tags: List[str] = None
    action_preferences: Dict[str, Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.action_preferences is None:
            self.action_preferences = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
        return {
            "categories": self.categories,
            "tags": self.tags,
            "action_preferences": self.action_preferences
        }


def AgentCall(
    func: Optional[F] = None,
    *,
    categories: Optional[Dict[str, List[str]]] = None,
    tags: Optional[List[str]] = None,
    action_preferences: Optional[Dict[str, Dict[str, Any]]] = None
) -> F:
    """
    Mark a plugin method as agent-callable with optional role-based categorization.

    The decorated function will get an ``_annotation`` attribute for method discovery,
    and an optional ``_metadata`` attribute for categorization.

    Args:
        func: The function to decorate (when used as @AgentCall).
        categories: Categorization information for role-based filtering.
            Example: {
                "role": ["doctor", "nurse"],  # Which agent roles can use this action
                "location": ["consultation_room", "pharmacy"]  # Where this action is available
            }
        tags: List of tags for additional filtering
        action_preferences: Action preferences defining the preference distribution for states.

    Example:
        @AgentCall()
        async def diagnose_patient(self, ...):
            ...

        @AgentCall()
        async def generate_report(self, ...):
            ...

    Returns:
        Callable: The original function with applied annotation.
    """
    def decorator(f: F) -> F:
        setattr(f, "_annotation", "AgentCall")
        if categories is not None or tags is not None or action_preferences is not None:
            metadata = ActionMetadata(
                categories=categories or {},
                tags=tags or [],
                action_preferences=action_preferences or {}
            )
            setattr(f, "_metadata", metadata)
        
        return cast(F, f)
    if func is None:
        return decorator
    else:
        return decorator(func)


def ServiceCall(func: F) -> F:
    """
    Mark a plugin method as callable by external services or management.

    The decorated function will get an ``_annotation`` attribute for method discovery.

    Args:
        func: The function to decorate.

    Returns:
        Callable: The original function with applied annotation.
    """
    setattr(func, "_annotation", "ServiceCall")
    return cast(F, func)
