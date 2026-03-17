#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$BASELINE_DIR/.." && pwd)"
FRONTEND_DIR="$BASELINE_DIR/frontend"
BACKEND_PORT=8000
FRONTEND_PORT=3000
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_info() { echo -e "${BLUE}[i]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }

ensure_frontend_deps() {
    if [ ! -d "node_modules" ]; then
        print_warning "node_modules not found, running npm install..."
        npm install || {
            print_error "npm install failed"
            exit 1
        }
    fi
}
LOG_DIR=""

for arg in "$@"; do
    if [ -z "$LOG_DIR" ] && [ -d "$arg" ]; then
        LOG_DIR="$(cd "$arg" && pwd)"
    fi
done
if [ -z "$LOG_DIR" ]; then
    LOG_DIR="$BASELINE_DIR/decoupling_output"
fi
if [ -d "$LOG_DIR" ]; then
    LOG_DIR="$(cd "$LOG_DIR" && pwd)"
fi

echo ""
echo "========================================"
echo "  Hospital Simulation - OFFLINE MODE"
echo "========================================"
echo ""
if [ ! -d "$LOG_DIR" ]; then
    print_error "Log directory not found: $LOG_DIR"
    echo ""
    echo "Usage: $0 [LOG_DIRECTORY]"
    echo ""
    echo "Examples:"
    echo "  $0                                      # Use default: ./decoupling_output"
    echo "  $0 /path/to/simulation/output           # Use custom directory"
    echo ""
    echo "Make sure you have run the simulation first:"
    echo "  python -m baseline.run_simulation"
    exit 1
fi
EVENT_FILES=$(find "$LOG_DIR" -name "events_tick_*.log" 2>/dev/null | head -5)
if [ -z "$EVENT_FILES" ]; then
    print_error "No events_tick_*.log files found in: $LOG_DIR"
    echo ""
    echo "This directory doesn't appear to contain simulation output."
    echo "Please run the simulation first or specify the correct directory."
    exit 1
fi

print_info "Using log directory: $LOG_DIR"
EVENT_COUNT=$(find "$LOG_DIR" -name "events_tick_*.log" 2>/dev/null | wc -l)
print_status "Found $EVENT_COUNT event files"
echo ""
kill_port() {
    local port=$1
    local pids=$(lsof -t -i :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        print_status "Killed processes on port $port"
    fi
}
CLEANUP_DONE=0
cleanup() {
    if [ "$CLEANUP_DONE" -eq 1 ]; then return; fi
    CLEANUP_DONE=1
    echo ""
    print_warning "Stopping services..."
    kill_port $BACKEND_PORT
    kill_port $FRONTEND_PORT
    print_status "Services stopped"
}
trap 'cleanup; exit 0' SIGINT SIGTERM
echo "Step 1: Cleaning up ports..."
kill_port $BACKEND_PORT
kill_port $FRONTEND_PORT
sleep 1
echo ""
echo "Step 2: Starting Frontend..."
if lsof -t -i :$FRONTEND_PORT >/dev/null 2>&1; then
    print_status "Frontend is already running on port $FRONTEND_PORT"
else
    cd "$FRONTEND_DIR"
    ensure_frontend_deps
    export VITE_BACKEND_URL="http://localhost:$BACKEND_PORT"

    nohup npm run dev > "$BASELINE_DIR/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    sleep 2

    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        print_status "Frontend started (PID: $FRONTEND_PID, Port: $FRONTEND_PORT)"
    else
        print_error "Frontend failed to start, check $BASELINE_DIR/frontend.log"
        exit 1
    fi
fi
echo ""
echo "Step 3: Starting Backend API server..."
cd "$PROJECT_ROOT"
if command -v conda &> /dev/null; then
    if [ -z "$CONDA_DEFAULT_ENV" ]; then
        eval "$(conda shell.bash hook)" 2>/dev/null || true
        conda activate benchmark 2>/dev/null || true
    fi
fi

echo ""
echo "========================================"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend:  http://localhost:$BACKEND_PORT"
echo "  Data:     $LOG_DIR"
echo ""
echo "  Mode:     OFFLINE (no Redis required)"
echo ""
echo "  Press Ctrl+C to stop"
echo "========================================"
echo ""
export MAS_EVENT_LOG_DIR="$LOG_DIR"
if [ -z "$HOSPITAL_EVAL_CACHE_MAX_SIZE" ]; then
    export HOSPITAL_EVAL_CACHE_MAX_SIZE="50000"
fi
python -c "
import uvicorn
uvicorn.run(
    'baseline.backend.main:app',
    host='0.0.0.0',
    port=$BACKEND_PORT,
    log_level='info',
)
"
