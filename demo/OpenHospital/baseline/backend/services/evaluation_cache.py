"""
Evaluation Cache Service - Cache LLM evaluation results to avoid redundant calls.

Memory Optimization:
- 使用 OrderedDict 实现 LRU 淘汰策略
- 限制缓存最大条目数
"""

import json
import logging
import hashlib
import os
from typing import Dict, Any, Optional
from pathlib import Path
from collections import OrderedDict

logger = logging.getLogger(__name__)

def _resolve_max_cache_size() -> int:
    """Resolve cache size from env with safe fallback."""
    raw = os.environ.get("HOSPITAL_EVAL_CACHE_MAX_SIZE", "1000").strip()
    try:
        size = int(raw)
        if size > 0:
            return size
    except Exception:
        pass
    return 1000
MAX_CACHE_SIZE = _resolve_max_cache_size()


class EvaluationCache:
    """
    Cache for LLM evaluation results.
    Persists to disk to survive restarts.
    Uses LRU eviction when cache exceeds max size.
    """

    def __init__(self, cache_file: str = "evaluation_cache.json"):
        self.cache_file = Path(cache_file)
        self._cache: OrderedDict = OrderedDict()                         
        self._max_size = MAX_CACHE_SIZE
        self._load_cache()

    def _load_cache(self):
        """Load cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._cache = OrderedDict(data)
                    while len(self._cache) > self._max_size:
                        self._cache.popitem(last=False)         
                logger.info(f"Loaded {len(self._cache)} evaluation results from cache")
            except Exception as e:
                logger.error(f"Failed to load evaluation cache: {e}")
                self._cache = OrderedDict()

    def _save_cache(self):
        """Save cache to disk."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(dict(self._cache), ensure_ascii=False, indent=2, fp=f)
        except Exception as e:
            logger.error(f"Failed to save evaluation cache: {e}")

    def _generate_key(self, doctor_id: str, patient_id: str, diagnosis, treatment_plan: str) -> str:
        """Generate a unique key for the evaluation request."""
        if isinstance(diagnosis, list):
            diagnosis_str = ", ".join(diagnosis)
        else:
            diagnosis_str = diagnosis.strip() if diagnosis else ""
        content = f"{doctor_id}:{patient_id}:{diagnosis_str}:{treatment_plan.strip()}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def get_evaluation(self, doctor_id: str, patient_id: str, diagnosis, treatment_plan: str) -> Optional[Dict[str, Any]]:
        """Get cached evaluation result (updates LRU order)."""
        key = self._generate_key(doctor_id, patient_id, diagnosis, treatment_plan)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set_evaluation(self, doctor_id: str, patient_id: str, diagnosis, treatment_plan: str, result: Dict[str, Any]):
        """Cache evaluation result with LRU eviction."""
        key = self._generate_key(doctor_id, patient_id, diagnosis, treatment_plan)
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            while len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug(f"Evicted cache entry: {evicted_key}")

        self._cache[key] = result
        self._save_cache()
_evaluation_cache: Optional[EvaluationCache] = None

def get_evaluation_cache() -> EvaluationCache:
    """Get the global evaluation cache instance."""
    global _evaluation_cache
    env_log_dir = os.environ.get("MAS_EVENT_LOG_DIR", "").strip()
    if env_log_dir and Path(env_log_dir).is_dir():
        cache_path = Path(env_log_dir) / "evaluation_cache.json"
    else:
        cache_path = Path("baseline/decoupling_output/evaluation_cache.json")

    if _evaluation_cache is None or _evaluation_cache.cache_file != cache_path:
        _evaluation_cache = EvaluationCache(str(cache_path))
    return _evaluation_cache
