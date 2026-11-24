import os  # Lee variables de entorno (como `process.env` en Node.js)
from datetime import datetime  # Manejo de fechas y horas (como `Date` en JS/TS)
from zoneinfo import ZoneInfo  # Zona horaria exacta (ej. America/Argentina/Buenos_Aires)
from typing import Any, Optional  # Tipado flexible o valores opcionales
from dotenv import load_dotenv  # Carga el archivo .env
from supabase import Client, create_client  # Cliente oficial de Supabase para Python

load_dotenv()


class DatabaseManager:
    """
    Encapsula todas las operaciones con Supabase (PostgreSQL).
    En TypeScript sería similar a un servicio `DatabaseService` con métodos async/sync.
    """

    def __init__(self) -> None:
        # En Python, `or ""` asegura que siempre sea `str` y nunca `None` al pasarlo a `create_client`
        url: str = os.getenv("SUPABASE_URL") or ""
        # Usamos SERVICE_ROLE_KEY en el backend para operar sin quedar trabados por RLS en servidor;
        # nunca expongas esta clave en el frontend ni en GitHub.
        key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""

        if not url or not key:
            raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env")

        self.supabase: Client = create_client(url, key)
        self.tz = ZoneInfo(os.getenv("APP_TIMEZONE", "America/Argentina/Buenos_Aires"))

    def can_run_now(self) -> tuple[bool, str]:
        """
        Consulta `system_config` para saber si la oficina está activa y en horario.
        Devuelve una tupla `(puede_correr, motivo)` — en TS sería `{ ok: boolean; reason: string }`.
        """
        response = self.supabase.table("system_config").select("*").eq("id", 1).single().execute()
        config = response.data

        if not config:
            return False, "No se encontró system_config (id=1)"

        if not config.get("is_active", False):
            return False, "La oficina está pausada manualmente (is_active=false)"

        # Revisamos ventana horaria configurada
        now_hour = datetime.now(self.tz).hour
        start_hour = int(config.get("work_start_hour", 0))
        end_hour = int(config.get("work_end_hour", 23))

        if not (start_hour <= now_hour <= end_hour):
            return False, f"Fuera de horario operativo ({now_hour}h fuera de {start_hour}h-{end_hour}h)"

        # Revisamos límite diario de tokens configurado
        tokens_used = int(config.get("tokens_used_today", 0))
        daily_limit = int(config.get("daily_token_limit", 150000))
        if tokens_used >= daily_limit:
            return False, f"Límite diario de tokens alcanzado ({tokens_used}/{daily_limit})"

        return True, "OK"

    def set_agent_state(self, agent_id: str, status: str, task: str) -> None:
        """
        Actualiza el estado de un avatar ('sara', 'mateo', 'valeria', 'lucas', 'elena')
        para que la oficina interactiva muestre qué está haciendo.
        """
        self.supabase.table("agent_states").update({
            "status": status,
            "current_task": task,
            "updated_at": datetime.now(self.tz).isoformat(),
        }).eq("agent_id", agent_id).execute()

    def save_deliverable(
        self,
        agent_id: str,
        category: str,
        title: str,
        content_json: dict[str, Any],
        source_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Guarda un borrador en `deliverables` con `status = 'pending_approval'`.
        Si `source_url` ya existe, evita duplicarlo gracias al constraint UNIQUE o verificación previa.
        """
        if source_url:
            existing = (
                self.supabase.table("deliverables")
                .select("id, title, status")
                .eq("source_url", source_url)
                .execute()
            )
            if existing.data:
                return {"duplicate": True, "existing": existing.data[0]}

        payload = {
            "agent_id": agent_id,
            "category": category,
            "title": title,
            "source_url": source_url,
            "content_json": content_json,
            "status": "pending_approval",
        }

        inserted = self.supabase.table("deliverables").insert(payload).execute()
        return {"duplicate": False, "record": inserted.data[0] if inserted.data else payload}

    def log_execution(
        self,
        agent_id: str,
        action: str,
        tokens_consumed: int = 0,
        status: str = "success",
        details: str = "",
    ) -> None:
        """
        Registra la ejecución en `execution_logs` y suma tokens consumidos en `system_config`.
        """
        self.supabase.table("execution_logs").insert({
            "agent_id": agent_id,
            "action": action,
            "tokens_consumed": tokens_consumed,
            "status": status,
            "details": details[:1000],  # Limitamos longitud para mantener logs limpios
        }).execute()

        if tokens_consumed > 0:
            cfg_res = self.supabase.table("system_config").select("tokens_used_today").eq("id", 1).single().execute()
            current_tokens = int((cfg_res.data or {}).get("tokens_used_today", 0))
            self.supabase.table("system_config").update({
                "tokens_used_today": current_tokens + tokens_consumed,
                "updated_at": datetime.now(self.tz).isoformat(),
            }).eq("id", 1).execute()