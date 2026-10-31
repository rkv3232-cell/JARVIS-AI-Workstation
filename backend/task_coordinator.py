import asyncio
import time
from typing import Dict, Any, Optional, Callable

class BackgroundTaskCoordinator:
    """
    Central coordinator for long-running and recurring background tasks in J.A.R.V.I.S.
    Enforces concurrency limits, prevents duplicate overlapping jobs, and provides
    telemetry on task status, run counts, and errors.
    """
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._task_metadata: Dict[str, Dict[str, Any]] = {}
        self._active_asyncio_tasks: Dict[str, asyncio.Task] = {}

    def _get_lock(self, task_name: str) -> asyncio.Lock:
        if task_name not in self._locks:
            self._locks[task_name] = asyncio.Lock()
        return self._locks[task_name]

    def is_running(self, task_name: str) -> bool:
        lock = self._get_lock(task_name)
        return lock.locked()

    async def run_exclusive(self, task_name: str, coroutine_func: Callable, *args, **kwargs) -> Any:
        """
        Executes a task exclusively. If an instance of the task is already active,
        it gracefully skips execution rather than queuing up or colliding.
        """
        lock = self._get_lock(task_name)
        if lock.locked():
            print(f"[Task Coordinator] Task '{task_name}' is already executing; skipping duplicate request.")
            return None

        async with lock:
            meta = self._task_metadata.setdefault(task_name, {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "last_started": None,
                "last_finished": None,
                "last_duration_ms": 0,
                "last_error": None,
                "status": "idle"
            })
            meta["status"] = "running"
            meta["last_started"] = time.time()
            meta["total_runs"] += 1
            t0 = time.perf_counter()

            try:
                result = await coroutine_func(*args, **kwargs)
                meta["successful_runs"] += 1
                meta["status"] = "idle"
                meta["last_error"] = None
                return result
            except Exception as e:
                meta["failed_runs"] += 1
                meta["status"] = "error"
                meta["last_error"] = str(e)
                print(f"[Task Coordinator Error in '{task_name}']: {e}")
                raise e
            finally:
                meta["last_finished"] = time.time()
                meta["last_duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                if meta["status"] != "error":
                    meta["status"] = "idle"

    def get_status(self) -> Dict[str, Any]:
        result = {}
        for name, meta in self._task_metadata.items():
            result[name] = {
                **meta,
                "is_currently_running": self.is_running(name)
            }
        return result

task_coordinator = BackgroundTaskCoordinator()

