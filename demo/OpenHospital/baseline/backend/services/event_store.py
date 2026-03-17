"""
Event Store Service - In-memory storage for simulation events.

This service stores events received via WebSocket and provides
query APIs for the frontend. When the simulation is not running,
it can read from log files instead.

Memory Optimization:
- Hot data: Recent events and active patient data kept in memory
- Cold data: Older events read from disk on demand
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import deque
from itertools import islice


class EventStore:
    """
    内存事件存储，用于缓存实时事件数据。

    数据来源:
    1. 实时模式: 通过 WebSocket 接收的事件
    2. 历史模式: 从日志文件读取

    内存优化策略:
    - 热数据: 最近 N 个 tick 的事件和活跃患者数据保留在内存
    - 冷数据: 旧数据从磁盘按需读取
    """
    MAX_EVENTS_IN_MEMORY = 5000            
    MAX_MESSAGES_IN_MEMORY = 2000            
    MAX_EXAMINATIONS_IN_MEMORY = 1000              
    MAX_PRESCRIPTIONS_IN_MEMORY = 1000              
    ACTIVE_PATIENT_WINDOW_TICKS = 50                   
    MAX_DISK_PATIENT_CACHE = 1000               
    TICK_EVENTS_SUBDIR = "tick_events"

    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}                       
        self._messages: deque = deque(maxlen=self.MAX_MESSAGES_IN_MEMORY)               
        self._patient_status: Dict[str, Dict[str, Any]] = {}                               
        self._examinations: deque = deque(maxlen=self.MAX_EXAMINATIONS_IN_MEMORY)               
        self._prescriptions: deque = deque(maxlen=self.MAX_PRESCRIPTIONS_IN_MEMORY)               
        self._all_events: deque = deque(maxlen=self.MAX_EVENTS_IN_MEMORY)               
        self._current_tick: int = 0
        self._is_simulation_running: bool = False
        self._log_dir: Optional[str] = None
        self._data_loaded: bool = False
        self._resume_mode: bool = False             
        self._local_write_enabled: bool = False                           
        self._available_tick_files: List[int] = []
        self._loaded_tick_files: set = set()                
        self._messages_by_patient: Dict[str, List[Dict[str, Any]]] = {}
        self._prescriptions_by_patient: Dict[str, List[Dict[str, Any]]] = {}
        self._examinations_by_patient: Dict[str, List[Dict[str, Any]]] = {}
        self._active_patient_ids: set = set()
        self._last_patient_activity_tick: Dict[str, int] = {}
        self._disk_patient_summary_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._disk_messages_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._disk_examinations_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._disk_prescriptions_cache: Dict[str, List[Dict[str, Any]]] = {}

        self._disk_examinations_index: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._disk_prescriptions_index: Optional[Dict[str, List[Dict[str, Any]]]] = None

        self._tick_examinations_index: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._tick_prescriptions_index: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def _set_patient_disk_cache(self, cache: Dict[str, List[Dict[str, Any]]], patient_id: str, records: List[Dict[str, Any]]) -> None:
        """Set per-patient disk cache with bounded size."""
        cache[patient_id] = records
        while len(cache) > self.MAX_DISK_PATIENT_CACHE:
            oldest_patient_id = next(iter(cache))
            cache.pop(oldest_patient_id, None)

    def _iter_tick_event_files(self) -> List[Path]:
        """Return all tick event files, preferring nested tick_events directory."""
        if not self._log_dir:
            return []

        log_path = Path(self._log_dir)
        nested_dir = log_path / self.TICK_EVENTS_SUBDIR
        nested_files = list(nested_dir.glob("events_tick_*.log")) if nested_dir.exists() else []

        if nested_files:
            return sorted(nested_files, key=lambda x: int(x.stem.split("_")[-1]))
        flat_files = list(log_path.glob("events_tick_*.log"))
        return sorted(flat_files, key=lambda x: int(x.stem.split("_")[-1]))

    def _resolve_tick_file(self, tick: int) -> Path:
        """Resolve tick file path, preferring nested tick_events directory."""
        if not self._log_dir:
            return Path(f"events_tick_{tick}.log")

        log_path = Path(self._log_dir)
        nested_file = log_path / self.TICK_EVENTS_SUBDIR / f"events_tick_{tick}.log"
        if nested_file.exists():
            return nested_file

        flat_file = log_path / f"events_tick_{tick}.log"
        if flat_file.exists():
            return flat_file
        return nested_file

    @staticmethod
    def _is_patient_id(agent_id: str) -> bool:
        """判断是否为患者 ID（兼容多种命名格式）。"""
        if not agent_id:
            return False
        return agent_id.startswith("Patient_") or agent_id.startswith("Patient-")

    @staticmethod
    def _is_doctor_id(agent_id: str) -> bool:
        """判断是否为医生 ID（兼容多种命名格式）。"""
        if not agent_id:
            return False
        return agent_id.startswith("Doctor_") or agent_id.startswith("Doctor-")

    @staticmethod
    def _normalize_examination_status(raw_status: Any, event_name: str, completed_tick: Optional[int] = None) -> str:
        """将检查状态标准化为 pending/completed。"""
        status = str(raw_status or "").strip().lower()

        if status in {"pending", "completed"}:
            return status

        if status == "success":
            if event_name == "DO_EXAMINATION" or completed_tick:
                return "completed"
            return "pending"

        if event_name == "SCHEDULE_EXAMINATION":
            return "pending"
        if event_name == "DO_EXAMINATION":
            return "completed"

        if completed_tick:
            return "completed"
        return status or "pending"

    @staticmethod
    def _normalize_prescription_status(raw_status: Any, event_name: str, completed_tick: Optional[int] = None) -> str:
        """将处方状态标准化为 pending/completed。"""
        status = str(raw_status or "").strip().lower()

        if status in {"pending", "completed"}:
            return status

        if status == "success":
            if event_name == "RECEIVE_TREATMENT" or completed_tick:
                return "completed"
            return "pending"

        if event_name == "PRESCRIBE_TREATMENT":
            return "pending"
        if event_name == "RECEIVE_TREATMENT":
            return "completed"

        if completed_tick:
            return "completed"
        return status or "pending"

    def set_log_dir(self, log_dir: str, resume_mode: bool = False, enable_local_write: bool = False):
        """设置日志目录，用于读取历史数据。

        Args:
            log_dir: 日志目录路径
            resume_mode: 是否为断点重续模式，如果是则加载历史数据
            enable_local_write: 是否启用本地 JSONL 写入（远程部署时后端自己持久化事件）
        """
        if not log_dir or not os.path.isdir(log_dir):
            print(f"[EventStore] Invalid log directory: {log_dir}")
            return
        self._log_dir = log_dir
        self._resume_mode = resume_mode
        self._local_write_enabled = enable_local_write
        self._data_loaded = False
        self._disk_patient_summary_cache = None
        self._disk_messages_cache = {}
        self._disk_examinations_cache = {}
        self._disk_prescriptions_cache = {}
        self._disk_examinations_index = None
        self._disk_prescriptions_index = None
        self._tick_examinations_index = None
        self._tick_prescriptions_index = None
        self._available_tick_files = []
        self._loaded_tick_files = set()

        if enable_local_write:
            print(f"[EventStore] Local JSONL write enabled at: {log_dir}")
        if resume_mode:
            print(f"[EventStore] Resume mode detected, loading historical data...")
            self._load_all_data()
        else:
            self._load_initial_agents()

    def set_simulation_running(self, running: bool):
        """设置模拟运行状态。"""
        self._is_simulation_running = running
        if running:
            if not self._resume_mode:
                self.clear()
            else:
                print(f"[EventStore] Resume mode: keeping existing data, current_tick={self._current_tick}")
        else:
            self._disk_patient_summary_cache = None
            self._disk_messages_cache = {}
            self._disk_examinations_cache = {}
            self._disk_prescriptions_cache = {}
            self._disk_examinations_index = None
            self._disk_prescriptions_index = None
            self._tick_examinations_index = None
            self._tick_prescriptions_index = None

    def clear(self):
        """清空所有缓存数据。"""
        self._agents = {}
        self._messages = deque(maxlen=self.MAX_MESSAGES_IN_MEMORY)
        self._patient_status = {}
        self._examinations = deque(maxlen=self.MAX_EXAMINATIONS_IN_MEMORY)
        self._prescriptions = deque(maxlen=self.MAX_PRESCRIPTIONS_IN_MEMORY)
        self._all_events = deque(maxlen=self.MAX_EVENTS_IN_MEMORY)
        self._current_tick = 0
        self._data_loaded = False
        self._messages_by_patient = {}
        self._prescriptions_by_patient = {}
        self._examinations_by_patient = {}
        self._active_patient_ids = set()
        self._last_patient_activity_tick = {}
        self._disk_patient_summary_cache = None
        self._disk_messages_cache = {}
        self._disk_examinations_cache = {}
        self._disk_prescriptions_cache = {}
        self._disk_examinations_index = None
        self._disk_prescriptions_index = None
        self._tick_examinations_index = None
        self._tick_prescriptions_index = None
        self._available_tick_files = []
        self._loaded_tick_files = set()

    def _load_all_data(self):
        """加载所有历史数据。"""
        if self._data_loaded or not self._log_dir:
            return

        self._disk_patient_summary_cache = None
        self._disk_messages_cache = {}
        self._disk_examinations_cache = {}
        self._disk_prescriptions_cache = {}
        self._disk_examinations_index = None
        self._disk_prescriptions_index = None
        self._tick_examinations_index = None
        self._tick_prescriptions_index = None
        self._available_tick_files = []
        self._loaded_tick_files = set()

        print(f"[EventStore] Loading data from {self._log_dir}")
        self._load_initial_agents()
        self._load_messages()
        self._load_patient_status()
        self._scan_available_tick_files()

        self._data_loaded = True

        print(f"[EventStore] Data loaded: {len(self._agents)} agents, {len(self._messages)} messages")

    def _load_messages(self):
        """从 messages.jsonl 加载消息。"""
        messages = self._read_from_log("messages.jsonl")
        for msg in messages:
            self._messages.append(msg)
            tick = msg.get("tick", 0)
            self._current_tick = max(self._current_tick, tick)
            sender = msg.get("sender", "")
            receiver = msg.get("receiver", "")
            for agent_id in [sender, receiver]:
                if self._is_patient_id(agent_id):
                    if agent_id not in self._messages_by_patient:
                        self._messages_by_patient[agent_id] = []
                    self._messages_by_patient[agent_id].append(msg)

        if messages:
            print(f"[EventStore] Loaded {len(messages)} messages from messages.jsonl")

    def _load_patient_status(self):
        """从 patient_status.jsonl 加载患者状态。"""
        statuses = self._read_from_log("patient_status.jsonl")
        for status in statuses:
            patient_id = status.get("patient_id", "")
            if patient_id:
                existing = self._patient_status.get(patient_id, {})
                if not status.get("department"):
                    status_details = status.get("details", {}) if isinstance(status.get("details"), dict) else {}
                    existing_details = existing.get("details", {}) if isinstance(existing.get("details"), dict) else {}
                    status["department"] = (
                        status_details.get("department")
                        or existing.get("department")
                        or existing_details.get("department")
                        or ""
                    )
                if status.get("tick", 0) >= existing.get("tick", 0):
                    self._patient_status[patient_id] = status

        if statuses:
            print(f"[EventStore] Loaded status for {len(self._patient_status)} patients from patient_status.jsonl")

    def _scan_available_tick_files(self):
        """扫描可用的 tick 文件，只记录文件名不读取内容。"""
        if not self._log_dir:
            return

        event_files = self._iter_tick_event_files()

        self._available_tick_files = []
        for event_file in event_files:
            try:
                tick_num = int(event_file.stem.split("_")[-1])
                self._available_tick_files.append(tick_num)
            except (ValueError, IndexError):
                continue

        if self._available_tick_files:
            print(f"[EventStore] Found {len(self._available_tick_files)} tick files (ticks {min(self._available_tick_files)}-{max(self._available_tick_files)})")

    def _load_all_events(self):
        """从所有 events_tick_*.log 文件加载事件（保留用于兼容，但不再在启动时调用）。"""
        if not self._log_dir:
            return

        event_files = self._iter_tick_event_files()

        total_events = 0
        for event_file in event_files:
            try:
                with open(event_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                event = json.loads(line)
                                self._process_event_for_loading(event)
                                total_events += 1
                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                print(f"[EventStore] Error reading {event_file}: {e}")

        if total_events > 0:
            print(f"[EventStore] Loaded {total_events} events from {len(event_files)} log files")

    def _load_tick_file(self, tick: int) -> List[Dict[str, Any]]:
        """加载单个 tick 文件的事件。"""
        if not self._log_dir:
            return []

        if tick in self._loaded_tick_files:
            return []           

        tick_file = self._resolve_tick_file(tick)
        if not tick_file.exists():
            return []

        events = []
        try:
            with open(tick_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                            events.append(event)
                        except json.JSONDecodeError:
                            pass
            self._loaded_tick_files.add(tick)
        except Exception as e:
            print(f"[EventStore] Error reading tick file {tick_file}: {e}")

        return events

    def _load_all_tick_events_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """加载所有 tick 文件中与特定患者相关的事件。"""
        if not self._available_tick_files:
            return []

        patient_events = []
        for tick in self._available_tick_files:
            events = self._load_tick_file(tick)
            for event in events:
                payload = event.get("payload", {})
                event_patient_id = payload.get("patient_id", payload.get("agent_id", ""))
                if event_patient_id == patient_id:
                    patient_events.append(event)

        return patient_events

    def _build_patient_index_from_jsonl(self, filename: str) -> Dict[str, List[Dict[str, Any]]]:
        """从 JSONL 文件构建 patient_id -> records 索引（单次扫描）。"""
        if not self._log_dir:
            return {}

        filepath = Path(self._log_dir) / filename
        if not filepath.exists():
            return {}

        index: Dict[str, List[Dict[str, Any]]] = {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    patient_id = record.get("patient_id", "")
                    if not patient_id:
                        continue

                    if patient_id not in index:
                        index[patient_id] = []
                    index[patient_id].append(record)
        except Exception as e:
            print(f"[EventStore] Error building patient index from {filename}: {e}")

        return index

    def _build_patient_indexes_from_tick_logs(self) -> tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        """从 tick 日志一次性构建 examinations/prescriptions 的患者索引。"""
        examinations_index: Dict[str, List[Dict[str, Any]]] = {}
        prescriptions_index: Dict[str, List[Dict[str, Any]]] = {}

        if not self._log_dir or not self._available_tick_files:
            return examinations_index, prescriptions_index

        for tick in self._available_tick_files:
            tick_file = self._resolve_tick_file(tick)
            if not tick_file.exists():
                continue

            try:
                with open(tick_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue

                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        event_name = event.get("name", "")
                        if event_name not in {
                            "SCHEDULE_EXAMINATION",
                            "DO_EXAMINATION",
                            "PRESCRIBE_TREATMENT",
                            "RECEIVE_TREATMENT",
                        }:
                            continue

                        payload = event.get("payload", {})
                        patient_id = payload.get("patient_id", payload.get("agent_id", ""))
                        if not patient_id:
                            continue

                        event_tick = event.get("tick", 0)
                        timestamp = event.get("timestamp", "")

                        if event_name in {"SCHEDULE_EXAMINATION", "DO_EXAMINATION"}:
                            items = payload.get("items", [])
                            if not items and "examination_type" in payload:
                                items = [payload["examination_type"]]
                            elif not items and "examination_name" in payload:
                                items = [payload["examination_name"]]

                            exam = {
                                "tick": event_tick,
                                "event": event_name,
                                "patient_id": patient_id,
                                "doctor_id": payload.get("doctor_id", ""),
                                "examination_type": ", ".join(items) if isinstance(items, list) else str(items),
                                "items": items,
                                "status": payload.get("status", ""),
                                "result": payload.get("result", ""),
                                "results": payload.get("results"),
                                "details": payload,
                                "timestamp": timestamp,
                            }
                            if patient_id not in examinations_index:
                                examinations_index[patient_id] = []
                            examinations_index[patient_id].append(exam)

                        if event_name in {"PRESCRIBE_TREATMENT", "RECEIVE_TREATMENT"}:
                            prescription = {
                                "tick": event_tick,
                                "event": event_name,
                                "patient_id": patient_id,
                                "doctor_id": payload.get("doctor_id", ""),
                                "treatment": payload.get("treatment", payload.get("treatment_plan", "")),
                                "diagnosis": payload.get("diagnosis", ""),
                                "status": payload.get("status", ""),
                                "details": payload,
                                "timestamp": timestamp,
                            }
                            if patient_id not in prescriptions_index:
                                prescriptions_index[patient_id] = []
                            prescriptions_index[patient_id].append(prescription)
            except Exception as e:
                print(f"[EventStore] Error reading tick file {tick_file}: {e}")

        return examinations_index, prescriptions_index

    def _ensure_tick_patient_indexes(self) -> None:
        """确保 tick 日志的患者索引已构建。"""
        if self._tick_examinations_index is not None and self._tick_prescriptions_index is not None:
            return

        examinations_index, prescriptions_index = self._build_patient_indexes_from_tick_logs()
        self._tick_examinations_index = examinations_index
        self._tick_prescriptions_index = prescriptions_index

    def _ensure_disk_examinations_index(self) -> None:
        """确保 examinations 的 patient 索引已构建。"""
        if self._disk_examinations_index is not None:
            return

        self._disk_examinations_index = self._build_patient_index_from_jsonl("examinations.jsonl")
        if self._disk_examinations_index:
            return

        self._ensure_tick_patient_indexes()
        self._disk_examinations_index = dict(self._tick_examinations_index or {})

    def _ensure_disk_prescriptions_index(self) -> None:
        """确保 prescriptions 的 patient 索引已构建。"""
        if self._disk_prescriptions_index is not None:
            return

        self._disk_prescriptions_index = self._build_patient_index_from_jsonl("prescriptions.jsonl")
        if self._disk_prescriptions_index:
            return

        self._ensure_tick_patient_indexes()
        self._disk_prescriptions_index = dict(self._tick_prescriptions_index or {})

    def _process_event_for_loading(self, event: Dict[str, Any]):
        """处理加载的事件，提取检查、处方、反思等数据。"""
        self._all_events.append(event)

        event_name = event.get("name", "")
        payload = event.get("payload", {})
        tick = event.get("tick", 0)
        timestamp = event.get("timestamp", "")

        self._current_tick = max(self._current_tick, tick)

        if event_name in ["SCHEDULE_EXAMINATION", "DO_EXAMINATION"]:
            self._process_examination(event_name, payload, tick, timestamp)
        elif event_name in ["PRESCRIBE_TREATMENT", "RECEIVE_TREATMENT"]:
            self._process_prescription(event_name, payload, tick, timestamp)

    def process_event(self, event: Dict[str, Any]):
        """
        处理接收到的实时事件，更新内存存储。

        Args:
            event: 事件数据，包含 category, name, payload, tick, timestamp
        """
        event_name = event.get("name", "")
        payload = event.get("payload", {})
        tick = event.get("tick", 0)
        recent_events = list(islice(reversed(self._all_events), 100))
        if any(e.get("tick") == tick and e.get("name") == event_name and e.get("payload") == payload for e in recent_events):
            return

        self._all_events.append(event)

        self._current_tick = max(self._current_tick, tick)
        if self._local_write_enabled:
            self._write_event_to_disk(event)

        timestamp = event.get("timestamp", "")

        if event_name == "SEND_MESSAGE":
            self._process_message(payload, tick, timestamp)
        elif event_name in ["PATIENT_MOVE", "PATIENT_REGISTER", "IDLE"]:
            self._process_patient_status(event_name, payload, tick, timestamp)
        elif event_name in ["SCHEDULE_EXAMINATION", "DO_EXAMINATION"]:
            self._process_examination(event_name, payload, tick, timestamp)
        elif event_name in ["PRESCRIBE_TREATMENT", "RECEIVE_TREATMENT"]:
            self._process_prescription(event_name, payload, tick, timestamp)

    def _update_patient_activity(self, patient_id: str, tick: int):
        """更新患者活跃状态。"""
        if self._is_patient_id(patient_id):
            self._last_patient_activity_tick[patient_id] = tick
            self._active_patient_ids.add(patient_id)

    def _cleanup_inactive_patients(self):
        """清理非活跃患者的数据索引（保留患者状态）。"""
        if not self._is_simulation_running:
            return

        inactive_threshold = self._current_tick - self.ACTIVE_PATIENT_WINDOW_TICKS
        inactive_patients = [
            pid for pid, last_tick in self._last_patient_activity_tick.items()
            if last_tick < inactive_threshold
        ]

        for patient_id in inactive_patients:
            self._active_patient_ids.discard(patient_id)
            if patient_id in self._messages_by_patient:
                del self._messages_by_patient[patient_id]
            if patient_id in self._examinations_by_patient:
                del self._examinations_by_patient[patient_id]
            if patient_id in self._prescriptions_by_patient:
                del self._prescriptions_by_patient[patient_id]

        if inactive_patients:
            self._disk_patient_summary_cache = None
            for patient_id in inactive_patients:
                self._disk_messages_cache.pop(patient_id, None)
                self._disk_examinations_cache.pop(patient_id, None)
                self._disk_prescriptions_cache.pop(patient_id, None)

    def _process_message(self, payload: Dict[str, Any], tick: int, timestamp: str):
        """处理消息事件。"""
        metadata = payload.get("metadata") or {}
        patient_id = metadata.get("patient_id")
        message_type = payload.get("message_type")
        sender = payload.get("agent_id", "")
        receiver = payload.get("target", "")
        if not message_type:
            if self._is_doctor_id(sender) and self._is_patient_id(receiver):
                message_type = "doctor_to_patient"
            elif self._is_patient_id(sender) and self._is_doctor_id(receiver):
                message_type = "patient_to_doctor"
            else:
                message_type = "agent_to_agent"

        msg = {
            "tick": tick,
            "sender": sender,
            "receiver": receiver,
            "content": payload.get("content_preview", ""),
            "full_content": payload.get("content", payload.get("content_preview", "")),
            "status": payload.get("status", "success"),
            "message_type": message_type,
            "metadata": metadata,
            "timestamp": timestamp,
        }
        if patient_id:
            msg["patient_id"] = patient_id
        for agent_id in [sender, receiver]:
            self._update_patient_activity(agent_id, tick)
        content_key = msg["full_content"][:100] if msg["full_content"] else msg["content"][:100]
        is_duplicate = any(
            m.get("tick") == tick
            and m.get("sender") == msg["sender"]
            and m.get("receiver") == msg["receiver"]
            and (m.get("full_content", "")[:100] == content_key or m.get("content", "")[:100] == content_key)
            for m in self._messages
        )

        if not is_duplicate:
            self._messages.append(msg)
            for agent_id in [msg["sender"], msg["receiver"]]:
                if self._is_patient_id(agent_id):
                    if agent_id not in self._messages_by_patient:
                        self._messages_by_patient[agent_id] = []
                    self._messages_by_patient[agent_id].append(msg)
        if tick % 100 == 0:
            self._cleanup_inactive_patients()

    def _process_patient_status(self, event_name: str, payload: Dict[str, Any], tick: int, timestamp: str):
        """处理患者状态事件。"""
        patient_id = payload.get("agent_id", "")
        if not patient_id:
            return
        self._update_patient_activity(patient_id, tick)

        existing = self._patient_status.get(patient_id, {})
        existing_details = existing.get("details", {}) if isinstance(existing.get("details"), dict) else {}
        department = payload.get("department") or existing.get("department") or existing_details.get("department", "")

        status = {
            "patient_id": patient_id,
            "tick": tick,
            "event": event_name,
            "location": payload.get("location", payload.get("target_location", "")),
            "phase": payload.get("phase", ""),
            "status": payload.get("status", ""),
            "assigned_doctor": payload.get("assigned_doctor", payload.get("target", "")),
            "department": department,
            "details": payload,
            "timestamp": timestamp,
        }
        self._patient_status[patient_id] = status

    def _process_examination(self, event_name: str, payload: Dict[str, Any], tick: int, timestamp: str):
        """处理检查事件。"""
        items = payload.get("items", [])
        if not items and "examination_type" in payload:
            items = [payload["examination_type"]]
        elif not items and "examination_name" in payload:
            items = [payload["examination_name"]]
        if not items:
            items = ["Medical Examination"]

        patient_id = payload.get("patient_id", payload.get("agent_id", ""))
        self._update_patient_activity(patient_id, tick)
        exam = {
            "id": payload.get("record_id", f"exam_{tick}_{len(self._examinations)}"),
            "tick": tick,
            "event": event_name,
            "patient_id": patient_id,
            "doctor_id": payload.get("doctor_id", payload.get("agent_id", "") if event_name == "SCHEDULE_EXAMINATION" else ""),
            "examination_type": ", ".join(items) if isinstance(items, list) else str(items),
            "items": items,
            "status": self._normalize_examination_status(
                payload.get("status", "pending" if event_name == "SCHEDULE_EXAMINATION" else "completed"),
                event_name,
            ),
            "result": payload.get("result"),
            "results": payload.get("results"),
            "reason": payload.get("reason", ""),
            "details": payload,
            "timestamp": timestamp,
        }

        if patient_id:
            self._disk_patient_summary_cache = None
            self._disk_examinations_cache.pop(patient_id, None)
            if self._disk_examinations_index is not None:
                if patient_id not in self._disk_examinations_index:
                    self._disk_examinations_index[patient_id] = []
                self._disk_examinations_index[patient_id].append(exam)
        if event_name == "DO_EXAMINATION":
            for i in range(len(self._examinations) - 1, -1, -1):
                prev = self._examinations[i]
                if prev["patient_id"] == patient_id and prev["status"] == "pending":
                    prev["status"] = "completed"
                    prev["completed_tick"] = tick
                    if exam.get("results") is not None:
                        prev["results"] = exam.get("results")
                    elif exam.get("result") not in (None, ""):
                        prev["result"] = exam.get("result")

                    if exam.get("items") and not prev.get("items"):
                        prev["items"] = exam.get("items")

                    if exam.get("doctor_id") and not prev.get("doctor_id"):
                        prev["doctor_id"] = exam.get("doctor_id")

                    prev["status"] = self._normalize_examination_status(
                        prev.get("status"),
                        prev.get("event", ""),
                        prev.get("completed_tick"),
                    )
                    return

        self._examinations.append(exam)
        if patient_id:
            if patient_id not in self._examinations_by_patient:
                self._examinations_by_patient[patient_id] = []
            self._examinations_by_patient[patient_id].append(exam)

    def _process_prescription(self, event_name: str, payload: Dict[str, Any], tick: int, timestamp: str):
        """处理处方事件。"""
        diagnosis = payload.get("diagnosis", "")
        treatment_plan = payload.get("treatment_plan", payload.get("treatment", ""))
        patient_id = payload.get("patient_id", payload.get("agent_id", ""))
        self._update_patient_activity(patient_id, tick)

        prescription = {
            "id": payload.get("record_id", f"rx_{tick}_{len(self._prescriptions)}"),
            "tick": tick,
            "event": event_name,
            "patient_id": patient_id,
            "doctor_id": payload.get("doctor_id", payload.get("agent_id", "") if event_name == "PRESCRIBE_TREATMENT" else ""),
            "diagnosis": diagnosis,
            "treatment": treatment_plan,
            "status": self._normalize_prescription_status(
                payload.get("status", "pending" if event_name == "PRESCRIBE_TREATMENT" else "completed"),
                event_name,
            ),
            "details": payload,
            "timestamp": timestamp,
        }

        if patient_id:
            self._disk_patient_summary_cache = None
            self._disk_prescriptions_cache.pop(patient_id, None)
            if self._disk_prescriptions_index is not None:
                if patient_id not in self._disk_prescriptions_index:
                    self._disk_prescriptions_index[patient_id] = []
                self._disk_prescriptions_index[patient_id].append(prescription)
        if event_name == "RECEIVE_TREATMENT":
            record_id = payload.get("prescription_id") or payload.get("record_id")
            if record_id:
                for prev in self._prescriptions:
                    if prev["id"] == record_id:
                        prev["status"] = "completed"
                        prev["completed_tick"] = tick
                        prev["status"] = self._normalize_prescription_status(
                            prev.get("status"),
                            prev.get("event", ""),
                            prev.get("completed_tick"),
                        )
                        return
            for i in range(len(self._prescriptions) - 1, -1, -1):
                prev = self._prescriptions[i]
                if prev["patient_id"] == patient_id and prev["status"] == "pending":
                    prev["status"] = "completed"
                    prev["completed_tick"] = tick
                    prev["status"] = self._normalize_prescription_status(
                        prev.get("status"),
                        prev.get("event", ""),
                        prev.get("completed_tick"),
                    )
                    return

        self._prescriptions.append(prescription)
        if patient_id:
            if patient_id not in self._prescriptions_by_patient:
                self._prescriptions_by_patient[patient_id] = []
            self._prescriptions_by_patient[patient_id].append(prescription)

    def _ensure_data_loaded(self):
        """确保数据已加载（懒加载）。"""
        if self._data_loaded:
            return

        if self._log_dir and not os.path.isdir(self._log_dir):
            print(f"[EventStore] Log directory missing: {self._log_dir}")
            self._log_dir = None

        if not self._log_dir:
            env_log_dir = os.environ.get("MAS_EVENT_LOG_DIR")
            if env_log_dir and os.path.isdir(env_log_dir):
                self.set_log_dir(env_log_dir)
                return

            default_log_dir = Path(__file__).resolve().parents[2] / "decoupling_output"
            if default_log_dir.is_dir():
                self.set_log_dir(str(default_log_dir))
                return

        if self._log_dir:
            self._load_all_data()

    def get_doctors(self) -> List[Dict[str, Any]]:
        """获取所有医生。"""
        self._ensure_data_loaded()

        doctors = [
            a
            for a in self._agents.values()
            if "Doctor" in a.get("template", "") or self._is_doctor_id(a.get("id", ""))
        ]

        return doctors

    def get_patients(self) -> List[Dict[str, Any]]:
        """获取所有患者。"""
        self._ensure_data_loaded()

        patients = [
            a
            for a in self._agents.values()
            if "Patient" in a.get("template", "") or self._is_patient_id(a.get("id", ""))
        ]

        return patients

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取单个 agent。"""
        self._ensure_data_loaded()

        return self._agents.get(agent_id)

    def get_messages(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取消息。优先从内存获取，必要时从磁盘懒加载。"""
        self._ensure_data_loaded()

        if agent_id:
            if self._is_patient_id(agent_id) and agent_id in self._messages_by_patient:
                in_memory_messages = list(self._messages_by_patient[agent_id])
            else:
                in_memory_messages = [
                    m for m in self._messages
                    if m.get("sender") == agent_id or m.get("receiver") == agent_id
                ]

            if not self._log_dir:
                return in_memory_messages
            disk_messages = self._lazy_load_messages_for_agent(agent_id)
            if not disk_messages:
                return in_memory_messages

            return self._merge_unique_messages(disk_messages, in_memory_messages)

        return list(self._messages)

    @staticmethod
    def _message_dedup_key(msg: Dict[str, Any]) -> tuple:
        """生成消息去重键。"""
        content = msg.get("full_content")
        if not content:
            content = msg.get("content", "")
        content = str(content or "")

        return (
            msg.get("tick", 0),
            msg.get("sender", ""),
            msg.get("receiver", ""),
            content[:100],
            msg.get("timestamp", ""),
        )

    def _merge_unique_messages(self, *message_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并多组消息并去重，按时间正序返回。"""
        merged: List[Dict[str, Any]] = []
        seen = set()

        for message_list in message_lists:
            for msg in message_list:
                key = self._message_dedup_key(msg)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(msg)

        merged.sort(key=lambda m: (m.get("tick", 0), m.get("timestamp", "")))
        return merged

    def _lazy_load_messages_for_agent(self, agent_id: str) -> List[Dict[str, Any]]:
        """从磁盘懒加载特定 agent（医生/患者）的消息（带缓存）。"""
        cached = self._disk_messages_cache.get(agent_id)
        if cached is not None:
            return list(cached)

        if not self._log_dir:
            return []

        messages = []
        try:
            filepath = Path(self._log_dir) / "messages.jsonl"
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                msg = json.loads(line)
                                if msg.get("sender") == agent_id or msg.get("receiver") == agent_id:
                                    messages.append(msg)
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            print(f"[EventStore] Error lazy loading messages for agent {agent_id}: {e}")

        self._set_patient_disk_cache(self._disk_messages_cache, agent_id, messages)
        return list(messages)

    def _lazy_load_messages_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """从磁盘懒加载特定患者的消息。"""
        return self._lazy_load_messages_for_agent(patient_id)

    def _lazy_load_examinations_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """从磁盘懒加载特定患者的检查记录（优先从 tick 文件按需加载）。"""
        cached = self._disk_examinations_cache.get(patient_id)
        if cached is not None:
            return list(cached)

        if not self._log_dir:
            return []

        self._ensure_disk_examinations_index()
        examinations = list((self._disk_examinations_index or {}).get(patient_id, []))

        merged_by_id: Dict[str, Dict[str, Any]] = {}
        pending_without_id: List[Dict[str, Any]] = []
        completed_without_id: List[Dict[str, Any]] = []

        for exam in examinations:
            raw_id = exam.get("id") or exam.get("record_id") or exam.get("details", {}).get("record_id")
            exam_id = str(raw_id) if raw_id else ""
            event_name = exam.get("event", "")

            normalized_items = exam.get("items")
            if not normalized_items:
                details = exam.get("details", {}) if isinstance(exam.get("details"), dict) else {}
                normalized_items = details.get("items")
            if not normalized_items and exam.get("examination_type"):
                normalized_items = [exam.get("examination_type")]

            if exam_id.startswith("EXAM_"):
                existing = merged_by_id.get(exam_id)
                if not existing:
                    merged_by_id[exam_id] = {
                        "id": exam_id,
                        "tick": exam.get("tick", 0),
                        "event": event_name,
                        "patient_id": exam.get("patient_id", ""),
                        "doctor_id": exam.get("doctor_id", "") or exam.get("details", {}).get("doctor_id") or exam.get("details", {}).get("agent_id", ""),
                        "items": normalized_items or [],
                        "status": exam.get("status", ""),
                        "completed_tick": exam.get("completed_tick"),
                        "results": exam.get("results") if exam.get("results") is not None else exam.get("result"),
                        "details": exam.get("details", {}),
                    }
                else:
                    existing["tick"] = min(existing.get("tick", exam.get("tick", 0)), exam.get("tick", 0))
                    if not existing.get("doctor_id"):
                        existing["doctor_id"] = exam.get("doctor_id", "") or exam.get("details", {}).get("doctor_id") or exam.get("details", {}).get("agent_id", "")
                    if not existing.get("items") and normalized_items:
                        existing["items"] = normalized_items

                    candidate_status = self._normalize_examination_status(
                        exam.get("status", ""),
                        event_name,
                        exam.get("completed_tick"),
                    )
                    if candidate_status == "completed":
                        existing["status"] = "completed"
                        existing["completed_tick"] = exam.get("completed_tick", existing.get("completed_tick"))
                        if exam.get("results") is not None:
                            existing["results"] = exam.get("results")
                        elif exam.get("result") not in (None, ""):
                            existing["results"] = exam.get("result")
            else:
                fallback = {
                    "id": exam.get("id", "") or exam_id,
                    "tick": exam.get("tick", 0),
                    "event": event_name,
                    "patient_id": exam.get("patient_id", ""),
                    "doctor_id": exam.get("doctor_id", "") or exam.get("details", {}).get("doctor_id") or exam.get("details", {}).get("agent_id", ""),
                    "items": normalized_items or [],
                    "status": exam.get("status", ""),
                    "completed_tick": exam.get("completed_tick"),
                    "results": exam.get("results") if exam.get("results") is not None else exam.get("result"),
                    "details": exam.get("details", {}),
                }
                normalized_status = self._normalize_examination_status(
                    fallback.get("status", ""),
                    fallback.get("event", ""),
                    fallback.get("completed_tick"),
                )
                if normalized_status == "completed":
                    completed_without_id.append(fallback)
                else:
                    pending_without_id.append(fallback)
        for completed in sorted(completed_without_id, key=lambda item: item.get("tick", 0)):
            matched_id = None
            for exam_id, pending in sorted(merged_by_id.items(), key=lambda kv: kv[1].get("tick", 0), reverse=True):
                pending_status = self._normalize_examination_status(
                    pending.get("status", ""),
                    pending.get("event", ""),
                    pending.get("completed_tick"),
                )
                if pending_status == "pending" and pending.get("tick", 0) <= completed.get("tick", 0):
                    matched_id = exam_id
                    break

            if matched_id:
                target = merged_by_id[matched_id]
                target["status"] = "completed"
                target["completed_tick"] = completed.get("tick", target.get("completed_tick"))
                if completed.get("results") is not None:
                    target["results"] = completed.get("results")
                elif completed.get("results") in (None, ""):
                    target["results"] = target.get("results")
                if not target.get("items") and completed.get("items"):
                    target["items"] = completed.get("items")
                if not target.get("doctor_id") and completed.get("doctor_id"):
                    target["doctor_id"] = completed.get("doctor_id")

        merged = list(merged_by_id.values()) + pending_without_id
        merged.sort(key=lambda item: (item.get("tick", 0), item.get("id", "")))
        self._set_patient_disk_cache(self._disk_examinations_cache, patient_id, merged)
        return list(merged)

    def _lazy_load_prescriptions_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """从磁盘懒加载特定患者的处方记录（优先从 tick 文件按需加载）。"""
        cached = self._disk_prescriptions_cache.get(patient_id)
        if cached is not None:
            return list(cached)

        if not self._log_dir:
            return []

        self._ensure_disk_prescriptions_index()
        prescriptions = list((self._disk_prescriptions_index or {}).get(patient_id, []))

        merged_by_id: Dict[str, Dict[str, Any]] = {}
        pending_without_id: List[Dict[str, Any]] = []
        completed_without_id: List[Dict[str, Any]] = []

        for presc in prescriptions:
            details = presc.get("details", {}) if isinstance(presc.get("details"), dict) else {}
            raw_id = presc.get("id") or presc.get("record_id") or details.get("record_id") or details.get("prescription_id")
            presc_id = str(raw_id) if raw_id else ""
            event_name = presc.get("event", "")

            diagnosis = presc.get("diagnosis")
            if diagnosis in (None, ""):
                diagnosis = details.get("diagnosis", "")

            treatment_plan = presc.get("treatment")
            if treatment_plan in (None, ""):
                treatment_plan = details.get("treatment_plan", details.get("treatment", ""))

            doctor_id = presc.get("doctor_id", "") or details.get("doctor_id") or details.get("agent_id", "")

            candidate = {
                "id": presc_id or presc.get("id", ""),
                "tick": presc.get("tick", 0),
                "event": event_name,
                "patient_id": presc.get("patient_id", ""),
                "doctor_id": doctor_id,
                "diagnosis": diagnosis,
                "treatment": treatment_plan,
                "status": presc.get("status", ""),
                "completed_tick": presc.get("completed_tick"),
                "details": details,
            }

            if presc_id.startswith("PRESC_"):
                existing = merged_by_id.get(presc_id)
                if not existing:
                    merged_by_id[presc_id] = candidate
                else:
                    existing["tick"] = min(existing.get("tick", candidate.get("tick", 0)), candidate.get("tick", 0))
                    if not existing.get("doctor_id"):
                        existing["doctor_id"] = candidate.get("doctor_id", "")
                    if not existing.get("diagnosis"):
                        existing["diagnosis"] = candidate.get("diagnosis", "")
                    if not existing.get("treatment"):
                        existing["treatment"] = candidate.get("treatment", "")

                    candidate_status = self._normalize_prescription_status(
                        candidate.get("status", ""),
                        candidate.get("event", ""),
                        candidate.get("completed_tick"),
                    )
                    if candidate_status == "completed":
                        existing["status"] = "completed"
                        existing["completed_tick"] = candidate.get("completed_tick") or candidate.get("tick", existing.get("completed_tick"))
            else:
                normalized_status = self._normalize_prescription_status(
                    candidate.get("status", ""),
                    candidate.get("event", ""),
                    candidate.get("completed_tick"),
                )
                if normalized_status == "completed":
                    completed_without_id.append(candidate)
                else:
                    pending_without_id.append(candidate)

        for completed in sorted(completed_without_id, key=lambda item: item.get("tick", 0)):
            matched_id = None
            for presc_id, pending in sorted(merged_by_id.items(), key=lambda kv: kv[1].get("tick", 0), reverse=True):
                pending_status = self._normalize_prescription_status(
                    pending.get("status", ""),
                    pending.get("event", ""),
                    pending.get("completed_tick"),
                )
                if pending_status == "pending" and pending.get("tick", 0) <= completed.get("tick", 0):
                    matched_id = presc_id
                    break

            if matched_id:
                target = merged_by_id[matched_id]
                target["status"] = "completed"
                target["completed_tick"] = completed.get("tick", target.get("completed_tick"))

        merged = list(merged_by_id.values()) + pending_without_id
        merged.sort(key=lambda item: (item.get("tick", 0), item.get("id", "")))
        self._set_patient_disk_cache(self._disk_prescriptions_cache, patient_id, merged)
        return list(merged)

    def get_conversation(self, agent1_id: str, agent2_id: str) -> List[Dict[str, Any]]:
        """获取两个 agent 之间的对话。"""
        self._ensure_data_loaded()

        in_memory = [
            m
            for m in self._messages
            if (m.get("sender") == agent1_id and m.get("receiver") == agent2_id)
            or (m.get("sender") == agent2_id and m.get("receiver") == agent1_id)
        ]

        if not self._log_dir:
            return sorted(in_memory, key=lambda m: (m.get("tick", 0), m.get("timestamp", "")))

        disk_messages = []
        try:
            filepath = Path(self._log_dir) / "messages.jsonl"
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                msg = json.loads(line)
                                if (
                                    (msg.get("sender") == agent1_id and msg.get("receiver") == agent2_id)
                                    or (msg.get("sender") == agent2_id and msg.get("receiver") == agent1_id)
                                ):
                                    disk_messages.append(msg)
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            print(f"[EventStore] Error lazy loading conversation {agent1_id}<->{agent2_id}: {e}")

        if not disk_messages:
            return sorted(in_memory, key=lambda m: (m.get("tick", 0), m.get("timestamp", "")))

        return self._merge_unique_messages(disk_messages, in_memory)

    def get_patient_status(self, patient_id: Optional[str] = None) -> Dict[str, Any]:
        """获取患者状态。"""
        self._ensure_data_loaded()

        if patient_id:
            return self._patient_status.get(patient_id, {})

        return self._patient_status.copy()

    def get_patient_trajectory(self, patient_id: str) -> List[Dict[str, Any]]:
        """获取患者的状态变化轨迹。"""
        self._ensure_data_loaded()
        if self._log_dir:
            return self._read_from_log("patient_status.jsonl", lambda s: s.get("patient_id") == patient_id)

        return []

    def get_examinations(self, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取检查记录。优先从内存获取，必要时从磁盘懒加载。"""
        self._ensure_data_loaded()

        if patient_id:
            in_memory_exams = self._examinations_by_patient.get(patient_id, [])
            if self._log_dir:
                disk_exams = self._lazy_load_examinations_for_patient(patient_id)
                exams = list(in_memory_exams) + list(disk_exams)
            else:
                exams = list(in_memory_exams)
        else:
            exams = list(self._examinations)
        exams_by_id: Dict[str, Dict[str, Any]] = {}
        unique_exams = []

        for exam in exams:
            exam_id = exam.get("id", "")
            if exam_id.startswith("EXAM_"):
                existing = exams_by_id.get(exam_id)
                if not existing:
                    exams_by_id[exam_id] = exam
                    continue

                existing_status = self._normalize_examination_status(
                    existing.get("status", "pending"),
                    existing.get("event", ""),
                    existing.get("completed_tick"),
                )
                candidate_status = self._normalize_examination_status(
                    exam.get("status", "pending"),
                    exam.get("event", ""),
                    exam.get("completed_tick"),
                )

                if existing_status != "completed" and candidate_status == "completed":
                    existing["status"] = exam.get("status", existing.get("status"))
                    existing["completed_tick"] = exam.get("completed_tick", existing.get("completed_tick"))

                if not existing.get("doctor_id") and exam.get("doctor_id"):
                    existing["doctor_id"] = exam.get("doctor_id")

                if not existing.get("items") and exam.get("items"):
                    existing["items"] = exam.get("items")

                if existing.get("results") is None and exam.get("results") is not None:
                    existing["results"] = exam.get("results")
                elif existing.get("result") in (None, "") and exam.get("result") not in (None, ""):
                    existing["result"] = exam.get("result")

                existing["tick"] = min(existing.get("tick", exam.get("tick", 0)), exam.get("tick", 0))
            elif exam_id.startswith("exam_"):
                continue
            else:
                unique_exams.append(exam)

        unique_exams = list(exams_by_id.values()) + unique_exams
        formatted_exams = []
        for exam in unique_exams:
            details = exam.get("details", {}) if isinstance(exam.get("details"), dict) else {}
            status = self._normalize_examination_status(
                exam.get("status", "pending"),
                exam.get("event", ""),
                exam.get("completed_tick"),
            )

            doctor_id = exam.get("doctor_id", "") or details.get("doctor_id") or details.get("agent_id", "")

            items = exam.get("items")
            if not items:
                items = details.get("items")
            if not items and exam.get("examination_type"):
                items = [exam.get("examination_type")]
            if isinstance(items, str):
                items = [items]
            if not items:
                items = []

            results = exam.get("results")
            if results is None:
                results = details.get("results")
            if results is None:
                results = exam.get("result")
            if results in ("", "Completed"):
                results = None

            formatted_exam = {
                "id": exam.get("id", "") or exam.get("record_id", ""),
                "patient_id": exam.get("patient_id", ""),
                "doctor_id": doctor_id,
                "examination_items": items,                                 
                "ordered_tick": exam.get("tick", 0),                           
                "status": status,        
                "completed_tick": exam.get("completed_tick"),
                "results": results,
            }
            formatted_exams.append(formatted_exam)
        formatted_exams.sort(key=lambda e: e.get("ordered_tick", 0), reverse=True)

        return formatted_exams

    def get_prescriptions(self, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取处方记录。优先从内存获取，必要时从磁盘懒加载。"""
        self._ensure_data_loaded()

        if patient_id:
            in_memory_prescriptions = self._prescriptions_by_patient.get(patient_id, [])
            if self._log_dir:
                disk_prescriptions = self._lazy_load_prescriptions_for_patient(patient_id)
                prescriptions = list(in_memory_prescriptions) + list(disk_prescriptions)
            else:
                prescriptions = list(in_memory_prescriptions)
        else:
            prescriptions = list(self._prescriptions)
        formatted_by_id: Dict[str, Dict[str, Any]] = {}
        fallback_prescriptions: List[Dict[str, Any]] = []

        for presc in prescriptions:
            details = presc.get("details", {}) if isinstance(presc.get("details"), dict) else {}

            doctor_id = presc.get("doctor_id", "") or details.get("doctor_id") or details.get("agent_id", "")

            diagnosis = presc.get("diagnosis")
            if diagnosis in (None, ""):
                diagnosis = details.get("diagnosis", "")

            treatment_plan = presc.get("treatment")
            if treatment_plan in (None, ""):
                treatment_plan = details.get("treatment_plan", details.get("treatment", ""))

            formatted_presc = {
                "id": presc.get("id", "") or details.get("record_id", "") or details.get("prescription_id", ""),
                "patient_id": presc.get("patient_id", ""),
                "doctor_id": doctor_id,
                "diagnosis": diagnosis,
                "treatment_plan": treatment_plan,                                  
                "prescribed_tick": presc.get("tick", 0),                                  
                "status": self._normalize_prescription_status(
                    presc.get("status", "pending"),
                    presc.get("event", ""),
                    presc.get("completed_tick"),
                ),
                "completed_tick": presc.get("completed_tick"),
                "treatment_result": presc.get("treatment_result"),
            }

            record_id = formatted_presc.get("id", "")
            if record_id and str(record_id).startswith("PRESC_"):
                existing = formatted_by_id.get(record_id)
                if not existing:
                    formatted_by_id[record_id] = formatted_presc
                    continue
                for field in ["doctor_id", "diagnosis", "treatment_plan", "treatment_result"]:
                    if not existing.get(field) and formatted_presc.get(field):
                        existing[field] = formatted_presc.get(field)

                existing_status = existing.get("status", "pending")
                candidate_status = formatted_presc.get("status", "pending")
                if existing_status != "completed" and candidate_status == "completed":
                    existing["status"] = "completed"
                    existing["completed_tick"] = formatted_presc.get("completed_tick", existing.get("completed_tick"))

                existing["prescribed_tick"] = min(
                    existing.get("prescribed_tick", formatted_presc.get("prescribed_tick", 0)),
                    formatted_presc.get("prescribed_tick", 0),
                )
            else:
                fallback_prescriptions.append(formatted_presc)

        formatted_prescriptions = list(formatted_by_id.values()) + fallback_prescriptions
        formatted_prescriptions.sort(key=lambda p: p.get("prescribed_tick", 0), reverse=True)

        return formatted_prescriptions

    def get_current_tick(self) -> int:
        """获取当前 tick。"""
        self._ensure_data_loaded()
        return self._current_tick

    def get_simulation_status(self) -> Dict[str, Any]:
        """获取模拟状态。"""
        self._ensure_data_loaded()

        return {
            "is_running": self._is_simulation_running,
            "current_tick": self._current_tick,
            "total_doctors": len(self.get_doctors()),
            "total_patients": len(self.get_patients()),
            "total_messages": len(self._messages),
            "total_events": len(self._all_events),
        }

    def get_all_events(self) -> List[Dict[str, Any]]:
        """获取所有事件（内存中的，可能不完整）。"""
        self._ensure_data_loaded()
        return list(self._all_events)

    def get_all_patient_summaries(self) -> Dict[str, Dict[str, Any]]:
        """
        批量获取所有患者的摘要信息（优化版本）。

        返回: Dict[patient_id, summary_data]
        summary_data 包含: phase, assigned_doctor, has_prescriptions, has_examinations, has_messages
        """
        self._ensure_data_loaded()
        valid_phases = {
            "idle", "home", "registered", "consulting", "examined", "treated", "finish",
            "waiting", "examination", "awaiting_results", "treatment", "completed", "follow_up",
        }
        def infer_phase(status: Dict[str, Any], prescriptions: List[Dict[str, Any]], examinations: List[Dict[str, Any]], messages: List[Dict[str, Any]]) -> str:
            raw_phase = status.get("phase", "")
            if raw_phase in valid_phases:
                return raw_phase

            completed_prescriptions = any(
                self._normalize_prescription_status(p.get("status"), p.get("event", ""), p.get("completed_tick")) == "completed"
                for p in prescriptions
            )
            pending_prescriptions = any(
                self._normalize_prescription_status(p.get("status"), p.get("event", ""), p.get("completed_tick")) == "pending"
                for p in prescriptions
            )
            completed_exams = any(
                self._normalize_examination_status(e.get("status"), e.get("event", ""), e.get("completed_tick")) == "completed"
                for e in examinations
            )
            pending_exams = any(
                self._normalize_examination_status(e.get("status"), e.get("event", ""), e.get("completed_tick")) == "pending"
                for e in examinations
            )

            if completed_prescriptions:
                return "finish"
            if pending_prescriptions:
                return "treated"
            if completed_exams and not pending_exams:
                return "examined"
            if pending_exams:
                return "consulting"
            if messages:
                return "consulting"
            if status.get("assigned_doctor") or status.get("event") == "PATIENT_REGISTER":
                return "registered"
            return "home"
        def infer_assigned_doctor(status: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
            assigned_doctor = status.get("assigned_doctor", "")
            if self._is_doctor_id(assigned_doctor):
                return assigned_doctor

            doctor_counts: Dict[str, int] = {}
            for msg in messages:
                sender = msg.get("sender", "")
                receiver = msg.get("receiver", "")
                doctor_id = sender if self._is_doctor_id(sender) else (receiver if self._is_doctor_id(receiver) else None)
                if doctor_id:
                    doctor_counts[doctor_id] = doctor_counts.get(doctor_id, 0) + 1

            if doctor_counts:
                return max(doctor_counts, key=doctor_counts.get)
            return assigned_doctor
        def get_disk_patient_summary_map() -> Dict[str, Dict[str, Any]]:
            if self._disk_patient_summary_cache is not None:
                return self._disk_patient_summary_cache

            summary_map: Dict[str, Dict[str, Any]] = {}
            if not self._log_dir:
                self._disk_patient_summary_cache = summary_map
                return summary_map

            for patient in self.get_patients():
                patient_id = patient.get("id", "")
                if not self._is_patient_id(patient_id):
                    continue

                status = self._patient_status.get(patient_id, {})
                status_details = status.get("details", {}) if isinstance(status.get("details"), dict) else {}

                summary_map[patient_id] = {
                    "_status": status,
                    "_has_messages": False,
                    "_pending_examinations": False,
                    "_completed_examinations": False,
                    "_pending_prescriptions": False,
                    "_completed_prescriptions": False,
                    "_doctor_counts": {},
                    "department": status.get("department") or status_details.get("department", ""),
                }

            if not summary_map:
                self._disk_patient_summary_cache = {}
                return {}
            for msg in self._read_from_log("messages.jsonl"):
                sender = msg.get("sender", "")
                receiver = msg.get("receiver", "")
                doctor_id = sender if self._is_doctor_id(sender) else (receiver if self._is_doctor_id(receiver) else "")

                for participant in (sender, receiver):
                    if not self._is_patient_id(participant):
                        continue
                    patient_summary = summary_map.get(participant)
                    if not patient_summary:
                        continue

                    patient_summary["_has_messages"] = True
                    if doctor_id:
                        doctor_counts = patient_summary["_doctor_counts"]
                        doctor_counts[doctor_id] = doctor_counts.get(doctor_id, 0) + 1
            for exam in self._read_from_log("examinations.jsonl"):
                patient_id = exam.get("patient_id", "")
                patient_summary = summary_map.get(patient_id)
                if not patient_summary:
                    continue

                status = self._normalize_examination_status(
                    exam.get("status"),
                    exam.get("event", ""),
                    exam.get("completed_tick"),
                )
                if status == "completed":
                    patient_summary["_completed_examinations"] = True
                elif status == "pending":
                    patient_summary["_pending_examinations"] = True
            for prescription in self._read_from_log("prescriptions.jsonl"):
                patient_id = prescription.get("patient_id", "")
                patient_summary = summary_map.get(patient_id)
                if not patient_summary:
                    continue

                status = self._normalize_prescription_status(
                    prescription.get("status"),
                    prescription.get("event", ""),
                    prescription.get("completed_tick"),
                )
                if status == "completed":
                    patient_summary["_completed_prescriptions"] = True
                elif status == "pending":
                    patient_summary["_pending_prescriptions"] = True

            finalized_summary: Dict[str, Dict[str, Any]] = {}
            for patient_id, patient_summary in summary_map.items():
                status = patient_summary.get("_status", {})

                raw_phase = status.get("phase", "")
                if raw_phase in valid_phases:
                    phase = raw_phase
                elif patient_summary.get("_completed_prescriptions"):
                    phase = "finish"
                elif patient_summary.get("_pending_prescriptions"):
                    phase = "treated"
                elif patient_summary.get("_completed_examinations") and not patient_summary.get("_pending_examinations"):
                    phase = "examined"
                elif patient_summary.get("_pending_examinations"):
                    phase = "consulting"
                elif patient_summary.get("_has_messages"):
                    phase = "consulting"
                elif status.get("assigned_doctor") or status.get("event") == "PATIENT_REGISTER":
                    phase = "registered"
                else:
                    phase = "home"

                assigned_doctor = status.get("assigned_doctor", "")
                if not self._is_doctor_id(assigned_doctor):
                    doctor_counts = patient_summary.get("_doctor_counts", {})
                    if doctor_counts:
                        assigned_doctor = max(doctor_counts, key=doctor_counts.get)

                finalized_summary[patient_id] = {
                    "phase": phase,
                    "assigned_doctor": assigned_doctor,
                    "department": patient_summary.get("department", ""),
                }

            self._disk_patient_summary_cache = finalized_summary
            return finalized_summary

        phase_rank = {
            "idle": 0,
            "home": 0,
            "registered": 1,
            "waiting": 2,
            "consulting": 2,
            "examination": 2,
            "awaiting_results": 2,
            "examined": 3,
            "treated": 4,
            "treatment": 4,
            "completed": 4,
            "follow_up": 4,
            "finish": 5,
        }

        result = {}
        disk_summary_map = get_disk_patient_summary_map()

        for patient_id in self._agents:
            if not self._is_patient_id(patient_id):
                continue

            status = self._patient_status.get(patient_id, {})
            prescriptions = self._prescriptions_by_patient.get(patient_id, [])
            examinations = self._examinations_by_patient.get(patient_id, [])
            messages = self._messages_by_patient.get(patient_id, [])

            status_details = status.get("details", {}) if isinstance(status.get("details"), dict) else {}

            memory_summary = {
                "phase": infer_phase(status, prescriptions, examinations, messages),
                "assigned_doctor": infer_assigned_doctor(status, messages),
                "department": status.get("department") or status_details.get("department", ""),
            }

            disk_summary = disk_summary_map.get(patient_id)
            if not disk_summary:
                result[patient_id] = memory_summary
                continue
            if patient_id not in self._active_patient_ids:
                result[patient_id] = disk_summary
                continue
            memory_rank = phase_rank.get(memory_summary["phase"], 0)
            disk_rank = phase_rank.get(disk_summary.get("phase", ""), 0)

            if disk_rank > memory_rank:
                merged_summary = dict(memory_summary)
                merged_summary["phase"] = disk_summary.get("phase", memory_summary["phase"])
                if not merged_summary.get("assigned_doctor") and disk_summary.get("assigned_doctor"):
                    merged_summary["assigned_doctor"] = disk_summary["assigned_doctor"]
                if not merged_summary.get("department") and disk_summary.get("department"):
                    merged_summary["department"] = disk_summary["department"]
                result[patient_id] = merged_summary
            else:
                result[patient_id] = memory_summary

        return result

    def _load_initial_agents(self):
        """从日志目录或项目数据目录加载初始 agents。"""
        if not self._log_dir:
            return
        agents = self._read_from_log("agents.jsonl")
        if agents:
            for agent in agents:
                agent_id = agent.get("id", "")
                if agent_id:
                    self._agents[agent_id] = agent
            print(f"[EventStore] Loaded {len(agents)} agents from agents.jsonl")
            return
        self._load_from_project_data()

    def _load_from_project_data(self):
        """从项目 data 目录加载 agent profiles。"""
        if not self._log_dir:
            return
        project_path = Path(self._log_dir).parent
        data_dir = project_path / "data"

        if not data_dir.exists():
            print(f"[EventStore] Data directory not found: {data_dir}")
            return

        loaded_count = 0
        doctor_profiles_path = data_dir / "doctors" / "profiles.jsonl"
        if doctor_profiles_path.exists():
            try:
                with open(doctor_profiles_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            profile = json.loads(line)
                            agent_id = profile.get("id", "")
                            if agent_id:
                                self._agents[agent_id] = {"id": agent_id, "template": "DoctorAgent", **profile}
                                loaded_count += 1
            except Exception as e:
                print(f"[EventStore] Error loading doctor profiles: {e}")
        patient_profiles_path = data_dir / "patients" / "profiles.jsonl"
        if patient_profiles_path.exists():
            try:
                with open(patient_profiles_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            profile = json.loads(line)
                            agent_id = profile.get("id", "")
                            if agent_id:
                                self._agents[agent_id] = {"id": agent_id, "template": "PatientAgent", **profile}
                                loaded_count += 1
            except Exception as e:
                print(f"[EventStore] Error loading patient profiles: {e}")

        if loaded_count > 0:
            print(f"[EventStore] Loaded {loaded_count} agents from project data directory")

    def _write_event_to_disk(self, event: Dict[str, Any]):
        """将事件写入本地 JSONL 文件（复用 FileEventLogger 的分类逻辑）。"""
        if not self._log_dir:
            return

        try:
            tick = event.get("tick", 0)
            event_name = event.get("name", "")
            payload = event.get("payload", {})
            timestamp = event.get("timestamp", "")
            event_line = json.dumps(event, ensure_ascii=False) + "\n"
            tick_file = self._resolve_tick_file(tick)
            tick_file.parent.mkdir(parents=True, exist_ok=True)
            with open(tick_file, "a", encoding="utf-8") as f:
                f.write(event_line)
            all_events_file = Path(self._log_dir) / "all_events.jsonl"
            with open(all_events_file, "a", encoding="utf-8") as f:
                f.write(event_line)
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
                    "timestamp": timestamp,
                }
                if patient_id:
                    msg["patient_id"] = patient_id
                self._append_jsonl("messages.jsonl", msg)

            elif event_name in ["PATIENT_MOVE", "PATIENT_REGISTER"]:
                status = {
                    "patient_id": payload.get("agent_id", ""),
                    "tick": tick,
                    "event": event_name,
                    "location": payload.get("location", payload.get("target_location", "")),
                    "phase": payload.get("phase", ""),
                    "status": payload.get("status", ""),
                    "details": payload,
                    "timestamp": timestamp,
                }
                self._append_jsonl("patient_status.jsonl", status)

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
                    "timestamp": timestamp,
                }
                self._append_jsonl("examinations.jsonl", exam)

            elif event_name in ["PRESCRIBE_TREATMENT", "RECEIVE_TREATMENT"]:
                prescription = {
                    "tick": tick,
                    "event": event_name,
                    "patient_id": payload.get("patient_id", payload.get("agent_id", "")),
                    "doctor_id": payload.get("doctor_id", ""),
                    "treatment": payload.get("treatment", payload.get("treatment_plan", "")),
                    "status": payload.get("status", ""),
                    "details": payload,
                    "timestamp": timestamp,
                }
                self._append_jsonl("prescriptions.jsonl", prescription)

        except Exception as e:
            print(f"[EventStore] Error writing event to disk: {e}")

    def _append_jsonl(self, filename: str, data: Dict[str, Any]):
        """追加一行 JSON 到指定文件。"""
        if not self._log_dir:
            return
        filepath = Path(self._log_dir) / filename
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _read_from_log(self, filename: str, filter_fn=None) -> List[Dict[str, Any]]:
        """从日志文件读取数据。"""
        if not self._log_dir:
            return []

        filepath = Path(self._log_dir) / filename
        if not filepath.exists():
            return []

        result = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            if filter_fn is None or filter_fn(data):
                                result.append(data)
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            print(f"Error reading log file {filename}: {e}")

        return result
_event_store: Optional[EventStore] = None


def get_event_store() -> EventStore:
    """获取事件存储单例。"""
    global _event_store
    if _event_store is None:
        _event_store = EventStore()
    return _event_store
