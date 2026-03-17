#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$BASELINE_DIR/.." && pwd)"
LOG_DIR="$BASELINE_DIR/decoupling_output"
LOGS_DIR="$BASELINE_DIR/logs"
DEBUG_PROMPTS_DIR="$BASELINE_DIR/debug_prompts"
BACKEND_PORT=8000
RESUME_MODE=false
if [ "$1" = "resume" ]; then
    RESUME_MODE=true
fi
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_info() { echo -e "${BLUE}[i]${NC} $1"; }
kill_port() {
    local port=$1
    local pids=$(lsof -t -i :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        print_status "Killed processes on port $port"
    fi
}

SIMULATION_PID=""
CLEANUP_DONE=0

cleanup() {
    if [ "$CLEANUP_DONE" -eq 1 ]; then return; fi
    CLEANUP_DONE=1

    echo ""
    print_warning "Stopping simulation..."

    if [ -n "$SIMULATION_PID" ] && kill -0 $SIMULATION_PID 2>/dev/null; then
        kill -TERM $SIMULATION_PID 2>/dev/null || true
        sleep 1
        kill -0 $SIMULATION_PID 2>/dev/null && kill -9 $SIMULATION_PID 2>/dev/null || true
    fi

    kill_port $BACKEND_PORT
    pkill -f "ray::" 2>/dev/null || true

    print_status "Simulation stopped"
    echo ""
    print_info "To view results:  ./startup/startup_frontend.sh"
    print_info "To resume:        ./startup/startup_backend.sh resume"
    print_info "To start fresh:   ./startup/startup_backend.sh"
}

trap 'cleanup; exit 0' SIGINT SIGTERM

echo ""
echo "========================================"
if [ "$RESUME_MODE" = true ]; then
    echo "  Hospital Simulation - RESUME (simulation only)"
else
    echo "  Hospital Simulation - FRESH START (simulation only)"
fi
echo "========================================"
echo ""

if [ "$RESUME_MODE" = true ]; then
    print_info "Resume mode: keeping existing logs and Redis data"
    echo ""
    kill_port $BACKEND_PORT
    sleep 1
else
    echo "Step 1: Cleaning up..."
    kill_port $BACKEND_PORT
    sleep 1
    echo ""
    echo "Step 2: Clearing old log files..."
    mkdir -p "$LOG_DIR"
    rm -f "$LOG_DIR"/*.jsonl "$LOG_DIR"/*.json "$LOG_DIR"/events_tick_*.log 2>/dev/null || true
    print_status "Old log files cleared"
    echo ""
    echo "Step 3: Clearing logs directory..."
    if [ -d "$LOGS_DIR" ]; then
        rm -rf "$LOGS_DIR"/* 2>/dev/null || true
        print_status "Logs directory cleared"
    else
        print_info "Logs directory does not exist, skipping"
    fi
    echo ""
    echo "Step 4: Clearing debug prompts..."
    rm -rf "$DEBUG_PROMPTS_DIR" 2>/dev/null || true
    print_status "Debug prompts cleared"
    echo ""
    echo "Step 5: Clearing Redis..."
    if command -v redis-cli &> /dev/null; then
        redis-cli FLUSHDB > /dev/null 2>&1 && print_status "Redis cleared" || print_warning "Failed to clear Redis"
    else
        print_warning "redis-cli not found, skipping Redis clear"
    fi
fi
echo ""
if [ "$RESUME_MODE" = true ]; then
    echo "Resuming simulation from checkpoint..."
else
    echo "Step 6: Running simulation..."
fi
echo ""
echo "========================================"
echo "  Mode: Simulation Only (no frontend/backend)"
echo ""
echo "  Press Ctrl+C to stop"
echo "========================================"
echo ""

cd "$PROJECT_ROOT"
if command -v conda &> /dev/null; then
    if [ -z "$CONDA_DEFAULT_ENV" ]; then
        eval "$(conda shell.bash hook)" 2>/dev/null || true
        conda activate benchmark 2>/dev/null || true
    fi
fi

if [ "$RESUME_MODE" = true ]; then
    python -m baseline.run_simulation --resume --skip-api-server &
else
    python -m baseline.run_simulation --skip-api-server &
fi
SIMULATION_PID=$!

wait $SIMULATION_PID 2>/dev/null
SIMULATION_EXIT_CODE=$?

if [ $SIMULATION_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "========================================"
    print_status "Simulation completed successfully!"
    echo ""
    print_info "JSONL output: $LOG_DIR"
    print_info "To view results: ./startup/startup_frontend.sh"
    echo "========================================"
    echo ""
else
    echo ""
    print_warning "Simulation was interrupted or failed"
    echo ""
    print_info "To view partial results: ./startup/startup_frontend.sh"
    print_info "To resume:               ./startup/startup_backend.sh resume"
    print_info "To start fresh:          ./startup/startup_backend.sh"
    echo ""
fi
