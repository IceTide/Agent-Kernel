
"""
File Event Logger for Hospital Simulation.
Singleton class for writing simulation events to files in chronological order.
Supports multiple output formats for frontend consumption.

Memory Optimization:
- 内存缓存使用 deque 限制大小
- 旧数据从磁盘按需读取
"""

import os
import asyncio
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from collections import deque

import aiofiles
MAX_MESSAGES_CACHE = 1000
MAX_EXAMINATIONS_CACHE = 500
MAX_PRESCRIPTIONS_CACHE = 500
TICK_EVENTS_SUBDIR = "tick_events"


class FileEventLogger:
    """
    单例类，用于将模拟事件按时序写入文件。

    输出文件结构:
    - tick_events/events_tick_{N}.log: 每个 tick 的所有事件
    - agents.jsonl: 所有 agent 的 profile 信息
    - messages.jsonl: 所有对话消息
    - patient_status.jsonl: 患者状态变化
    - examinations.jsonl: 检查记录
    - prescriptions.jsonl: 处方记录
    - all_events.jsonl: 所有事件的汇总

    内存优化:
    - 只保留最近的 N 条消息/检查/处方在内存中
    - 完整数据从磁盘读取
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(FileEventLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.output_dir: Optional[str] = None
        self.lock = asyncio.Lock()
        self._initialized = True
        self._agents: Dict[str, Dict[str, Any]] = {}                                  
        self._messages: deque = deque(maxlen=MAX_MESSAGES_CACHE)
        self._patient_status: Dict[str, Dict[str, Any]] = {}                                           
        self._examinations: deque = deque(maxlen=MAX_EXAMINATIONS_CACHE)
        self._prescriptions: deque = deque(maxlen=MAX_PRESCRIPTIONS_CACHE)
        self._current_tick: int = 0

        print(f"FileEventLogger initialized in process {os.getpid()}.")

    def start_logging(
        self,
        output_dir: str,
        project_path: Optional[str] = None,
        clear_old_logs: bool = True,
        patient_profiles_path: Optional[str] = None,
        doctor_profiles_path: Optional[str] = None,
    ) -> str:
        """
        设置日志目录，并返回该目录的路径。
        
        Args:
            output_dir: 日志输出目录
            project_path: 项目路径，用于加载初始 agent profiles
            clear_old_logs: 是否清除旧日志文件（默认 True）
            patient_profiles_path: 可选，当前运行的患者 profile 文件路径（优先于默认 data 目录）
            doctor_profiles_path: 可选，当前运行的医生 profile 文件路径（优先于默认 data 目录）
        """
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir = output_dir
        os.makedirs(os.path.join(output_dir, TICK_EVENTS_SUBDIR), exist_ok=True)
        self._agents = {}
        self._messages = deque(maxlen=MAX_MESSAGES_CACHE)
        self._patient_status = {}
        self._examinations = deque(maxlen=MAX_EXAMINATIONS_CACHE)
        self._prescriptions = deque(maxlen=MAX_PRESCRIPTIONS_CACHE)
        self._current_tick = 0
        if clear_old_logs:
            self._clear_old_logs(output_dir)
        
        print(f"File event logging prepared. Output directory: {output_dir}")
        if project_path:
            self._load_initial_profiles(
                project_path,
                patient_profiles_path=patient_profiles_path,
                doctor_profiles_path=doctor_profiles_path,
            )
        
        return output_dir
    
    def _clear_old_logs(self, output_dir: str):
        """清除旧的日志文件。"""
        log_files = [
            "agents.jsonl",
            "messages.jsonl",
            "patient_status.jsonl",
            "examinations.jsonl",
            "prescriptions.jsonl",
            "all_events.jsonl",
        ]
        
        cleared_count = 0
        for filename in log_files:
            filepath = os.path.join(output_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                cleared_count += 1
        for filepath in Path(output_dir).glob("events_tick_*.log"):
            filepath.unlink()
            cleared_count += 1
        tick_events_dir = Path(output_dir) / TICK_EVENTS_SUBDIR
        if tick_events_dir.exists():
            for filepath in tick_events_dir.glob("events_tick_*.log"):
                filepath.unlink()
                cleared_count += 1
        
        if cleared_count > 0:
            print(f"Cleared {cleared_count} old log files from {output_dir}")
    
    def _load_initial_profiles(
        self,
        project_path: str,
        patient_profiles_path: Optional[str] = None,
        doctor_profiles_path: Optional[str] = None,
    ):
        """加载初始 agent profiles 并写入 agents.jsonl。"""
        try:
            from pathlib import Path

            data_dir = Path(project_path) / "data"
            doctor_profiles_file = Path(doctor_profiles_path) if doctor_profiles_path else data_dir / "doctors" / "profiles.jsonl"
            if doctor_profiles_file.exists():
                with open(doctor_profiles_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            profile = json.loads(line)
                            agent_id = profile.get("id", "")
                            if agent_id:
                                self._agents[agent_id] = {
                                    "id": agent_id,
                                    "tick": 0,
                                    "template": "DoctorAgent",
                                    **profile
                                }
                print(f"Loaded {len([a for a in self._agents if 'Doctor' in a])} doctor profiles")
            else:
                print(f"Doctor profiles file not found: {doctor_profiles_file}")
            patient_profiles_file = Path(patient_profiles_path) if patient_profiles_path else data_dir / "patients" / "profiles.jsonl"
            if patient_profiles_file.exists():
                with open(patient_profiles_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            profile = json.loads(line)
                            agent_id = profile.get("id", "")
                            if agent_id:
                                self._agents[agent_id] = {
                                    "id": agent_id,
                                    "tick": 0,
                                    "template": "PatientAgent",
                                    **profile
                                }
                print(f"Loaded {len([a for a in self._agents if 'Patient' in a])} patient profiles")
            else:
                print(f"Patient profiles file not found: {patient_profiles_file}")
            if self._agents and self.output_dir:
                agents_file = os.path.join(self.output_dir, "agents.jsonl")
                with open(agents_file, "w", encoding="utf-8") as f:
                    for agent in self._agents.values():
                        f.write(json.dumps(agent, ensure_ascii=False) + "\n")
                print(f"Wrote {len(self._agents)} agents to agents.jsonl")
                
        except Exception as e:
            print(f"Error loading initial profiles: {e}")

    async def log_event(self, event_data: Dict[str, Any]):
        """
        异步地将事件写入日志文件，同时更新内存缓存。
        """
        async with self.lock:
            try:
                if self.output_dir is None:
                    self.output_dir = os.environ.get('MAS_EVENT_LOG_DIR')
                    if not self.output_dir:
                        return

                tick = event_data.get('tick', 0)
                self._current_tick = max(self._current_tick, tick)
                
                event_name = event_data.get('name', '')
                payload = event_data.get('payload', {})
                tick_events_dir = os.path.join(self.output_dir, TICK_EVENTS_SUBDIR)
                os.makedirs(tick_events_dir, exist_ok=True)
                log_file_path = os.path.join(tick_events_dir, f"events_tick_{tick}.log")
                log_line = json.dumps(event_data, ensure_ascii=False) + "\n"
                async with aiofiles.open(log_file_path, "a", encoding="utf-8") as f:
                    await f.write(log_line)
                all_events_path = os.path.join(self.output_dir, "all_events.jsonl")
                async with aiofiles.open(all_events_path, "a", encoding="utf-8") as f:
                    await f.write(log_line)
                await self._categorize_event(event_name, payload, tick, event_data)

            except Exception as e:
                print(f"Error writing to log file in process {os.getpid()}: {e}")

    async def _categorize_event(self, event_name: str, payload: Dict[str, Any], tick: int, full_event: Dict[str, Any]):
        """根据事件类型分类存储到不同文件和内存缓存。"""
        try:
            if event_name == "SEND_MESSAGE":
                metadata = payload.get("metadata") or {}
                patient_id = metadata.get("patient_id")
                msg = {
                    "tick": tick,
                    "sender": payload.get("agent_id", ""),
                    "receiver": payload.get("target", ""),
                    "content": payload.get("content_preview", ""),
                    "full_content": payload.get("content", payload.get("content_preview", "")),
                    "message_type": payload.get("message_type"),
                    "metadata": metadata,
                    "timestamp": full_event.get("timestamp", ""),
                }
                if patient_id:
                    msg["patient_id"] = patient_id
                self._messages.append(msg)
                await self._append_to_file("messages.jsonl", msg)

            elif event_name in ["PATIENT_MOVE", "PATIENT_REGISTER"]:
                patient_id = payload.get("agent_id", "")
                status = {
                    "patient_id": patient_id,
                    "tick": tick,
                    "event": event_name,
                    "location": payload.get("location", payload.get("target_location", "")),
                    "phase": payload.get("phase", ""),
                    "status": payload.get("status", ""),
                    "details": payload,
                    "timestamp": full_event.get("timestamp", ""),
                }
                self._patient_status[patient_id] = status
                await self._append_to_file("patient_status.jsonl", status)

            elif event_name in ["SCHEDULE_EXAMINATION", "DO_EXAMINATION"]:
                exam = {
                    "tick": tick,
                    "event": event_name,
                    "patient_id": payload.get("patient_id", payload.get("agent_id", "")),
                    "doctor_id": payload.get("doctor_id", ""),
                    "examination_type": payload.get("examination_type", payload.get("examination_name", "")),
                    "status": payload.get("status", ""),
                    "result": payload.get("result", ""),
                    "details": payload,
                    "timestamp": full_event.get("timestamp", ""),
                }
                self._examinations.append(exam)
                await self._append_to_file("examinations.jsonl", exam)

            elif event_name in ["PRESCRIBE_TREATMENT", "RECEIVE_TREATMENT"]:
                prescription = {
                    "tick": tick,
                    "event": event_name,
                    "patient_id": payload.get("patient_id", payload.get("agent_id", "")),
                    "doctor_id": payload.get("doctor_id", ""),
                    "treatment": payload.get("treatment", payload.get("treatment_plan", "")),
                    "status": payload.get("status", ""),
                    "details": payload,
                    "timestamp": full_event.get("timestamp", ""),
                }
                self._prescriptions.append(prescription)
                await self._append_to_file("prescriptions.jsonl", prescription)

        except Exception as e:
            print(f"Error categorizing event {event_name}: {e}")

    async def _append_to_file(self, filename: str, data: Dict[str, Any]):
        """追加数据到指定文件。"""
        if not self.output_dir:
            return
        filepath = os.path.join(self.output_dir, filename)
        line = json.dumps(data, ensure_ascii=False) + "\n"
        async with aiofiles.open(filepath, "a", encoding="utf-8") as f:
            await f.write(line)
    
    def get_agents(self) -> Dict[str, Dict[str, Any]]:
        """获取所有 agent profile。"""
        return self._agents.copy()
    
    def get_doctors(self) -> List[Dict[str, Any]]:
        """获取所有医生。"""
        return [a for a in self._agents.values() if "Doctor" in a.get("template", "") or a.get("id", "").startswith("Doctor_")]
    
    def get_patients(self) -> List[Dict[str, Any]]:
        """获取所有患者。"""
        return [a for a in self._agents.values() if "Patient" in a.get("template", "") or a.get("id", "").startswith("Patient_")]
    
    def get_messages(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取对话消息（内存中的最近消息）。"""
        if agent_id:
            return [m for m in self._messages if m.get("sender") == agent_id or m.get("receiver") == agent_id]
        return list(self._messages)
    
    def get_patient_status(self, patient_id: Optional[str] = None) -> Dict[str, Any]:
        """获取患者状态。"""
        if patient_id:
            return self._patient_status.get(patient_id, {})
        return self._patient_status.copy()
    
    def get_examinations(self, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取检查记录（内存中的最近记录）。"""
        if patient_id:
            return [e for e in self._examinations if e.get("patient_id") == patient_id]
        return list(self._examinations)
    
    def get_prescriptions(self, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取处方记录（内存中的最近记录）。"""
        if patient_id:
            return [p for p in self._prescriptions if p.get("patient_id") == patient_id]
        return list(self._prescriptions)
    
    def get_current_tick(self) -> int:
        """获取当前 tick。"""
        return self._current_tick

    def stop_logging(self):
        """停止日志记录。"""
        print(f"Stopping file event logging in process {os.getpid()}.")
        self.output_dir = None

class EventLogReader:
    """从日志文件读取历史事件数据。"""
    
    def __init__(self, log_dir: str):
        self.log_dir = Path(log_dir)
    
    def read_jsonl(self, filename: str) -> List[Dict[str, Any]]:
        """读取 JSONL 文件。"""
        filepath = self.log_dir / filename
        if not filepath.exists():
            return []
        
        result = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return result
    
    def get_agents(self) -> List[Dict[str, Any]]:
        """获取所有 agent。"""
        return self.read_jsonl("agents.jsonl")
    
    def get_doctors(self) -> List[Dict[str, Any]]:
        """获取所有医生。"""
        agents = self.get_agents()
        return [a for a in agents if "Doctor" in a.get("template", "") or a.get("id", "").startswith("Doctor_")]
    
    def get_patients(self) -> List[Dict[str, Any]]:
        """获取所有患者。"""
        agents = self.get_agents()
        return [a for a in agents if "Patient" in a.get("template", "") or a.get("id", "").startswith("Patient_")]
    
    def get_messages(self) -> List[Dict[str, Any]]:
        """获取所有消息。"""
        return self.read_jsonl("messages.jsonl")
    
    def get_patient_status(self) -> List[Dict[str, Any]]:
        """获取患者状态历史。"""
        return self.read_jsonl("patient_status.jsonl")
    
    def get_examinations(self) -> List[Dict[str, Any]]:
        """获取检查记录。"""
        return self.read_jsonl("examinations.jsonl")
    
    def get_prescriptions(self) -> List[Dict[str, Any]]:
        """获取处方记录。"""
        return self.read_jsonl("prescriptions.jsonl")
    
    def get_all_events(self) -> List[Dict[str, Any]]:
        """获取所有事件。"""
        return self.read_jsonl("all_events.jsonl")
    
    def get_events_by_tick(self, tick: int) -> List[Dict[str, Any]]:
        """获取指定 tick 的事件。"""
        events = self.read_jsonl(f"{TICK_EVENTS_SUBDIR}/events_tick_{tick}.log")
        if events:
            return events
        return self.read_jsonl(f"events_tick_{tick}.log")
file_event_logger = FileEventLogger()
