"""Helpers for building a Ray runtime environment for the baseline project."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


def _resolve_working_dir(project_path: str) -> Path:
    """Return the directory that should be added to worker PYTHONPATH."""
    project_dir = Path(project_path).resolve()
    package_name = os.environ.get("MAS_PROJECT_REL_PATH", project_dir.name)
    if project_dir.name == package_name:
        return project_dir.parent

    return project_dir


def build_ray_runtime_env(project_path: str, extra_env_vars: Dict[str, str] | None = None) -> Dict[str, Any]:
    """Build a runtime_env that keeps the baseline package importable on Ray workers."""
    project_dir = Path(project_path).resolve()
    working_dir = _resolve_working_dir(project_path)
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    pythonpath_parts = [str(working_dir)]

    if current_pythonpath:
        pythonpath_parts.append(current_pythonpath)

    env_vars = {
        "MAS_PROJECT_ABS_PATH": str(project_dir),
        "MAS_PROJECT_REL_PATH": os.environ.get("MAS_PROJECT_REL_PATH", project_dir.name),
        "PYTHONPATH": os.pathsep.join(pythonpath_parts),
    }

    if extra_env_vars:
        env_vars.update(extra_env_vars)

    project_rel = project_dir.relative_to(working_dir).as_posix() if project_dir != working_dir else ""

    def under_project(path: str) -> str:
        return f"{project_rel}/{path}" if project_rel else path

    return {
        "working_dir": str(working_dir),
        "env_vars": env_vars,
        "excludes": [
            "*.pyc",
            "__pycache__",
            ".git",
            ".idea",
            under_project("logs"),
            under_project("data"),
            under_project("decoupling_output"),
            under_project("decoupling_output_copy"),
            under_project("experiments"),
            under_project("workspace"),
            under_project("cache"),
            "node_modules",
            under_project("frontend/node_modules"),
            under_project("frontend/dist"),
        ],
    }
