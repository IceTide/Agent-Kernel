"""Hospital Simulation Backend API main entry point."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .services import ws_manager, get_event_store
from .routers import (
    doctor_router,
    patient_router,
    conversation_router,
    simulation_router,
)
from .routers.websocket import router as websocket_router, redis_listener
from .routers.real_time_evaluator import start_real_time_evaluation, stop_real_time_evaluation
_redis_listener_task = None
_evaluator_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _redis_listener_task, _evaluator_task
    print("Starting Hospital Simulation Backend API...")
    store = get_event_store()
    log_dir = os.environ.get("MAS_EVENT_LOG_DIR")
    enable_local_write = False

    if not log_dir:
        default_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "decoupling_output")
        os.makedirs(default_log_dir, exist_ok=True)
        if os.path.isdir(default_log_dir):
            log_dir = default_log_dir
            enable_local_write = True
    resume_mode = False
    if log_dir and os.path.isdir(log_dir):
        import glob
        tick_events_dir = os.path.join(log_dir, "tick_events")
        event_files = glob.glob(os.path.join(tick_events_dir, "events_tick_*.log"))
        if not event_files:
            event_files = glob.glob(os.path.join(log_dir, "events_tick_*.log"))
        if event_files:
            resume_mode = True
            print(f"[Backend] Detected {len(event_files)} historical event files, enabling resume mode")

        store.set_log_dir(log_dir, resume_mode=resume_mode, enable_local_write=enable_local_write)
        print(f"EventStore log directory: {log_dir} (resume_mode={resume_mode}, local_write={enable_local_write})")
    _redis_listener_task = asyncio.create_task(redis_listener())
    print(f"Redis event listener started (Redis: {settings.redis_host}:{settings.redis_port})")
    await start_real_time_evaluation()
    print("Real-time evaluation started")

    yield
    print("Shutting down...")
    await stop_real_time_evaluation()
    print("Real-time evaluation stopped")
    if _redis_listener_task:
        _redis_listener_task.cancel()
        try:
            await _redis_listener_task
        except asyncio.CancelledError:
            pass
        print("Redis listener stopped")
app = FastAPI(
    title="Hospital Simulation API",
    description="Backend API for Hospital Simulation frontend - Event-driven architecture",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + ["*"],                     
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(doctor_router)
app.include_router(patient_router)
app.include_router(conversation_router)
app.include_router(simulation_router)
app.include_router(websocket_router)


@app.get("/", summary="API根路径")
async def root():
    """返回API基本信息。"""
    store = get_event_store()
    return {
        "name": "Hospital Simulation API",
        "version": "2.0.0",
        "status": "running",
        "architecture": "event-driven",
        "simulation": store.get_simulation_status(),
    }


@app.get("/health", summary="健康检查")
async def health_check():
    """健康检查端点。"""
    return {"status": "healthy"}


def run_server():
    """Run the server using uvicorn (for development)."""
    import uvicorn

    uvicorn.run(
        "baseline.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )


def start_server(config: dict) -> None:
    """
    Launch the FastAPI server with the provided configuration.

    This function is designed to be called from run_simulation.py as a
    replacement for agentkernel_distributed.mas.interface.server.start_server.

    Args:
        config: Settings dictionary containing host, port, and Redis details.
            Expected keys:
            - host: Server bind address (default: "0.0.0.0")
            - port: Server port (default: 8000)
            - redis_settings: Dict with Redis connection settings
    """
    import uvicorn
    redis_settings = config.get("redis_settings", {})
    if redis_settings:
        os.environ["HOSPITAL_API_REDIS_HOST"] = str(redis_settings.get("host", "localhost"))
        os.environ["HOSPITAL_API_REDIS_PORT"] = str(redis_settings.get("port", 6379))
        os.environ["HOSPITAL_API_REDIS_DB"] = str(redis_settings.get("db", 0))
        if redis_settings.get("password"):
            os.environ["HOSPITAL_API_REDIS_PASSWORD"] = redis_settings["password"]

    host = config.get("host", "0.0.0.0")
    port = config.get("port", 8000)

    print(f"Starting Hospital Simulation Backend API on {host}:{port}")
    print(f"Redis: {redis_settings.get('host', 'localhost')}:{redis_settings.get('port', 6379)}")
    print(f"Event Log Dir: {os.environ.get('MAS_EVENT_LOG_DIR', 'Not set')}")

    uvicorn.run(
        "baseline.backend.main:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
