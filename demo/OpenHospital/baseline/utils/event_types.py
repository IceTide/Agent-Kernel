"""
Event types for Hospital Simulation evaluation.

This module defines the event types used for recording and evaluating
the hospital simulation. These event types are application-specific
and not part of the core framework.

See docs/evaluation_events.md for detailed documentation.
"""

from enum import Enum

__all__ = ["HospitalEventType"]


class HospitalEventType(str, Enum):
    """
    Event types specific to hospital simulation evaluation.
    
    These event types are used with the framework's Recorder component
    to track simulation events for later evaluation.
    """
    SCHEDULE_EXAMINATION = "SCHEDULE_EXAMINATION"
    PRESCRIBE_TREATMENT = "PRESCRIBE_TREATMENT"
    LLM_INFERENCE = "LLM_INFERENCE"
    PATIENT_REGISTER = "PATIENT_REGISTER"
    PATIENT_MOVE = "PATIENT_MOVE"
    DO_EXAMINATION = "DO_EXAMINATION"
    RECEIVE_TREATMENT = "RECEIVE_TREATMENT"
    SEND_MESSAGE = "SEND_MESSAGE"
    SYSTEM_CONFIG = "SYSTEM_CONFIG"
    IDLE = "IDLE"
