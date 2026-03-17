#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$BASELINE_DIR/.." && pwd)"

MODE="${1:-fresh}"
if [[ "$MODE" != "fresh" && "$MODE" != "resume" ]]; then
  echo "[✗] Invalid mode: $MODE (expected: fresh | resume)"
  exit 1
fi
EXPERIMENT_NAME="${EXPERIMENT_NAME:-longrun_001}"
SPLIT_DIR="${SPLIT_DIR:-$PROJECT_ROOT/.private_data/splits}"
EXPERIMENT_DIR="${EXPERIMENT_DIR:-$BASELINE_DIR/experiments/runs/$EXPERIMENT_NAME}"
REFLECTION_NAMESPACE="${REFLECTION_NAMESPACE:-$EXPERIMENT_NAME}"

START_BATCH="${START_BATCH:-1}"
END_BATCH="${END_BATCH:-}"

PRECOMPUTED_TREATMENT_EVAL="${PRECOMPUTED_TREATMENT_EVAL:-}"
NO_LLM_FALLBACK="${NO_LLM_FALLBACK:-0}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-0}"
QUIET_EVAL="${QUIET_EVAL:-0}"
EVAL_CONFIG="${EVAL_CONFIG:-}"
EVAL_MAX_CONCURRENCY="${EVAL_MAX_CONCURRENCY:-}"
DRY_RUN="${DRY_RUN:-0}"
CLEAN_PORTS="${CLEAN_PORTS:-1}"
CLEAN_RAY="${CLEAN_RAY:-1}"
CLEAN_EXPERIMENT="${CLEAN_EXPERIMENT:-1}"
CLEAN_REFLECTION="${CLEAN_REFLECTION:-1}"
CLEAN_DEBUG_PROMPTS="${CLEAN_DEBUG_PROMPTS:-1}"
CLEAN_REDIS="${CLEAN_REDIS:-}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DB_KV="${REDIS_DB_KV:-0}"
REDIS_DB_GRAPH="${REDIS_DB_GRAPH:-1}"

if [[ -z "$CLEAN_REDIS" ]]; then
  if [[ "$MODE" == "fresh" ]]; then
    CLEAN_REDIS=1
  else
    CLEAN_REDIS=0
  fi
fi

if [[ "$MODE" == "resume" ]]; then
  CLEAN_EXPERIMENT=0
  CLEAN_REFLECTION=0
  CLEAN_DEBUG_PROMPTS=0
fi
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_info() { echo -e "${BLUE}[i]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -t -i :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
    print_status "Killed processes on port $port"
  fi
}

cleanup_before_run() {
  if [[ "$CLEAN_PORTS" == "1" ]]; then
    print_info "Cleaning ports (8000/3000)..."
    kill_port 8000
    kill_port 3000
  fi

  if [[ "$CLEAN_RAY" == "1" ]]; then
    print_info "Stopping Ray leftovers..."
    if command -v ray >/dev/null 2>&1; then
      ray stop --force >/dev/null 2>&1 || true
    fi
    pkill -f "ray::" 2>/dev/null || true
    print_status "Ray cleanup done"
  fi

  if [[ "$CLEAN_EXPERIMENT" == "1" && -d "$EXPERIMENT_DIR" ]]; then
    print_warning "Removing experiment dir: $EXPERIMENT_DIR"
    rm -rf "$EXPERIMENT_DIR"
  fi

  if [[ "$CLEAN_REFLECTION" == "1" && -d "$EXPERIMENT_DIR/reflection_store" ]]; then
    print_warning "Removing reflection store: $EXPERIMENT_DIR/reflection_store"
    rm -rf "$EXPERIMENT_DIR/reflection_store"
  fi

  if [[ "$CLEAN_DEBUG_PROMPTS" == "1" && -d "$EXPERIMENT_DIR/artifacts" ]]; then
    print_warning "Removing all batch debug prompts under: $EXPERIMENT_DIR/artifacts"
    find "$EXPERIMENT_DIR/artifacts" -type d -name debug_prompts -prune -exec rm -rf {} + 2>/dev/null || true
  fi

  if [[ "$CLEAN_DEBUG_PROMPTS" == "1" && -d "$BASELINE_DIR/debug_prompts" ]]; then
    print_warning "Removing legacy debug prompts: $BASELINE_DIR/debug_prompts"
    rm -rf "$BASELINE_DIR/debug_prompts"
  fi

  if [[ "$CLEAN_REDIS" == "1" ]]; then
    if command -v redis-cli >/dev/null 2>&1; then
      print_warning "Flushing Redis db$REDIS_DB_KV and db$REDIS_DB_GRAPH on ${REDIS_HOST}:${REDIS_PORT}"
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB_KV" FLUSHDB >/dev/null || true
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB_GRAPH" FLUSHDB >/dev/null || true
      print_status "Redis flush complete"
    else
      print_warning "redis-cli not found, skip Redis flush"
    fi
  fi
}

