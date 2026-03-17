"""
Prompt persistence utilities for Hospital Simulation.
"""

import os
import re
from pathlib import Path
from typing import Any, Optional

from agentkernel_distributed.toolkit.logger import get_logger

logger = get_logger(__name__)

PROMPT_SAVE_ENV = "HOSPITAL_SAVE_PROMPT"
LEGACY_PROMPT_SAVE_ENV = "MAS_SAVE_PROMPT"


def _parse_bool_env(raw_value: Optional[str], default: bool = True) -> bool:
    """Parse a boolean-like environment variable value."""
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if not value:
        return default

    if value in {"1", "true", "yes", "on", "y", "t"}:
        return True
    if value in {"0", "false", "no", "off", "n", "f"}:
        return False

    return default


def should_save_prompt() -> bool:
    """Whether prompt persistence is enabled via environment variable."""
    raw_value = os.environ.get(PROMPT_SAVE_ENV)
    if raw_value is None:
        raw_value = os.environ.get(LEGACY_PROMPT_SAVE_ENV)
    return _parse_bool_env(raw_value, default=True)


def _sanitize_filename_part(value: str) -> str:
    """Sanitize value for safe usage in filenames."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    return cleaned.strip("._")


def save_prompt(
    *,
    agent_id: str,
    tick: int,
    context_id: str = "",
    stage: str = "",
    system_prompt: str = "",
    user_prompt: str = "",
    response: str = "",
    plugin_logger: Optional[Any] = None,
) -> Optional[Path]:
    """Save prompts and model response to a debug file if enabled."""
    if not should_save_prompt():
        return None

    active_logger = plugin_logger or logger

    try:
        project_root = Path(os.environ.get("MAS_PROJECT_ABS_PATH", os.getcwd()))
        custom_dir = os.environ.get("MAS_DEBUG_PROMPT_DIR")
        output_dir = Path(custom_dir) if custom_dir else project_root / "debug_prompts"
        output_dir.mkdir(parents=True, exist_ok=True)

        file_parts = [
            _sanitize_filename_part(agent_id),
            _sanitize_filename_part(context_id) if context_id else "",
            _sanitize_filename_part(str(tick)),
            _sanitize_filename_part(stage) if stage else "",
        ]
        filename = "_".join([part for part in file_parts if part]) + ".txt"
        prompt_file = output_dir / filename

        stage_label = stage or "N/A"

        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"SYSTEM PROMPT (Stage: {stage_label})\n")
            f.write("=" * 80 + "\n")
            f.write(system_prompt if system_prompt else "(No system prompt)")
            f.write("\n\n")

            f.write("=" * 80 + "\n")
            f.write("USER PROMPT\n")
            f.write("=" * 80 + "\n")
            f.write(user_prompt if user_prompt else "(No user prompt)")
            f.write("\n")

            if response:
                f.write("\n" + "=" * 80 + "\n")
                f.write("MODEL RESPONSE\n")
                f.write("=" * 80 + "\n")
                f.write(response)
                f.write("\n")

        active_logger.info("[%s] Saved prompts to %s", agent_id, prompt_file)
        return prompt_file
    except Exception as e:
        active_logger.warning("[%s] Failed to save prompt: %s", agent_id, e)
        return None
