#!/usr/bin/env python3

"""Prepare a patient-only train/test split with optional train batching.

This script is intentionally lightweight:
1. All configuration is managed in the constants below.
2. No command-line arguments are required.
3. It writes patient split artifacts plus the shared doctor profiles needed by batch runs.

Key guarantee:
- The test set is determined only by SPLIT_SEED + TEST_RATIO + source data.
- TRAIN_BATCH_SIZE only affects how the train subset is grouped afterwards.
- Changing TRAIN_BATCH_SIZE will not change which patients belong to test/train.
"""

from __future__ import annotations

import json
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
PATIENT_PROFILES_PATH = REPO_ROOT / "data" / "patients_data" / "profiles.jsonl"
GROUND_TRUTH_PATH = REPO_ROOT / "data" / "patients_data" / "ground_truth.json"
EXAMINATION_DATA_PATH = REPO_ROOT / "data" / "patients_data" / "examination_data.json"
DOCTOR_PROFILES_PATH = REPO_ROOT / "baseline" / "data" / "doctors" / "profiles.jsonl"
PATIENT_ID_WHITELIST: Optional[Path] = None
OUTPUT_DIR = REPO_ROOT / ".private_data" / "splits"
OVERWRITE_OUTPUT = True
TEST_RATIO = 0.1
USE_STRATIFIED_SPLIT = True
SPLIT_SEED = 20260211
TRAIN_BATCH_SIZE: Optional[int] = 500
BATCH_SEED = 20260211


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_id_list(path: Path) -> List[str]:
    ids: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                ids.append(line)
    return ids


