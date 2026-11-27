import os
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

_NOT_STATED = "No figura en la fuente"

OUTREACH_TABLE = "outreach_log"
OUTREACH_REQUIRED_COLUMNS = (
    "id",
    "agent_id",
    "category",
    "title",
    "recipient",
    "source_platform",
    "source_url",
    "source_url_of_application",
    "company_or_client_name",
    "contact_channel",
    "contact_ref",
    "contact_ref_pending",
    "full_text",
    "summary",
    "cv_reference",
    "attachment_reference",
    "hourly_rate_usd",
    "rate_model",
    "status",
    "gmail_message_id",
    "gmail_thread_id",
    "gmail_label",
    "last_response_at",
    "notes",
    "operator",
    "created_at",
    "updated_at",
)

_CONTEXT_FIELDS = (
    "summary",
    "tailored_summary",
    "proposed_solution",
    "outreach_draft",
    "reasons_to_stand_out",
    "highlights",
    "gaps",
    "pain_points",
    "missing_info",
    "next_steps",
    "match_arguments",
    "outreach_variants",
    "proposal_variants",
    "hourly_rate",
    "hourly_rate_usd",
    "rate_justification",
    "complexity",
    "hours_per_day",
    "estimated_hours_per_day",
    "estimated_timeline",
    "delivery_modalities",
    "preview_policy",
    "detailed_budget_note",
    "interview_prep",
    "role_title",
    "application_channel",
    "application_instructions",
    "cv_reference",
    "source",
    "source_platform",
    "source_url",
    "company_or_client_name",
    "contact_channel",
    "contact_ref",
    "contact_pending",
    "channel",
    "url",
    "market",
    "company",
    "prospect_name",
)


def _flatten_deliverable(row: dict[str, Any]) -> dict[str, Any]:
    """Expone content_json en el mismo nivel y completa trazabilidad sin inventar datos."""
    flat = dict(row)
    content = flat.pop("content_json", None) or {}
    if not isinstance(content, dict):
        content = {}
    for key, value in content.items():
        flat.setdefault(key, value)

    flat["source_platform"] = flat.get("source_platform") or flat.get("source") or "No figura en la fuente"
    flat["source_url"] = flat.get("source_url") or flat.get("url") or None
    flat["company_or_client_name"] = (
        flat.get("company_or_client_name")
        or flat.get("company")
        or flat.get("prospect_name")
        or _NOT_STATED
    )
    flat["contact_channel"] = flat.get("contact_channel") or flat.get("channel") or _NOT_STATED
    flat["contact_ref"] = flat.get("contact_ref") or flat.get("contact_email") or _NOT_STATED
    flat["contact_pending"] = bool(
        flat.get("contact_pending", True)
        and flat["contact_ref"] == _NOT_STATED
    )
    flat["source"] = flat["source_platform"]
    flat["summary"] = flat.get("summary") or flat.get("tailored_summary") or flat.get("proposed_solution") or ""
    if flat.get("fit_score") is None:
        flat["fit_score"] = content.get("fit_score")
    flat["_context_fields"] = [key for key in _CONTEXT_FIELDS if key in flat]
    return flat


