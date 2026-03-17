"""
Hospital Simulation Runner.
Run with:
  python -m baseline.run_simulation           # Fresh start
  python -m baseline.run_simulation --resume  # Resume from checkpoint
"""

import os
import sys
import asyncio
import time
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Set, Optional

import yaml

os.environ["MAS_LOG_LEVEL"] = "INFO"                                    
os.environ["MAS_SAVE_PROMPT"]= "0"                                                           
project_path = os.path.dirname(os.path.abspath(__file__))
if "MAS_PROJECT_ABS_PATH" not in os.environ:
    os.environ["MAS_PROJECT_ABS_PATH"] = project_path

if "MAS_PROJECT_REL_PATH" not in os.environ:
    os.environ["MAS_PROJECT_REL_PATH"] = "baseline"

import multiprocessing

import ray
from agentkernel_distributed.mas.builder import Builder
from baseline.backend.main import start_server
from baseline.registry import RESOURCE_MAPS
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.toolkit.storages.graph_adapters.redis import RedisGraphAdapter

from baseline.utils.file_event_logger import file_event_logger
from baseline.utils.ray_runtime import build_ray_runtime_env

logger = get_logger(__name__)


def _load_data_file(file_path: Path) -> Any:
    """Load a data file by extension."""
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    if suffix in {".yaml", ".yml"}:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    if suffix == ".jsonl":
        rows = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows
    raise ValueError(f"Unsupported data file type: {file_path}")


def _normalize_loaded_data(data: Any) -> Any:
    """Normalize loaded data structure to framework expectations."""
    if (
        isinstance(data, list)
        and all(isinstance(entry, dict) for entry in data)
        and all("id" in entry for entry in data)
    ):
        return {entry["id"]: entry for entry in data}
    return data