def write_id_list(path: Path, ids: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for patient_id in ids:
            f.write(f"{patient_id}\n")


def _normalize_diagnosis_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _extract_final_diagnosis_labels(value: Any) -> List[str]:
    if isinstance(value, list):
        labels = [_normalize_diagnosis_label(item) for item in value]
        return [label for label in labels if label]

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []

        parts = re.split(r"\s*(?:,|，|;|；|、)\s*", raw)
        labels = [_normalize_diagnosis_label(part) for part in parts]
        labels = [label for label in labels if label]
        if labels:
            return labels

        fallback = _normalize_diagnosis_label(raw)
        return [fallback] if fallback else []

    return []


def infer_patient_stratum(patient_id: str, ground_truth: Dict[str, Any]) -> str:
    truth = ground_truth.get(patient_id, {}) if isinstance(ground_truth, dict) else {}
    diagnosis_value = truth.get("final_diagnosis") if isinstance(truth, dict) else None
    labels = _extract_final_diagnosis_labels(diagnosis_value)

    if not labels:
        return "diagnosis|unknown"

    unique_labels = sorted(set(labels))
    if len(unique_labels) == 1:
        return f"diagnosis|single|{unique_labels[0]}"

    combo = " + ".join(unique_labels)
    return f"diagnosis|comorbid|{combo}"


def random_split(patient_ids: List[str], test_ratio: float, seed: int) -> Tuple[List[str], List[str]]:
    if len(patient_ids) <= 1:
        return list(patient_ids), []

    rng = random.Random(seed)
    shuffled = list(patient_ids)
    rng.shuffle(shuffled)

    n_total = len(shuffled)
    n_test = int(round(n_total * test_ratio))
    n_test = max(1, n_test)
    n_test = min(n_test, n_total - 1)

    test_ids = shuffled[:n_test]
    train_ids = shuffled[n_test:]
    return train_ids, test_ids


def stratified_split(
    patient_ids: List[str],
    ground_truth: Dict[str, Any],
    test_ratio: float,
    seed: int,
) -> Tuple[List[str], List[str], Dict[str, int], Dict[str, int]]:
    rng = random.Random(seed)

    stratum_to_ids: Dict[str, List[str]] = {}
    for patient_id in patient_ids:
        key = infer_patient_stratum(patient_id, ground_truth)
        stratum_to_ids.setdefault(key, []).append(patient_id)

    train_ids: List[str] = []
    test_ids: List[str] = []
    strata_counts: Dict[str, int] = {}
    strata_test_counts: Dict[str, int] = {}

    for stratum, ids in sorted(stratum_to_ids.items()):
        ids_local = list(ids)
        rng.shuffle(ids_local)
        n = len(ids_local)
        strata_counts[stratum] = n

        if n <= 1:
            n_test = 0
        else:
            n_test = int(round(n * test_ratio))
            n_test = max(1, n_test) if n >= 5 else n_test
            n_test = min(n_test, n - 1)

        strata_test_counts[stratum] = n_test

        test_part = ids_local[:n_test]
        train_part = ids_local[n_test:]
        test_ids.extend(test_part)
        train_ids.extend(train_part)

    if not test_ids:
        train_ids, test_ids = random_split(patient_ids, test_ratio, seed)
        strata_counts = {"fallback_random": len(patient_ids)}
        strata_test_counts = {"fallback_random": len(test_ids)}
        return train_ids, test_ids, strata_counts, strata_test_counts

    rng.shuffle(train_ids)
    rng.shuffle(test_ids)
    return train_ids, test_ids, strata_counts, strata_test_counts


def build_stratified_balanced_batches(
    train_ids: List[str],
    ground_truth: Dict[str, Any],
    batch_size: int,
    seed: int,
) -> List[List[str]]:
    if not train_ids:
        return []

    rng = random.Random(seed)
    n_batches = max(1, (len(train_ids) + batch_size - 1) // batch_size)

    stratum_to_ids: Dict[str, List[str]] = defaultdict(list)
    for patient_id in train_ids:
        stratum = infer_patient_stratum(patient_id, ground_truth)
        stratum_to_ids[stratum].append(patient_id)

    for ids in stratum_to_ids.values():
        rng.shuffle(ids)

    batches: List[List[str]] = [[] for _ in range(n_batches)]

    batch_index = 0
    for ids in (stratum_to_ids[key] for key in sorted(stratum_to_ids)):
        for patient_id in ids:
            attempts = 0
            while attempts < n_batches and len(batches[batch_index]) >= batch_size:
                batch_index = (batch_index + 1) % n_batches
                attempts += 1

            batches[batch_index].append(patient_id)
            batch_index = (batch_index + 1) % n_batches

    non_empty = [batch for batch in batches if batch]
    for batch in non_empty:
        rng.shuffle(batch)
    return non_empty


def compute_batch_diversity(
    train_batches: List[List[str]],
    ground_truth: Dict[str, Any],
) -> List[Dict[str, Any]]:
    stats: List[Dict[str, Any]] = []
    for idx, batch_ids in enumerate(train_batches, start=1):
        stratum_counter = Counter(infer_patient_stratum(pid, ground_truth) for pid in batch_ids)
        total = len(batch_ids)
        top_items = stratum_counter.most_common(5)
        stats.append(
            {
                "batch_index": idx,
                "size": total,
                "unique_disease_groups": len(stratum_counter),
                "top_disease_groups": [{"group": key, "count": count} for key, count in top_items],
            }
        )
    return stats


def filter_profiles_by_ids(
    profiles: List[Dict[str, Any]],
    ids: List[str],
) -> List[Dict[str, Any]]:
    profile_map = {row.get("id"): row for row in profiles if isinstance(row, dict) and row.get("id")}
    filtered: List[Dict[str, Any]] = []
    for patient_id in ids:
        row = profile_map.get(patient_id)
        if row is not None:
            filtered.append(row)
    return filtered


def filter_dict_by_ids(data: Dict[str, Any], ids: List[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for patient_id in ids:
        if patient_id in data:
            result[patient_id] = data[patient_id]
    return result


def validate_ids(
    profiles: List[Dict[str, Any]],
    ground_truth: Dict[str, Any],
    examination_data: Dict[str, Any],
    explicit_id_file: Path | None,
) -> List[str]:
    profile_ids = [row.get("id") for row in profiles if isinstance(row, dict) and row.get("id")]

    if explicit_id_file:
        raw_ids = read_id_list(explicit_id_file)
        id_set = set(raw_ids)
        profile_ids = [pid for pid in profile_ids if pid in id_set]

    filtered_ids = [pid for pid in profile_ids if pid in ground_truth and pid in examination_data]
    if not filtered_ids:
        raise ValueError("No valid patient IDs after filtering with ground truth and examination data")
    return filtered_ids


def write_subset(
    output_dir: Path,
    ids: List[str],
    profiles: List[Dict[str, Any]],
    ground_truth: Dict[str, Any],
    examination_data: Dict[str, Any],
) -> None:
    subset_profiles = filter_profiles_by_ids(profiles, ids)
    subset_ground_truth = filter_dict_by_ids(ground_truth, ids)
    subset_exam = filter_dict_by_ids(examination_data, ids)

    write_jsonl(output_dir / "profiles.jsonl", subset_profiles)
    write_json(output_dir / "ground_truth.json", subset_ground_truth)
    write_json(output_dir / "examination_data.json", subset_exam)
    write_id_list(output_dir / "patient_ids.txt", ids)


def _validate_config() -> None:
    if not (0.0 < TEST_RATIO < 1.0):
        raise ValueError("TEST_RATIO must be in (0, 1)")

    if TRAIN_BATCH_SIZE is not None and TRAIN_BATCH_SIZE <= 0:
        raise ValueError("TRAIN_BATCH_SIZE must be positive or None")

    required_paths = [
        PATIENT_PROFILES_PATH,
        GROUND_TRUTH_PATH,
        EXAMINATION_DATA_PATH,
        DOCTOR_PROFILES_PATH,
    ]
    for path in required_paths:
        if not path.exists():
            raise FileNotFoundError(f"Required input file not found: {path}")

    if PATIENT_ID_WHITELIST is not None and not PATIENT_ID_WHITELIST.exists():
        raise FileNotFoundError(f"PATIENT_ID_WHITELIST not found: {PATIENT_ID_WHITELIST}")


def _prepare_output_dir() -> None:
    if OUTPUT_DIR.exists():
        if not OVERWRITE_OUTPUT:
            raise FileExistsError(f"Output dir already exists: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _build_manifest(
    train_ids: List[str],
    test_ids: List[str],
    train_batches: List[List[str]],
    strata_counts: Dict[str, int],
    strata_test_counts: Dict[str, int],
    batch_diversity: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "split_type": "patient_only",
        "seed": SPLIT_SEED,
        "batch_seed": BATCH_SEED if TRAIN_BATCH_SIZE is not None else None,
        "test_ratio": TEST_RATIO,
        "stratified_split": 1 if USE_STRATIFIED_SPLIT else 0,
        "split_strategy": "diagnosis_stratified" if USE_STRATIFIED_SPLIT else "global_random",
        "batch_size": TRAIN_BATCH_SIZE,
        "total_patients": len(train_ids) + len(test_ids),
        "train_count": len(train_ids),
        "test_count": len(test_ids),
        "train_batch_count": len(train_batches),
        "train_ids_file": "train/patient_ids.txt",
        "test_ids_file": "test/patient_ids.txt",
        "train_batches_dir": "train_batches" if train_batches else None,
        "doctor_profiles": "shared/doctor_profiles.jsonl",
        "strata_counts": strata_counts,
        "strata_test_counts": strata_test_counts,
        "batch_diversity": batch_diversity,
        "source_paths": {
            "patient_profiles": str(PATIENT_PROFILES_PATH),
            "doctor_profiles": str(DOCTOR_PROFILES_PATH),
            "ground_truth": str(GROUND_TRUTH_PATH),
            "examination_data": str(EXAMINATION_DATA_PATH),
            "patient_ids": str(PATIENT_ID_WHITELIST) if PATIENT_ID_WHITELIST else None,
        },
    }


def main() -> None:
    _validate_config()

    patient_profiles = load_jsonl(PATIENT_PROFILES_PATH)
    ground_truth = load_json(GROUND_TRUTH_PATH)
    examination_data = load_json(EXAMINATION_DATA_PATH)

    patient_ids = validate_ids(
        profiles=patient_profiles,
        ground_truth=ground_truth,
        examination_data=examination_data,
        explicit_id_file=PATIENT_ID_WHITELIST,
    )

    if USE_STRATIFIED_SPLIT:
        train_ids, test_ids, strata_counts, strata_test_counts = stratified_split(
            patient_ids=patient_ids,
            ground_truth=ground_truth,
            test_ratio=TEST_RATIO,
            seed=SPLIT_SEED,
        )
    else:
        train_ids, test_ids = random_split(
            patient_ids=patient_ids,
            test_ratio=TEST_RATIO,
            seed=SPLIT_SEED,
        )
        strata_counts = {"global_random": len(patient_ids)}
        strata_test_counts = {"global_random": len(test_ids)}

    if not train_ids:
        raise ValueError("Generated empty train set; decrease TEST_RATIO or increase data size")
    if not test_ids:
        raise ValueError("Generated empty test set; increase TEST_RATIO or increase data size")

    train_batches: List[List[str]] = []
    batch_diversity: List[Dict[str, Any]] = []
    if TRAIN_BATCH_SIZE is not None:
        train_batches = build_stratified_balanced_batches(
            train_ids=train_ids,
            ground_truth=ground_truth,
            batch_size=TRAIN_BATCH_SIZE,
            seed=BATCH_SEED,
        )
        if not train_batches:
            raise ValueError("No train batches generated")
        batch_diversity = compute_batch_diversity(train_batches, ground_truth)

    _prepare_output_dir()

    write_subset(OUTPUT_DIR / "train", train_ids, patient_profiles, ground_truth, examination_data)
    write_subset(OUTPUT_DIR / "test", test_ids, patient_profiles, ground_truth, examination_data)

    if train_batches:
        batches_dir = OUTPUT_DIR / "train_batches"
        for idx, batch_ids in enumerate(train_batches, start=1):
            batch_dir = batches_dir / f"batch_{idx:04d}"
            write_subset(batch_dir, batch_ids, patient_profiles, ground_truth, examination_data)

    shared_dir = OUTPUT_DIR / "shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOCTOR_PROFILES_PATH, shared_dir / "doctor_profiles.jsonl")

    manifest = _build_manifest(
        train_ids=train_ids,
        test_ids=test_ids,
        train_batches=train_batches,
        strata_counts=strata_counts,
        strata_test_counts=strata_test_counts,
        batch_diversity=batch_diversity,
    )
    write_json(OUTPUT_DIR / "manifest.json", manifest)

    print("Patient-only split prepared successfully")
    print(f"- Output Dir: {OUTPUT_DIR}")
    print(f"- Train Patients: {len(train_ids)}")
    print(f"- Test Patients: {len(test_ids)}")
    print(f"- Split Seed: {SPLIT_SEED}")
    print(f"- Test Ratio: {TEST_RATIO}")
    print(f"- Stratified Split: {1 if USE_STRATIFIED_SPLIT else 0}")
    if TRAIN_BATCH_SIZE is None:
        print("- Train Batches: disabled")
    else:
        print(f"- Train Batches: {len(train_batches)}")
        print(f"- Train Batch Size: {TRAIN_BATCH_SIZE}")
        print(f"- Batch Seed: {BATCH_SEED}")


if __name__ == "__main__":
    main()