class DatabaseManager:
    """Acceso a Supabase para estados de agentes, entregables y logs de ejecución."""

    def __init__(self) -> None:
        url: str = os.getenv("SUPABASE_URL") or ""
        key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        if not url or not key:
            raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env")
        self.supabase: Client = create_client(url, key)
        self.tz = ZoneInfo(os.getenv("APP_TIMEZONE", "America/Argentina/Buenos_Aires"))
        self._outreach_schema: dict[str, Any] | None = None

    def outreach_schema_status(self) -> dict[str, Any]:
        if self._outreach_schema is not None:
            return self._outreach_schema
        result: dict[str, Any] = {
            "available": False,
            "table": f"public.{OUTREACH_TABLE}",
            "missing_columns": [],
            "error": "",
            "message": "",
        }
        try:
            self.supabase.table(OUTREACH_TABLE).select(
                ",".join(OUTREACH_REQUIRED_COLUMNS)
            ).limit(1).execute()
            result["available"] = True
            result["message"] = (
                f"public.{OUTREACH_TABLE} disponible con todas las columnas del esquema OpenAPI."
            )
            self._outreach_schema = result
            return result
        except Exception as exc:
            raw = str(exc)
            lowered = raw.lower()
            result["error"] = raw
            table_missing = (
                "pgrst205" in lowered
                or ("could not find the" in lowered and "table" in lowered)
                or ("relation" in lowered and "does not exist" in lowered)
            )
            column_missing = (
                "pgrst204" in lowered
                or "undefined column" in lowered
                or ("could not find the" in lowered and "column" in lowered)
                or ("column" in lowered and "does not exist" in lowered)
            )
            if table_missing:
                result["message"] = (
                    f"No existe public.{OUTREACH_TABLE} en Supabase. "
                    "Aplicá backend/migrations/001_outreach_log.sql; si la tabla ya existía, "
                    "aplicá también backend/migrations/002_outreach_log_columns.sql."
                )
            elif column_missing:
                missing: list[str] = []
                for column in OUTREACH_REQUIRED_COLUMNS:
                    try:
                        self.supabase.table(OUTREACH_TABLE).select(column).limit(1).execute()
                    except Exception:
                        missing.append(column)
                result["missing_columns"] = missing
                if missing:
                    result["message"] = (
                        f"Faltan columnas en public.{OUTREACH_TABLE}: {', '.join(missing)}. "
                        "Aplicá backend/migrations/002_outreach_log_columns.sql."
                    )
                else:
                    result["message"] = (
                        f"El esquema de public.{OUTREACH_TABLE} no coincide con el OpenAPI: {raw}"
                    )
            elif "schema cache" in lowered:
                result["message"] = (
                    f"No se pudo verificar public.{OUTREACH_TABLE} por un error de caché de Supabase: {raw}"
                )
            elif any(token in lowered for token in ("permission denied", "401", "403", "jwt", "rls")):
                result["message"] = (
                    f"Supabase rechazó la lectura de public.{OUTREACH_TABLE}: {raw}. "
                    "Verificá SUPABASE_SERVICE_ROLE_KEY y las policies de RLS."
                )
            else:
                result["message"] = f"No se pudo verificar public.{OUTREACH_TABLE}: {raw}"
        self._outreach_schema = result
        return result

    @property
    def outreach_available(self) -> bool:
        return bool(self.outreach_schema_status()["available"])

    def can_run_now(self) -> tuple[bool, str]:
        """Devuelve (puede_correr, motivo) según system_config."""
        response = (
            self.supabase.table("system_config")
            .select("*")
            .eq("id", 1)
            .maybe_single()
            .execute()
        )
        config = response.data
        if not config:
            return False, "No se encontró system_config (id=1)"
        if not config.get("is_active", False):
            return False, "La oficina está pausada manualmente (is_active=false)"

        now_hour = datetime.now(self.tz).hour
        start_hour = int(config.get("work_start_hour", 0))
        end_hour = int(config.get("work_end_hour", 23))
        if not (start_hour <= now_hour <= end_hour):
            return False, f"Fuera de horario operativo ({now_hour}h fuera de {start_hour}h-{end_hour}h)"

        return self.check_token_budget()

    def _config_row(self) -> dict[str, Any]:
        response = (
            self.supabase.table("system_config")
            .select("*")
            .eq("id", 1)
            .maybe_single()
            .execute()
        )
        return response.data or {}

    def token_budget(self) -> dict[str, Any]:
        config = self._config_row()
        used = int(config.get("tokens_used_today", 0))
        configured_limit = config.get("daily_token_limit") or config.get("daily_tokens_limit")
        limit = int(os.getenv("DAILY_TOKEN_LIMIT") or configured_limit or 150000)
        threshold = float(os.getenv("TOKEN_ALERT_THRESHOLD", "0.85"))
        ratio = round(used / limit, 4) if limit > 0 else 1.0
        alert = ratio >= threshold
        exhausted = used >= limit
        if exhausted:
            message = (
                f"Sara: alcanzamos el límite diario de tokens ({used}/{limit}). "
                "Es preferible continuar mañana; frené las corridas pesadas."
            )
        elif alert:
            message = (
                f"Sara: queda poco margen de tokens hoy ({used}/{limit}, {int(ratio * 100)}%). "
                "Conviene pausar nuevas búsquedas y continuar mañana."
            )
        else:
            message = "Sara: margen de tokens suficiente para continuar las corridas de hoy."
        return {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "ratio": ratio,
            "threshold": threshold,
            "alert": alert,
            "exhausted": exhausted,
            "message": message,
        }

    def check_token_budget(self) -> tuple[bool, str]:
        budget = self.token_budget()
        if budget["exhausted"] or budget["alert"]:
            return False, str(budget["message"])
        return True, "OK"

    def set_agent_state(self, agent_id: str, status: str, task: str) -> None:
        """Actualiza status y current_task de un agente en la tabla agent_states."""
        (
            self.supabase.table("agent_states")
            .update({
                "status": status,
                "current_task": task,
                "updated_at": datetime.now(self.tz).isoformat(),
            })
            .eq("agent_id", agent_id)
            .execute()
        )

    def get_agent_states(self) -> list[dict[str, Any]]:
        """Devuelve los estados visibles de la oficina, con un fallback para filas faltantes."""
        response = self.supabase.table("agent_states").select("*").execute()
        return response.data or []

    def save_deliverable(
        self,
        agent_id: str,
        category: str,
        title: str,
        content_json: dict[str, Any],
        source_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Guarda un borrador en pending_approval evitando duplicados por source_url."""
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
        return {
            "duplicate": False,
            "record": _flatten_deliverable(inserted.data[0] if inserted.data else payload),
        }

    def list_deliverables(self, status: Optional[str] = "pending_approval") -> list[dict[str, Any]]:
        """Lista entregables con content_json aplanado para el frontend."""
        query = self.supabase.table("deliverables").select("*")
        if status:
            query = query.eq("status", status)
        response = query.order("created_at", desc=True).execute()
        return [_flatten_deliverable(row) for row in (response.data or [])]

    def get_deliverable(self, deliverable_id: str) -> Optional[dict[str, Any]]:
        response = (
            self.supabase.table("deliverables")
            .select("*")
            .eq("id", deliverable_id)
            .maybe_single()
            .execute()
        )
        return _flatten_deliverable(response.data) if response.data else None

    def update_deliverable_status(
        self,
        deliverable_id: str,
        status: str,
        reviewer_notes: str = "",
    ) -> dict[str, Any]:
        """Actualiza el estado del entregable; usa user_feedback si existe en el esquema."""
        payload: dict[str, Any] = {"status": status}
        if reviewer_notes:
            payload["user_feedback"] = reviewer_notes[:1000]
        response = (
            self.supabase.table("deliverables")
            .update(payload)
            .eq("id", deliverable_id)
            .execute()
        )
        return _flatten_deliverable(response.data[0]) if response.data else {"id": deliverable_id, **payload}

    def log_execution(
        self,
        agent_id: str,
        action: str,
        tokens_consumed: int = 0,
        status: str = "success",
        details: str = "",
    ) -> None:
        """Registra la ejecución y acumula tokens consumidos en system_config."""
        (
            self.supabase.table("execution_logs")
            .insert({
                "agent_id": agent_id,
                "action": action,
                "tokens_consumed": tokens_consumed,
                "status": status,
                "details": details[:1000],
            })
            .execute()
        )
        if tokens_consumed > 0:
            cfg_res = (
                self.supabase.table("system_config")
                .select("tokens_used_today")
                .eq("id", 1)
                .maybe_single()
                .execute()
            )
            current_tokens = int((cfg_res.data or {}).get("tokens_used_today", 0))
            (
                self.supabase.table("system_config")
                .update({
                    "tokens_used_today": current_tokens + tokens_consumed,
                    "updated_at": datetime.now(self.tz).isoformat(),
                })
                .eq("id", 1)
                .execute()
            )

    def add_outreach_record(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """Inscribe un envío/postulación trazable. Devuelve None si falta la migración."""
        if not self.outreach_available:
            return None
        payload = dict(record)
        payload.setdefault("status", "pending_approval")
        payload.setdefault("source_platform", "No figura en la fuente")
        payload.setdefault("company_or_client_name", _NOT_STATED)
        payload.setdefault("contact_channel", _NOT_STATED)
        payload.setdefault("contact_ref", _NOT_STATED)
        payload.setdefault("contact_ref_pending", payload["contact_ref"] == _NOT_STATED)
        payload["created_at"] = datetime.now(self.tz).isoformat()
        payload["updated_at"] = payload["created_at"]
        response = self.supabase.table(OUTREACH_TABLE).insert(payload).execute()
        return response.data[0] if response.data else payload

    def list_outreach(self, status: Optional[str] = None, agent_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Historial de enviados y seguimiento, ordenado por fecha descendente."""
        if not self.outreach_available:
            return []
        query = self.supabase.table(OUTREACH_TABLE).select("*")
        if status:
            query = query.eq("status", status)
        if agent_id:
            query = query.eq("agent_id", agent_id)
        response = query.order("created_at", desc=True).execute()
        return response.data or []

    def update_outreach_status(
        self,
        record_id: str,
        status: str,
        notes: str = "",
        response_at: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """Actualiza el estado de seguimiento de un envío registrado."""
        if not self.outreach_available:
            return None
        payload: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(self.tz).isoformat(),
        }
        if notes:
            payload["notes"] = notes[:1000]
        if response_at:
            payload["last_response_at"] = response_at
        result = (
            self.supabase.table(OUTREACH_TABLE)
            .update(payload)
            .eq("id", record_id)
            .execute()
        )
        return result.data[0] if result.data else {"id": record_id, **payload}

    def link_outreach_gmail(
        self,
        record_id: str,
        message_id: str,
        thread_id: str,
        label: str,
        status: Optional[str] = None,
        notes: str = "",
        response_at: Optional[str] = None,
    ) -> dict[str, Any] | None:
        if not self.outreach_available:
            return None
        payload: dict[str, Any] = {
            "gmail_message_id": message_id or None,
            "gmail_thread_id": thread_id or None,
            "gmail_label": label,
            "updated_at": datetime.now(self.tz).isoformat(),
        }
        if status:
            payload["status"] = status
        if notes:
            payload["notes"] = notes[:1000]
        if response_at:
            payload["last_response_at"] = response_at
        result = (
            self.supabase.table(OUTREACH_TABLE)
            .update(payload)
            .eq("id", record_id)
            .execute()
        )
        return result.data[0] if result.data else {"id": record_id, **payload}

    def get_outreach_record(self, record_id: str) -> dict[str, Any] | None:
        if not self.outreach_available:
            return None
        result = (
            self.supabase.table(OUTREACH_TABLE)
            .select("*")
            .eq("id", record_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def find_outreach_by_thread(self, thread_id: str) -> dict[str, Any] | None:
        if not self.outreach_available:
            return None
        result = (
            self.supabase.table(OUTREACH_TABLE)
            .select("*")
            .eq("gmail_thread_id", thread_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
