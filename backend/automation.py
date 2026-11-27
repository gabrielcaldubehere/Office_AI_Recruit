import os
import threading
import time
from datetime import datetime
from typing import Any, Callable

from database import DatabaseManager
from llm_router import LLMBudgetExceeded, LLMResponseError


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()


class AutomationController:
    def __init__(
        self,
        db: DatabaseManager,
        cycles: dict[str, Callable[[], dict[str, Any]]],
    ) -> None:
        self.db = db
        self.cycles = cycles
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._reason = ""
        self._paused_by_operator = False
        self._started_at: str | None = None
        self._agents: dict[str, dict[str, Any]] = {
            name: {
                "running": False,
                "last_run": None,
                "next_run": None,
                "last_result": None,
                "last_error": None,
                "runs": 0,
            }
            for name in cycles
        }

    def _interval(self, name: str, default_minutes: int) -> int:
        key = f"AUTO_{name.upper()}_INTERVAL_MINUTES"
        return max(1, int(os.getenv(key, str(default_minutes)))) * 60

    def _set_reason(self, reason: str) -> None:
        with self._lock:
            self._reason = str(reason)[:1000]

    def _pause_internal(self, reason: str) -> None:
        self._pause.set()
        self._set_reason(reason)
        self.db.log_execution(
            agent_id="sara",
            action="automation_paused",
            status="blocked",
            details=reason,
        )

    def start(self, trigger: str = "operator") -> dict[str, Any]:
        with self._lock:
            if any(thread.is_alive() for thread in self._threads.values()):
                self._pause.clear()
                self._paused_by_operator = False
                self._reason = ""
                return self.status()
            if os.getenv("AUTO_ENABLED", "true").lower() in ("false", "0", "no"):
                self._set_reason("AUTO_ENABLED=false: automatización desactivada por configuración")
                return self.status()
            if self._paused_by_operator:
                self._set_reason("Búsquedas pausadas manualmente por el operador")
                return self.status()
            allowed, reason = self.db.can_run_now()
            if not allowed:
                self._set_reason(reason)
                return self.status()
            budget = self.db.token_budget()
            if budget["alert"] or budget["exhausted"]:
                self._pause_internal(str(budget["message"]))
                return self.status()
            self._stop.clear()
            self._pause.clear()
            self._reason = ""
            self._started_at = _iso_now()
            self._threads = {}
            for name in self.cycles:
                thread = threading.Thread(
                    target=self._worker,
                    args=(name,),
                    name=f"auto-{name}",
                    daemon=True,
                )
                self._threads[name] = thread
                self._agents[name]["running"] = True
                self._agents[name]["last_error"] = None
                thread.start()
            self.db.log_execution(
                agent_id="sara",
                action="automation_started",
                status="success",
                details=f"trigger={trigger} | agents={','.join(self.cycles)}",
            )
        return self.status()

    def pause(self, reason: str = "Pausado manualmente por el operador") -> dict[str, Any]:
        with self._lock:
            self._paused_by_operator = True
            self._pause_internal(reason)
            for values in self._agents.values():
                values["next_run"] = None
        return self.status()

    def resume(self) -> dict[str, Any]:
        with self._lock:
            self._paused_by_operator = False
            self._pause.clear()
            self._reason = ""
            self.db.log_execution(
                agent_id="sara",
                action="automation_resumed",
                status="success",
                details="Reanudado por el operador",
            )
        return self.start(trigger="resume")

    def stop(self) -> dict[str, Any]:
        threads = list(self._threads.values())
        self._stop.set()
        self._pause.clear()
        for thread in threads:
            thread.join(timeout=1.0)
        with self._lock:
            self._threads = {}
            self._paused_by_operator = False
            self._reason = ""
            for name, values in self._agents.items():
                values["running"] = False
                values["next_run"] = None
        self.db.log_execution(
            agent_id="sara",
            action="automation_stopped",
            status="success",
            details="Detenido por el operador",
        )
        return self.status()

    def _update_next_run(self, name: str, seconds: int) -> None:
        with self._lock:
            self._agents[name]["next_run"] = datetime.fromtimestamp(
                time.time() + seconds
            ).astimezone().isoformat()

    def _worker(self, name: str) -> None:
        default = 30 if name == "mateo" else 45
        interval = self._interval(name, default)
        while not self._stop.is_set():
            if self._pause.is_set():
                with self._lock:
                    self._agents[name]["running"] = False
                    self._agents[name]["next_run"] = None
                self._stop.wait(5)
                continue
            budget = self.db.token_budget()
            if budget["alert"] or budget["exhausted"]:
                self._pause_internal(str(budget["message"]))
                self._stop.wait(min(interval, 60))
                continue
            allowed, reason = self.db.can_run_now()
            if not allowed:
                self._set_reason(reason)
                self._stop.wait(min(interval, 60))
                continue
            with self._lock:
                self._agents[name]["running"] = True
                self._agents[name]["last_error"] = None
            self._update_next_run(name, interval)
            try:
                result = self.cycles[name]()
                with self._lock:
                    values = self._agents[name]
                    values["last_run"] = _iso_now()
                    values["last_result"] = result
                    values["runs"] += 1
            except LLMBudgetExceeded as exc:
                self._pause_internal(str(exc))
            except LLMResponseError as exc:
                self._pause_internal(
                    f"{name}: respuesta LLM vacía o sin JSON válido; pauso para no quemar tokens. {exc}"
                )
            except Exception as exc:
                with self._lock:
                    self._agents[name]["last_error"] = str(exc)[:1000]
                self.db.log_execution(
                    agent_id="sara",
                    action="automation_cycle_error",
                    status="error",
                    details=f"{name}: {exc}",
                )
            self._update_next_run(name, interval)
            self._stop.wait(interval)
        with self._lock:
            self._agents[name]["running"] = False
            self._agents[name]["next_run"] = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            alive = any(thread.is_alive() for thread in self._threads.values())
            state = "stopped"
            if alive:
                state = "paused" if self._pause.is_set() else "running"
            return {
                "state": state,
                "enabled": os.getenv("AUTO_ENABLED", "true").lower() not in ("false", "0", "no"),
                "started_at": self._started_at,
                "reason": self._reason,
                "max_age_days": int(os.getenv("SOURCE_MAX_AGE_DAYS", "15")),
                "budget": self.db.token_budget(),
                "agents": {name: dict(values) for name, values in self._agents.items()},
            }