def _resolve_data_path(base_project_path: str, raw_path: str) -> Path:
    """Resolve path string to an absolute path."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(base_project_path) / raw_path
    return path


def _resolve_optional_input_path(base_project_path: str, raw_path: Any) -> Optional[str]:
    """Resolve an optional path argument to absolute string."""
    if not raw_path:
        return None
    return str(_resolve_data_path(base_project_path, str(raw_path)))


def _apply_data_overrides_to_builder(sim_builder: Builder, data_overrides: Dict[str, str]) -> None:
    """Apply runtime data path overrides and reload loaded_data for builder."""
    overridden_keys: Set[str] = set()

    for data_key, override_path in data_overrides.items():
        if not override_path:
            continue
        setattr(sim_builder.config.data, data_key, override_path)
        overridden_keys.add(data_key)
        logger.info("Data override applied: %s -> %s", data_key, override_path)

    data_paths = sim_builder.config.data.model_dump() if hasattr(sim_builder.config.data, "model_dump") else {}
    loaded_data: Dict[str, Any] = {}

    for data_key, raw_path in data_paths.items():
        if not isinstance(raw_path, str):
            continue
        full_path = _resolve_data_path(project_path, raw_path)
        if not full_path.exists():
            raise FileNotFoundError(f"Data file for '{data_key}' not found at: {full_path}")

        data = _load_data_file(full_path)
        loaded_data[data_key] = _normalize_loaded_data(data)

    sim_builder.config.loaded_data = loaded_data
    logger.info("Reloaded builder loaded_data with %d sources", len(loaded_data))
    templates_config = getattr(sim_builder.config, "agent_templates", None)
    if not templates_config or not getattr(templates_config, "templates", None):
        return

    for template in templates_config.templates:
        profile_component = template.components.get("profile") if template.components else None
        if not profile_component or not profile_component.plugin:
            continue

        _, plugin_obj = next(iter(profile_component.plugin.items()))
        profile_data_key = plugin_obj.model_dump().get("profile_data")
        if not isinstance(profile_data_key, str):
            continue
        if profile_data_key not in overridden_keys:
            continue

        profiles = loaded_data.get(profile_data_key)
        if isinstance(profiles, dict):
            template.agents = sorted(profiles.keys())
            logger.info(
                "Refreshed template '%s' agents from '%s' (%d ids)",
                template.name,
                profile_data_key,
                len(template.agents),
            )
        else:
            logger.warning(
                "Could not refresh template '%s' agents: '%s' is not a dict in loaded_data",
                template.name,
                profile_data_key,
            )


async def get_redis_adapter(project_path: str):
    """Create and connect a Redis adapter using config."""
    db_config_path = Path(project_path) / "configs" / "db_config.yaml"
    if not db_config_path.exists():
        logger.warning(f"Database config not found: {db_config_path}")
        return None

    with open(db_config_path, "r", encoding="utf-8") as f:
        db_config = yaml.safe_load(f)

    redis_pool_config = db_config.get("pools", {}).get("default_redis", {})
    redis_settings = redis_pool_config.get("settings", {})

    redis = RedisKVAdapter(
        host=redis_settings.get("host", "localhost"),
        port=redis_settings.get("port", 6379),
        db=redis_settings.get("db", 0),
    )
    await redis.connect(config=redis_settings)
    return redis


async def load_catalogs_to_redis(redis, project_path: str):
    """Load medical catalogs (examinations, diseases) to Redis.

    Args:
        redis: Connected Redis adapter
        project_path: Project root path
    """
    catalogs_dir = Path(project_path) / "data" / "catalogs"
    normal_exam_files = {
        "adolescent": "examinations_normal_adolescent.json",
        "adult": "examinations_normal_adult.json",
        "child": "examinations_normal_child.json",
        "elderly": "examinations_normal_elderly.json",
        "infant": "examinations_normal_infant.json",
    }
    total_loaded = 0
    for age_group, filename in normal_exam_files.items():
        normal_path = catalogs_dir / filename
        if not normal_path.exists():
            logger.warning(f"Normal examinations not found: {normal_path}")
            continue

        with open(normal_path, "r", encoding="utf-8") as f:
            normal_data = json.load(f)

        for item in normal_data.get("results", []):
            exam_name = item.get("item_name", "")
            if not exam_name:
                continue
            male_key = f"hospital:normal_examination:{age_group}:male:{exam_name}"
            female_key = f"hospital:normal_examination:{age_group}:female:{exam_name}"
            await redis.set(male_key, item.get("male_result"))
            await redis.set(female_key, item.get("female_result"))
            total_loaded += 2

        logger.info(f"Loaded normal examinations for {age_group}")
    departments_path = catalogs_dir / "departments.json"
    if departments_path.exists():
        with open(departments_path, "r", encoding="utf-8") as f:
            departments_data = json.load(f)

        departments_list = departments_data.get("departments", [])
        await redis.set("hospital:departments", departments_list)
        logger.info(f"Loaded {len(departments_list)} departments to Redis")
    else:
        logger.warning(f"Departments catalog not found: {departments_path}")
    diseases_path = catalogs_dir / "diseases_catalog.json"
    if diseases_path.exists():
        with open(diseases_path, "r", encoding="utf-8") as f:
            diseases_data = json.load(f)

        dept_count = 0
        for category in diseases_data.get("diseases", []):
            dept_name = category.get("category", "")
            if not dept_name:
                continue
            redis_key = f"hospital:diseases:{dept_name}"
            await redis.set(redis_key, category.get("items", []))
            dept_count += 1

        logger.info(f"Loaded diseases for {dept_count} departments to Redis")
    else:
        logger.warning(f"Diseases catalog not found: {diseases_path}")


async def load_data_to_redis(project_path: str, data_config: Dict[str, str], resume: bool = False):
    """Load all simulation data to Redis for shared access across pods.

    Args:
        project_path: Project root path for resolving relative paths
        data_config: Data paths configuration from simulation_config.yaml
        resume: If True, skip clearing Redis (for checkpoint resume)
    """
    redis = None
    redis_graph = None
    try:
        redis = await get_redis_adapter(project_path)
        db_config_path = Path(project_path) / "configs" / "db_config.yaml"
        with open(db_config_path, "r", encoding="utf-8") as f:
            db_config = yaml.safe_load(f)
        graph_pool_config = db_config.get("pools", {}).get("default_graph", {})
        graph_settings = graph_pool_config.get("settings", {})
        if not graph_settings:
            logger.warning("default_graph pool not found in db_config.yaml, falling back to default_redis")
            graph_pool_config = db_config.get("pools", {}).get("default_redis", {})
            graph_settings = graph_pool_config.get("settings", {})

        redis_graph = RedisGraphAdapter(
            host=graph_settings.get("host", "localhost"),
            port=graph_settings.get("port", 6379),
            db=graph_settings.get("db", 0),
        )
        await redis_graph.connect(config=graph_settings)

        if not redis:
            logger.warning("Redis not available, data not loaded")
            return
        if not resume:
            logger.info("Clearing Redis KV database (db 0)...")
            await redis.clear()
            logger.info(f"Clearing Redis Graph database (db {graph_settings.get('db', 0)})...")
            await redis_graph.clear()
        else:
            logger.info("Resuming from checkpoint, skipping Redis clear...")
        await load_catalogs_to_redis(redis, project_path)
        ground_truth_path = Path(project_path) / data_config.get("ground_truth", "")
        examination_data_path = Path(project_path) / data_config.get("examination_data", "")
        doctor_profiles_path = Path(project_path) / data_config.get("doctor_profiles", "")
        patient_profiles_path = Path(project_path) / data_config.get("patient_profiles", "")
        if ground_truth_path.exists():
            with open(ground_truth_path, "r", encoding="utf-8") as f:
                ground_truth_data = json.load(f)

            for patient_id, truth_info in ground_truth_data.items():
                redis_key = f"hospital:ground_truth:{patient_id}"
                await redis.set(redis_key, truth_info)

            logger.info(f"Loaded ground truth for {len(ground_truth_data)} patients to Redis")
        else:
            logger.warning(f"Ground truth file not found: {ground_truth_path}")
        if examination_data_path.exists():
            with open(examination_data_path, "r", encoding="utf-8") as f:
                examination_data = json.load(f)

            for patient_id, exam_list in examination_data.items():
                redis_key = f"hospital:examination:{patient_id}"
                await redis.set(redis_key, exam_list)

            logger.info(f"Loaded examination data for {len(examination_data)} patients to Redis")
        else:
            logger.warning(f"Examination data file not found: {examination_data_path}")
        doctors = []
        if doctor_profiles_path.exists():
            with open(doctor_profiles_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        profile = json.loads(line)
                        agent_id = profile.get("id")
                        if agent_id:
                            doctors.append(profile)
            logger.info(f"Loading relationships for {len(doctors)} doctors from relation files...")

            relation_dir = Path(project_path) / "data" / "relation"
            nodes_path = relation_dir / "nodes.jsonl"
            edges_path = relation_dir / "edges.jsonl"
            node_count = 0
            if nodes_path.exists():
                with open(nodes_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            node_data = json.loads(line)
                            await redis_graph.create_node(node_data["id"], node_data.get("properties", {}))
                            node_count += 1
                logger.info(f"Created {node_count} doctor nodes in Redis Graph")
            else:
                logger.warning(f"Nodes file not found: {nodes_path}, skipping node creation")
            edge_count = 0
            if edges_path.exists():
                with open(edges_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            edge_data = json.loads(line)
                            relation_type = edge_data.get("relation_type", "colleague")
                            await redis_graph.create_edge(
                                edge_data["source"], edge_data["target"], {"relation_type": relation_type}
                            )
                            edge_count += 1
                logger.info(f"Created {edge_count} colleague edges in Redis Graph")
            else:
                logger.warning(f"Edges file not found: {edges_path}, skipping edge creation")
        if patient_profiles_path.exists():
            with open(patient_profiles_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        profile = json.loads(line)

        logger.info(f"Loaded doctor and patient profiles")

    except Exception as e:
        logger.error(f"Failed to load data to Redis: {e}")
    finally:
        if redis:
            await redis.disconnect()
        if redis_graph:
            await redis_graph.disconnect()


async def main() -> bool:
    """Main simulation loop."""
    parser = argparse.ArgumentParser(description="Hospital Simulation")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint (skip clearing Redis)")
    parser.add_argument("--patient-profiles", help="Override patient profiles JSONL path")
    parser.add_argument("--doctor-profiles", help="Override doctor profiles JSONL path")
    parser.add_argument("--ground-truth", help="Override ground truth JSON path")
    parser.add_argument("--examination-data", help="Override examination data JSON path")
    parser.add_argument("--event-log-dir", help="Override event output directory (default: decoupling_output)")
    parser.add_argument("--trajectory-output", help="Override final trajectory output JSON path")
    parser.add_argument(
        "--reflection-mode",
        choices=["write", "read_only", "off", "train", "eval", "readonly", "disabled"],
        help="Reflection mode for doctor plugin",
    )
    parser.add_argument("--reflection-namespace", help="Reflection namespace for experiment isolation")
    parser.add_argument("--skip-api-server", action="store_true", help="Skip launching local API server")
    parser.add_argument("--max-active-patients", type=int, help="Override max_active_patients in simulation config")
    parser.add_argument("--max-ticks", type=int, help="Override max_ticks in simulation config")
    args = parser.parse_args()

    resume_mode = args.resume

    if args.reflection_mode:
        os.environ["HOSPITAL_REFLECTION_MODE"] = args.reflection_mode
    if args.reflection_namespace:
        os.environ["HOSPITAL_REFLECTION_NAMESPACE"] = args.reflection_namespace

    api_process = None
    pod_manager = None
    system = None
    total_duration = 0
    keep_servers_alive = False

    try:
        if resume_mode:
            logger.info(f"Hospital Simulation starting in RESUME mode...")
        else:
            logger.info(f"Hospital Simulation starting in FRESH START mode...")
        logger.info(f"Project path: {project_path}")
        decoupling_output_dir = args.event_log_dir or os.path.join(project_path, "decoupling_output")
        decoupling_output_dir = str(Path(decoupling_output_dir).expanduser())
        if not os.path.isabs(decoupling_output_dir):
            decoupling_output_dir = os.path.join(project_path, decoupling_output_dir)
        log_dir_path = file_event_logger.start_logging(
            decoupling_output_dir,
            project_path=project_path,
            clear_old_logs=not resume_mode,
            patient_profiles_path=_resolve_optional_input_path(project_path, args.patient_profiles),
            doctor_profiles_path=_resolve_optional_input_path(project_path, args.doctor_profiles),
        )
        if log_dir_path:
            os.environ["MAS_EVENT_LOG_DIR"] = log_dir_path
            logger.info(f"Set environment variable MAS_EVENT_LOG_DIR to {log_dir_path}")
        if not ray.is_initialized():
            runtime_env = build_ray_runtime_env(
                project_path,
                extra_env_vars={
                    "MAS_EVENT_LOG_DIR": os.environ.get("MAS_EVENT_LOG_DIR", ""),
                },
            )

            logger.info(f"Initializing Ray with runtime_env...")
            ray.init(runtime_env=runtime_env)

        logger.info(f"Ray initialized.")
        logger.info(f"Building simulation...")
        resume_from_tick = None
        if resume_mode:
            redis = await get_redis_adapter(project_path)
            if redis:
                try:
                    saved_tick = await redis.get("simulation:current_tick")
                    if saved_tick is not None:
                        resume_from_tick = int(saved_tick)
                        logger.info(f"Found checkpoint at tick {resume_from_tick}, will resume from there")
                    else:
                        logger.warning("Resume mode requested but no checkpoint found in Redis")
                except Exception as e:
                    logger.warning(f"Failed to check for checkpoint: {e}")
                finally:
                    await redis.disconnect()
        else:
            logger.info("Fresh start mode: will start from tick 0")
        builder_class = RESOURCE_MAPS.get("builder", Builder)
        logger.info(f"Using builder class: {builder_class.__name__}")

        sim_builder = builder_class(
            project_path=project_path,
            resource_maps=RESOURCE_MAPS,
            resume_mode=resume_mode,                                     
        )

        data_overrides = {
            "patient_profiles": args.patient_profiles,
            "doctor_profiles": args.doctor_profiles,
            "ground_truth": args.ground_truth,
            "examination_data": args.examination_data,
        }
        if any(data_overrides.values()):
            _apply_data_overrides_to_builder(sim_builder, data_overrides)

        if args.max_active_patients is not None:
            setattr(sim_builder.config.simulation, "max_active_patients", args.max_active_patients)
            logger.info("Overrode simulation.max_active_patients=%s", args.max_active_patients)

        if args.max_ticks is not None:
            setattr(sim_builder.config.simulation, "max_ticks", args.max_ticks)
            logger.info("Overrode simulation.max_ticks=%s", args.max_ticks)
        if resume_from_tick is not None:
            if "timer" in sim_builder.config.system.components:
                sim_builder.config.system.components["timer"]["start_tick"] = resume_from_tick
                logger.info(f"Set timer start_tick to {resume_from_tick}")
            else:
                logger.warning("Timer component not found in system config, cannot set start_tick")
        if sim_builder.config.api_server:
            if args.skip_api_server:
                logger.info("--skip-api-server enabled, skipping local API server startup")
            else:
                logger.info("API server config found. Starting it in a separate process...")
                redis_pool_config = sim_builder.config.database.pools.get("default_redis")
                if not redis_pool_config:
                    raise ValueError("API server requires 'default_redis' pool in db_config.yaml")

                server_config = sim_builder.config.api_server.model_dump()
                server_config["redis_settings"] = redis_pool_config.settings

                api_process = multiprocessing.Process(target=start_server, args=(server_config,), daemon=True)
                api_process.start()
                logger.info(f"API server process started with PID: {api_process.pid}")
                await asyncio.sleep(3)
        data_config = sim_builder.config.data.model_dump() if hasattr(sim_builder.config.data, "model_dump") else {}
        await load_data_to_redis(project_path, data_config, resume=resume_mode)
        pod_manager, system = await sim_builder.init()
        logger.info(f"Simulation built successfully.")
        max_ticks = sim_builder.config.simulation.max_ticks
        start_tick = resume_from_tick if resume_from_tick is not None else 0
        queue_manager = sim_builder.get_queue_manager()
        use_infinite_loop = max_ticks is None or max_ticks == 0

        if resume_from_tick is not None:
            if use_infinite_loop:
                logger.info(f"Resuming simulation from tick {start_tick} (auto-stop when all patients finish)...")
            else:
                logger.info(f"Resuming simulation from tick {start_tick} to {max_ticks}...")
        else:
            if use_infinite_loop:
                logger.info(f"Starting simulation (auto-stop when all patients finish)...")
            else:
                logger.info(f"Starting simulation for {max_ticks} ticks...")

        current_tick = start_tick
        while True:
            if not use_infinite_loop and current_tick >= max_ticks:
                logger.info(f"Reached max_ticks limit ({max_ticks}). Stopping simulation.")
                break

            tick_start_time = time.time()

            current_tick = await system.run("timer", "get_tick")
            logger.info(f"=== Tick {current_tick} ===")
            await pod_manager.step_agent.remote()
            await system.run("messager", "dispatch_messages")

            tick_end_time = time.time()
            tick_duration = tick_end_time - tick_start_time
            total_duration += tick_duration
            if queue_manager:
                all_finished = await queue_manager.is_all_patients_finished.remote()
                if all_finished:
                    logger.info(f"All patients have finished treatment at tick {current_tick}. Stopping simulation.")
                    break
            await system.run("timer", "add_tick", duration_seconds=tick_duration)
            logger.info(f"--- Tick {current_tick} finished in {tick_duration:.4f}s ---")
        logger.info(f"Simulation complete.")
        actual_ticks = current_tick - start_tick + 1 if "current_tick" in dir() else 0

        if actual_ticks > 0:
            avg_duration = total_duration / actual_ticks
            logger.info(f"Actual ticks run: {actual_ticks}")
            logger.info(f"Average tick duration: {avg_duration:.4f}s")
            logger.info(f"Total duration: {total_duration:.4f}s")
        try:
            trajectory_path = await system.run("recorder", "save_trajectory", path=args.trajectory_output)
            if trajectory_path:
                logger.info(f"Trajectory saved to: {trajectory_path}")

        except Exception as e:
            logger.error(f"Failed to save trajectory: {e}")

    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user (Ctrl+C)")
        raise                               
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        file_event_logger.stop_logging()
        if "MAS_EVENT_LOG_DIR" in os.environ:
            del os.environ["MAS_EVENT_LOG_DIR"]
        if pod_manager:
            result = await pod_manager.close.remote()
            logger.info(f"Pod Manager closed: {result}")
        if system:
            result = await system.close()
            logger.info(f"System closed: {result}")
        if ray.is_initialized():
            ray.shutdown()
        if api_process and api_process.is_alive():
            import sys

            if sys.exc_info()[0] is KeyboardInterrupt:
                logger.info("Terminating API server process...")
                api_process.terminate()
                api_process.join()
            else:
                logger.info("API server will continue running. View results at http://localhost:8000")
                logger.info("Press Ctrl+C again to stop the server.")
                keep_servers_alive = True

    return keep_servers_alive


if __name__ == "__main__":
    try:
        keep_servers_alive = asyncio.run(main())

        if keep_servers_alive:
            print("\n" + "=" * 60)
            print("  Simulation completed successfully!")
            print("  Frontend: http://localhost:3000")
            print("  Backend:  http://localhost:8000")
            print("")
            print("  Servers are still running. You can view results in the frontend.")
            print("  Press Ctrl+C to stop all services.")
            print("=" * 60 + "\n")
            import signal

            def signal_handler(sig, frame):
                print("\nStopping servers...")
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Services stopped by user.")
    finally:
        logger.info("Exiting.")
