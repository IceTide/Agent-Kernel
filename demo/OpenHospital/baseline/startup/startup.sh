#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$BASELINE_DIR/.." && pwd)"
FRONTEND_DIR="$BASELINE_DIR/frontend"
LOG_DIR="$BASELINE_DIR/decoupling_output"
LOGS_DIR="$BASELINE_DIR/logs"
DEBUG_PROMPTS_DIR="$BASELINE_DIR/debug_prompts"
BACKEND_PORT=8000
FRONTEND_PORT=3000
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

start_frontend_dev() {
    nohup npm run dev > "$BASELINE_DIR/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    sleep 2

    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        print_status "Frontend started (PID: $FRONTEND_PID, Port: $FRONTEND_PORT)"
    else
        print_error "Frontend failed to start, check $BASELINE_DIR/frontend.log"
        exit 1
    fi
}
kill_port() {
    local port=$1
    local pids=$(lsof -t -i :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        print_status "Killed processes on port $port"
    else
        print_info "Port $port is free"
    fi
}
is_port_in_use() {
    local port=$1
    lsof -t -i :$port >/dev/null 2>&1
    return $?
}
FRONTEND_PID=""
SIMULATION_PID=""
CLEANUP_DONE=0
cleanup() {
    if [ "$CLEANUP_DONE" -eq 1 ]; then
        return
    fi
    CLEANUP_DONE=1

    echo ""
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
    print_info "Frontend is still running at http://localhost:$FRONTEND_PORT"
    print_info "You can resume with: ./startup/startup.sh resume"
    print_info "Or start fresh with: ./startup/startup.sh"
}
trap 'cleanup; exit 0' SIGINT SIGTERM

echo ""
echo "========================================"
if [ "$RESUME_MODE" = true ]; then
    echo "  Hospital Simulation - RESUME MODE"
else
    echo "  Hospital Simulation - FRESH START"
fi
echo "========================================"
echo ""

if [ "$RESUME_MODE" = true ]; then
    print_info "Resume mode: keeping existing logs, Redis data, and frontend"
    echo ""
    if is_port_in_use $FRONTEND_PORT; then
        print_status "Frontend is already running on port $FRONTEND_PORT"
    else
        print_warning "Frontend is not running, starting it..."
        cd "$FRONTEND_DIR"

        ensure_frontend_deps
        start_frontend_dev
    fi
    if is_port_in_use $BACKEND_PORT; then
        print_warning "Backend is running on port $BACKEND_PORT, stopping it..."
        kill_port $BACKEND_PORT
        sleep 1
    fi

else
    echo "Step 1: Cleaning up old processes..."
    kill_port $BACKEND_PORT
    kill_port $FRONTEND_PORT
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
    echo ""
    echo "Step 6: Starting Frontend dev server..."
    cd "$FRONTEND_DIR"

    ensure_frontend_deps
    start_frontend_dev
fi
echo ""
if [ "$RESUME_MODE" = true ]; then
    echo "Resuming simulation from checkpoint..."
else
    echo "Step 7: Running simulation (backend will start automatically)..."
fi
echo ""
echo "========================================"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend:  http://localhost:$BACKEND_PORT (starting with simulation)"
echo ""
echo "  Press Ctrl+C to stop all services"
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
    python -m baseline.run_simulation --resume &
else
    python -m baseline.run_simulation &
fi
SIMULATION_PID=$!
wait $SIMULATION_PID 2>/dev/null
SIMULATION_EXIT_CODE=$?
if [ $SIMULATION_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "========================================"
    print_status "Simulation completed successfully!"
    echo ""
    print_info "Frontend and backend are still running:"
    print_info "  Frontend: http://localhost:$FRONTEND_PORT"
    print_info "  Backend:  http://localhost:$BACKEND_PORT"
    echo ""
    print_info "You can view simulation results in the frontend."
    print_info "To resume: ./startup/startup.sh resume"
    print_info "To start fresh: ./startup/startup.sh"
    print_warning "Press Ctrl+C to stop backend and keep frontend running."
    echo "========================================"
    echo ""
    while true; do
        sleep 1
    done
else
    print_warning "Simulation was interrupted or failed"
    echo ""
    print_info "Frontend is still running at http://localhost:$FRONTEND_PORT"
    print_info "Backend has been stopped"
    echo ""
    print_info "To resume: ./startup/startup.sh resume"
    print_info "To start fresh: ./startup/startup.sh"
    echo ""
fi
