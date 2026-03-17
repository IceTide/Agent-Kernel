"""Simulation status API routes - using EventStore as data source."""

import os
from typing import Optional

from fastapi import APIRouter, Query

from ..services import get_event_store

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


@router.get("/status", summary="获取模拟状态")
async def get_simulation_status() -> dict:
    """
    获取当前模拟的状态信息。
    """
    store = get_event_store()
    return store.get_simulation_status()


@router.get("/tick", summary="获取当前 tick")
async def get_current_tick() -> dict:
    """获取当前模拟的 tick 值。"""
    store = get_event_store()
    return {"current_tick": store.get_current_tick()}


@router.post("/log-dir", summary="设置日志目录")
async def set_log_dir(log_dir: str = Query(..., description="日志目录路径")) -> dict:
    """
    设置日志目录，用于读取历史数据。
    
    这允许前端在模拟结束后仍然可以查看历史数据。
    """
    store = get_event_store()
    
    if not os.path.isdir(log_dir):
        return {"success": False, "error": f"Directory not found: {log_dir}"}
    
    store.set_log_dir(log_dir)
    return {"success": True, "log_dir": log_dir}


@router.get("/events", summary="获取所有事件")
async def get_all_events(
    limit: int = Query(100, description="最大返回数量"),
    offset: int = Query(0, description="偏移量"),
) -> dict:
    """
    获取所有事件（用于调试）。
    """
    store = get_event_store()
    events = store._all_events[offset:offset + limit]
    
    return {
        "total": len(store._all_events),
        "offset": offset,
        "limit": limit,
        "events": events,
    }


@router.get("/events/by-tick/{tick}", summary="获取指定 tick 的事件")
async def get_events_by_tick(tick: int) -> dict:
    """获取指定 tick 的所有事件。"""
    store = get_event_store()
    
    events = [e for e in store._all_events if e.get("tick") == tick]
    
    return {
        "tick": tick,
        "event_count": len(events),
        "events": events,
    }


@router.get("/statistics", summary="获取模拟统计数据")
async def get_simulation_statistics() -> dict:
    """
    获取模拟的统计数据 (SimulationStatistics)。
    
    包括:
    - 总医生数、患者数
    - 总对话数
    - 总检查数、处方数
    - 各状态的患者分布
    """
    store = get_event_store()
    
    doctors = store.get_doctors()
    patients = store.get_patients()
    messages = store.get_messages()
    examinations = store.get_examinations()
    prescriptions = store.get_prescriptions()
    from .patient import normalize_phase
    
    phase_distribution = {}
    for patient in patients:
        patient_id = patient.get("id", "")
        status = store.get_patient_status(patient_id)
        raw_phase = status.get("phase") or status.get("event") or "idle"
        phase = normalize_phase(raw_phase)
        phase_distribution[phase] = phase_distribution.get(phase, 0) + 1
    active_pairs = set()
    for msg in messages:
        sender = msg.get("sender", "")
        receiver = msg.get("receiver", "")
        if sender and receiver:
            pair = tuple(sorted([sender, receiver]))
            active_pairs.add(pair)
    
    return {
        "total_doctors": len(doctors),
        "total_patients": len(patients),
        "total_messages": len(messages),
        "total_examinations": len(examinations),
        "total_prescriptions": len(prescriptions),
        "active_consultations": len(active_pairs),
        "phase_distribution": phase_distribution,
        "current_tick": store.get_current_tick(),
    }
