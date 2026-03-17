#!/usr/bin/env python3

"""Run long-horizon train-by-batch + fixed-test evaluation pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_DIR = REPO_ROOT / "baseline"
DEFAULT_SPLIT_DIR = REPO_ROOT / ".private_data" / "splits"
DEFAULT_RUNS_DIR = PROJECT_DIR / "experiments" / "runs"


@dataclass
class BatchPaths:
    index: int
    batch_dir: Path
    train_patient_profiles: Path
    train_ground_truth: Path
    train_examination_data: Path
    train_patient_ids: Path


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object from {path}")
    return data


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def _count_ids(path: Path) -> int:
    total = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total += 1
    return total


def _load_batch_dirs(split_dir: Path) -> List[BatchPaths]:
    train_batches_dir = split_dir / "train_batches"
    if not train_batches_dir.exists():
        raise FileNotFoundError(f"Missing train_batches directory: {train_batches_dir}")

    batch_entries: List[Tuple[int, Path]] = []
    for entry in train_batches_dir.iterdir():
        if not entry.is_dir():
            continue
        match = re.match(r"batch_(\d+)$", entry.name)
        if not match:
            continue
        batch_index = int(match.group(1))
        batch_entries.append((batch_index, entry))

    if not batch_entries:
        raise ValueError(f"No batch_* directories found under {train_batches_dir}")

    batch_entries.sort(key=lambda item: item[0])

    batch_paths: List[BatchPaths] = []
    for batch_index, batch_dir in batch_entries:
        batch_paths.append(
            BatchPaths(
                index=batch_index,
                batch_dir=batch_dir,
                train_patient_profiles=batch_dir / "profiles.jsonl",
                train_ground_truth=batch_dir / "ground_truth.json",
                train_examination_data=batch_dir / "examination_data.json",
                train_patient_ids=batch_dir / "patient_ids.txt",
            )
        )
    return batch_paths


def _validate_split_dir(split_dir: Path) -> Dict[str, Any]:
    manifest_path = split_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Split manifest not found: {manifest_path}")

    manifest = _read_json(manifest_path)
    required_paths = [
        split_dir / "shared" / "doctor_profiles.jsonl",
        split_dir / "test" / "profiles.jsonl",
        split_dir / "test" / "ground_truth.json",
        split_dir / "test" / "examination_data.json",
        split_dir / "test" / "patient_ids.txt",
    ]
    for required in required_paths:
        if not required.exists():
            raise FileNotFoundError(f"Missing split artifact: {required}")

    return manifest


def _run_command(
    command: List[str],
    env: Optional[Dict[str, str]],
    cwd: Path,
    log_path: Path,
    dry_run: bool = False,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd_display = " ".join(command)

    if dry_run:
        print(f"[DRY-RUN] {cmd_display}")
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"[DRY-RUN] {cmd_display}\n")
        return 0

    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write("\n" + "=" * 120 + "\n")
        log_file.write(f"[{datetime.now().isoformat()}] {cmd_display}\n")

        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log_file.write(line)

        process.wait()
        log_file.write(f"[EXIT CODE] {process.returncode}\n")
        return process.returncode


def _resolve_experiment_dir(args: argparse.Namespace) -> Path:
    if args.experiment_dir:
        return args.experiment_dir

    experiment_name = args.experiment_name or f"batch_train_eval_{_timestamp()}"
    return DEFAULT_RUNS_DIR / experiment_name


def _load_or_init_state(
    state_path: Path,
    args: argparse.Namespace,
    split_dir: Path,
    reflection_namespace: str,
    experiment_name: str,
) -> Dict[str, Any]:
    if state_path.exists():
        if not args.resume:
            raise FileExistsError(
                f"State file already exists: {state_path}. Use --resume or --reset-experiment."
            )
        state = _read_json(state_path)
        return state

    state = {
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "experiment_name": experiment_name,
        "split_dir": str(split_dir),
        "reflection_namespace": reflection_namespace,
        "completed_batches": [],
        "results": [],
    }
    _write_json(state_path, state)
    return state


def _build_simulation_command(
    data_patient_profiles: Path,
    data_doctor_profiles: Path,
    data_ground_truth: Path,
    data_examination_data: Path,
    event_log_dir: Path,
    trajectory_output: Path,
    reflection_mode: str,
    reflection_namespace: str,
    max_active_patients: Optional[int],
    max_ticks: Optional[int],
) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "baseline.run_simulation",
        "--patient-profiles",
        str(data_patient_profiles),
        "--doctor-profiles",
        str(data_doctor_profiles),
        "--ground-truth",
        str(data_ground_truth),
        "--examination-data",
        str(data_examination_data),
        "--event-log-dir",
        str(event_log_dir),
        "--trajectory-output",
        str(trajectory_output),
        "--reflection-mode",
        reflection_mode,
        "--reflection-namespace",
        reflection_namespace,
        "--skip-api-server",
    ]

    if max_active_patients is not None:
        command.extend(["--max-active-patients", str(max_active_patients)])
    if max_ticks is not None:
        command.extend(["--max-ticks", str(max_ticks)])

    return command


def _build_evaluation_command(
    trajectory_path: Path,
    ground_truth_path: Path,
    patient_profiles_path: Path,
    report_output: Path,
    eval_config: Optional[Path],
    precomputed_treatment_eval: Optional[Path],
    no_llm_fallback: bool,
    quiet_eval: bool,
    max_concurrency: Optional[int],
) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "benchmark.evaluate.evaluate",
        "--trajectory",
        str(trajectory_path),
        "--ground-truth",
        str(ground_truth_path),
        "--patient-data",
        str(patient_profiles_path),
        "--output",
        str(report_output),
    ]

    if eval_config:
        command.extend(["--config", str(eval_config)])
    if max_concurrency is not None:
        command.extend(["--max-concurrency", str(max_concurrency)])

    if precomputed_treatment_eval:
        command.extend(["--precomputed-treatment-eval", str(precomputed_treatment_eval)])
    if no_llm_fallback:
        command.append("--no-llm-fallback")
    if quiet_eval:
        command.append("--quiet")

    return command


def _append_metrics_csv(metrics_csv_path: Path, row: Dict[str, Any]) -> None:
    metrics_csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "batch_index",
        "batch_train_patients",
        "cumulative_train_patients",
        "test_patients",
        "diagnosis_accuracy",
        "examination_precision",
        "treatment_matching_score",
        "total_input_tokens",
        "report_path",
    ]

    write_header = not metrics_csv_path.exists()
    with open(metrics_csv_path, "a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({key: row.get(key) for key in fieldnames})


def _extract_summary(report_path: Path) -> Dict[str, Any]:
    report = _read_json(report_path)
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        raise ValueError(f"Invalid summary in report: {report_path}")
    return summary


def _is_nonempty_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def _build_batch_prompt_dirs(artifacts_dir: Path) -> Dict[str, Path]:
    """Build train/val prompt directories for one batch."""
    debug_root = artifacts_dir / "debug_prompts"
    return {
        "train": debug_root / "train",
        "val": debug_root / "val",
    }


def _print_batch_summary(result: Dict[str, Any]) -> None:
    print("\n" + "-" * 80)
    print(f"Batch {result['batch_index']} completed")
    print(f"- Batch train patients: {result['batch_train_patients']}")
    print(f"- Cumulative train patients: {result['cumulative_train_patients']}")
    print(f"- Test diagnosis accuracy: {result['diagnosis_accuracy']:.4f}")
    print(f"- Test examination precision: {result['examination_precision']:.4f}")
    print(f"- Test treatment matching score: {result['treatment_matching_score']:.4f}")
    print("-" * 80)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run train-by-batch (100 patients each) with fixed test evaluation after each batch"
    )
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR, help="Prepared split directory")
    parser.add_argument("--experiment-dir", type=Path, default=None, help="Experiment output directory")
    parser.add_argument("--experiment-name", type=str, default=None, help="Experiment name")
    parser.add_argument("--reflection-namespace", type=str, default=None, help="Reflection namespace")
    parser.add_argument("--reflection-store-dir", type=Path, default=None, help="Reflection store directory")

    parser.add_argument("--resume", action="store_true", help="Resume from existing state")
    parser.add_argument("--reset-experiment", action="store_true", help="Delete experiment directory before run")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue to next batch on error")

    parser.add_argument("--start-batch", type=int, default=1, help="Start batch index (1-based)")
    parser.add_argument("--end-batch", type=int, default=None, help="End batch index (inclusive)")

    parser.add_argument("--max-active-patients", type=int, default=None, help="Override max active patients")
    parser.add_argument("--max-ticks", type=int, default=None, help="Override max ticks")

    parser.add_argument("--precomputed-treatment-eval", type=Path, default=None, help="Precomputed treatment scores")
    parser.add_argument("--no-llm-fallback", action="store_true", help="Fail evaluation if precomputed missing")
    parser.add_argument("--quiet-eval", action="store_true", help="Pass --quiet to evaluator")
    parser.add_argument(
        "--eval-config",
        type=Path,
        default=None,
        help="Path passed to benchmark.evaluate.evaluate --config",
    )
    parser.add_argument(
        "--eval-max-concurrency",
        type=int,
        default=None,
        help="Maximum concurrent LLM requests inside one evaluation run (overrides eval config)",
    )

    args = parser.parse_args()

    if args.start_batch <= 0:
        raise ValueError("--start-batch must be >= 1")
    if args.end_batch is not None and args.end_batch < args.start_batch:
        raise ValueError("--end-batch must be >= --start-batch")
    if args.eval_max_concurrency is not None and args.eval_max_concurrency <= 0:
        raise ValueError("--eval-max-concurrency must be >= 1")

    return args


def main() -> None:
    args = parse_args()

    split_dir = args.split_dir.resolve()
    experiment_dir = _resolve_experiment_dir(args).resolve()
    experiment_name = args.experiment_name or experiment_dir.name

    if args.reset_experiment and experiment_dir.exists():
        shutil.rmtree(experiment_dir)

    experiment_dir.mkdir(parents=True, exist_ok=True)
    _validate_split_dir(split_dir)

    reflection_namespace = args.reflection_namespace or experiment_dir.name
    reflection_store_dir = (
        args.reflection_store_dir.resolve()
        if args.reflection_store_dir
        else (experiment_dir / "reflection_store")
    )

    state_path = experiment_dir / "state.json"
    state = _load_or_init_state(
        state_path=state_path,
        args=args,
        split_dir=split_dir,
        reflection_namespace=reflection_namespace,
        experiment_name=experiment_name,
    )

    batch_paths = _load_batch_dirs(split_dir)
    if args.end_batch is None:
        selected_batches = [batch for batch in batch_paths if batch.index >= args.start_batch]
    else:
        selected_batches = [batch for batch in batch_paths if args.start_batch <= batch.index <= args.end_batch]

    if not selected_batches:
        raise ValueError("No batches selected to run")

    completed_batches = {int(i) for i in state.get("completed_batches", [])}
    cumulative_train_patients = 0
    for record in state.get("results", []):
        if isinstance(record, dict):
            cumulative_train_patients = max(cumulative_train_patients, int(record.get("cumulative_train_patients", 0)))

    doctor_profiles_path = split_dir / "shared" / "doctor_profiles.jsonl"
    test_profiles_path = split_dir / "test" / "profiles.jsonl"
    test_ground_truth_path = split_dir / "test" / "ground_truth.json"
    test_examination_data_path = split_dir / "test" / "examination_data.json"
    test_patients_count = _count_ids(split_dir / "test" / "patient_ids.txt")

    metrics_csv_path = experiment_dir / "metrics.csv"

    for batch in selected_batches:
        if batch.index in completed_batches:
            print(f"Skip completed batch {batch.index}")
            continue

        print(f"\n=== Running batch {batch.index} ===")

        artifacts_dir = experiment_dir / "artifacts" / f"batch_{batch.index:04d}"
        train_event_log_dir = artifacts_dir / "train_event_logs"
        test_event_log_dir = artifacts_dir / "test_event_logs"
        train_trajectory = artifacts_dir / "train_trajectory.json"
        test_trajectory = artifacts_dir / "test_trajectory.json"
        eval_report = artifacts_dir / "test_eval_report.json"
        batch_log = artifacts_dir / "commands.log"
        prompt_dirs = _build_batch_prompt_dirs(artifacts_dir)
        train_prompt_dir = prompt_dirs["train"]
        val_prompt_dir = prompt_dirs["val"]

        env = os.environ.copy()
        env["HOSPITAL_REFLECTION_NAMESPACE"] = reflection_namespace
        env["HOSPITAL_REFLECTION_STORE_DIR"] = str(reflection_store_dir)

        print(f"Prompt directories (batch {batch.index}):")
        print(f"- train: {train_prompt_dir}")
        print(f"- val:   {val_prompt_dir}")

        summary: Optional[Dict[str, Any]] = None

        if args.resume and not args.dry_run and _is_nonempty_file(train_trajectory):
            print(f"Reuse existing train trajectory for batch {batch.index}: {train_trajectory}")
        else:
            train_command = _build_simulation_command(
                data_patient_profiles=batch.train_patient_profiles,
                data_doctor_profiles=doctor_profiles_path,
                data_ground_truth=batch.train_ground_truth,
                data_examination_data=batch.train_examination_data,
                event_log_dir=train_event_log_dir,
                trajectory_output=train_trajectory,
                reflection_mode="write",
                reflection_namespace=reflection_namespace,
                max_active_patients=args.max_active_patients,
                max_ticks=args.max_ticks,
            )

            train_code = _run_command(
                command=train_command,
                env={
                    **env,
                    "MAS_DEBUG_PROMPT_DIR": str(train_prompt_dir),
                },
                cwd=REPO_ROOT,
                log_path=batch_log,
                dry_run=args.dry_run,
            )
            if train_code != 0:
                message = f"Batch {batch.index} train run failed (exit code={train_code})"
                print(message)
                if not args.continue_on_error:
                    raise RuntimeError(message)
                continue

        if args.resume and not args.dry_run and _is_nonempty_file(test_trajectory):
            print(f"Reuse existing test trajectory for batch {batch.index}: {test_trajectory}")
        else:
            test_command = _build_simulation_command(
                data_patient_profiles=test_profiles_path,
                data_doctor_profiles=doctor_profiles_path,
                data_ground_truth=test_ground_truth_path,
                data_examination_data=test_examination_data_path,
                event_log_dir=test_event_log_dir,
                trajectory_output=test_trajectory,
                reflection_mode="read_only",
                reflection_namespace=reflection_namespace,
                max_active_patients=args.max_active_patients,
                max_ticks=args.max_ticks,
            )

            test_code = _run_command(
                command=test_command,
                env={
                    **env,
                    "MAS_DEBUG_PROMPT_DIR": str(val_prompt_dir),
                },
                cwd=REPO_ROOT,
                log_path=batch_log,
                dry_run=args.dry_run,
            )
            if test_code != 0:
                message = f"Batch {batch.index} test run failed (exit code={test_code})"
                print(message)
                if not args.continue_on_error:
                    raise RuntimeError(message)
                continue

        if args.resume and not args.dry_run and _is_nonempty_file(eval_report):
            try:
                summary = _extract_summary(eval_report)
                print(f"Reuse existing evaluation report for batch {batch.index}: {eval_report}")
            except Exception as exc:
                print(
                    f"Existing evaluation report is invalid for batch {batch.index} ({exc}); rerunning evaluation."
                )

        if summary is None:
            eval_command = _build_evaluation_command(
                trajectory_path=test_trajectory,
                ground_truth_path=test_ground_truth_path,
                patient_profiles_path=test_profiles_path,
                report_output=eval_report,
                eval_config=args.eval_config,
                precomputed_treatment_eval=args.precomputed_treatment_eval,
                no_llm_fallback=args.no_llm_fallback,
                quiet_eval=args.quiet_eval,
                max_concurrency=args.eval_max_concurrency,
            )

            eval_code = _run_command(
                command=eval_command,
                env=env,
                cwd=REPO_ROOT,
                log_path=batch_log,
                dry_run=args.dry_run,
            )
            if eval_code != 0:
                message = f"Batch {batch.index} evaluation failed (exit code={eval_code})"
                print(message)
                if not args.continue_on_error:
                    raise RuntimeError(message)
                continue

        batch_train_patients = _count_ids(batch.train_patient_ids)
        cumulative_train_patients += batch_train_patients

        if args.dry_run and summary is None:
            summary = {
                "diagnosis_accuracy": 0.0,
                "examination_precision": 0.0,
                "treatment_matching_score": 0.0,
                "total_input_tokens": 0,
            }
        elif summary is None:
            summary = _extract_summary(eval_report)

        result = {
            "batch_index": batch.index,
            "batch_train_patients": batch_train_patients,
            "cumulative_train_patients": cumulative_train_patients,
            "test_patients": test_patients_count,
            "diagnosis_accuracy": float(summary.get("diagnosis_accuracy", 0.0)),
            "examination_precision": float(summary.get("examination_precision", 0.0)),
            "treatment_matching_score": float(summary.get("treatment_matching_score", 0.0)),
            "total_input_tokens": int(summary.get("total_input_tokens", 0)),
            "paths": {
                "batch_dir": str(batch.batch_dir),
                "train_trajectory": str(train_trajectory),
                "test_trajectory": str(test_trajectory),
                "eval_report": str(eval_report),
                "commands_log": str(batch_log),
                "train_event_log_dir": str(train_event_log_dir),
                "test_event_log_dir": str(test_event_log_dir),
                "train_debug_prompt_dir": str(train_prompt_dir),
                "val_debug_prompt_dir": str(val_prompt_dir),
            },
            "finished_at": datetime.now().isoformat(),
        }

        state_results = state.get("results", [])
        if not isinstance(state_results, list):
            state_results = []
        state_results.append(result)
        state["results"] = state_results

        state_completed = state.get("completed_batches", [])
        if not isinstance(state_completed, list):
            state_completed = []
        state_completed.append(batch.index)
        state["completed_batches"] = sorted(set(int(i) for i in state_completed))
        state["updated_at"] = datetime.now().isoformat()

        _write_json(state_path, state)
        _append_metrics_csv(metrics_csv_path, result)
        _print_batch_summary(result)

    print("\nRun complete")
    print(f"- Experiment dir: {experiment_dir}")
    print(f"- State: {state_path}")
    print(f"- Metrics CSV: {metrics_csv_path}")


if __name__ == "__main__":
    main()