activate_conda_if_needed() {
  if command -v conda >/dev/null 2>&1; then
    if [ -z "${CONDA_DEFAULT_ENV:-}" ]; then
      eval "$(conda shell.bash hook)" 2>/dev/null || true
      conda activate benchmark 2>/dev/null || true
    fi
  fi
}

build_command() {
  local cmd=(
    python
    baseline/scripts/run_batch_train_eval.py
    --split-dir "$SPLIT_DIR"
    --experiment-name "$EXPERIMENT_NAME"
    --reflection-namespace "$REFLECTION_NAMESPACE"
    --start-batch "$START_BATCH"
  )

  if [[ -n "$END_BATCH" ]]; then
    cmd+=(--end-batch "$END_BATCH")
  fi

  if [[ "$MODE" == "resume" ]]; then
    cmd+=(--resume)
  else
    cmd+=(--reset-experiment)
  fi

  if [[ -n "$PRECOMPUTED_TREATMENT_EVAL" ]]; then
    cmd+=(--precomputed-treatment-eval "$PRECOMPUTED_TREATMENT_EVAL")
  fi

  if [[ "$NO_LLM_FALLBACK" == "1" ]]; then
    cmd+=(--no-llm-fallback)
  fi

  if [[ "$CONTINUE_ON_ERROR" == "1" ]]; then
    cmd+=(--continue-on-error)
  fi

  if [[ "$QUIET_EVAL" == "1" ]]; then
    cmd+=(--quiet-eval)
  fi

  if [[ -n "$EVAL_CONFIG" ]]; then
    cmd+=(--eval-config "$EVAL_CONFIG")
  fi

  if [[ -n "$EVAL_MAX_CONCURRENCY" ]]; then
    cmd+=(--eval-max-concurrency "$EVAL_MAX_CONCURRENCY")
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    cmd+=(--dry-run)
  fi

  echo "${cmd[@]}"
}

ensure_prepared_split() {
  local required_paths=(
    "$SPLIT_DIR/manifest.json"
    "$SPLIT_DIR/shared/doctor_profiles.jsonl"
    "$SPLIT_DIR/test/profiles.jsonl"
    "$SPLIT_DIR/test/ground_truth.json"
    "$SPLIT_DIR/test/examination_data.json"
    "$SPLIT_DIR/test/patient_ids.txt"
    "$SPLIT_DIR/train_batches"
  )

  for path in "${required_paths[@]}"; do
    if [[ ! -e "$path" ]]; then
      print_error "Prepared split artifact missing: $path"
      print_info "Generate the split first: python baseline/scripts/patients_data_split.py"
      exit 1
    fi
  done
}

echo ""
echo "========================================"
echo "  Hospital Batch Train+Eval ($MODE)"
echo "========================================"
echo ""
print_info "Experiment: $EXPERIMENT_NAME"
print_info "Split Dir:   $SPLIT_DIR"
print_info "Split mode:  use precomputed split only"
print_info "Batches:     $START_BATCH -> ${END_BATCH:-END}"
echo ""

ensure_prepared_split
cleanup_before_run
activate_conda_if_needed

cd "$PROJECT_ROOT"

CMD_STR=$(build_command)
print_info "Running command:"
echo "  $CMD_STR"
echo ""

set +e
eval "$CMD_STR"
EXIT_CODE=$?
set -e

echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
  print_status "Batch train+eval completed"
  print_info "Results: $EXPERIMENT_DIR"
else
  print_error "Batch train+eval failed (exit code=$EXIT_CODE)"
  print_info "Check logs under: $EXPERIMENT_DIR"
fi

exit $EXIT_CODE
