import re
from typing import Literal

from agents.mateo import MateoRecruiterAgent
from agents.valeria import ValeriaHunterAgent
from database import DatabaseManager
from llm_router import LLMRouter


class SaraOrchestrator:
    """Directora: filtra, deduplica, coordina agentes y controla tokens."""

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self.db = db or DatabaseManager()
        self.router = LLMRouter(
            token_guard=self.db.check_token_budget,
            event_logger=self._router_event,
        )
        self.mateo = MateoRecruiterAgent(self.router)
        self.valeria = ValeriaHunterAgent(self.db, self.router)
        self.agent_id = "sara"

    def _router_event(self, event: dict) -> None:
        status = str(event.get("status") or "success")
        details = (
            f"provider={event.get('provider')} | tokens={event.get('tokens', 0)} | "
            f"{event.get('details', '')}"
        )
        self.db.log_execution(
            agent_id=self.agent_id,
            action=f"llm_{status}",
            tokens_consumed=int(event.get("tokens") or 0),
            status="success" if status == "success" else "error",
            details=details,
        )

    def _is_duplicate_deliverable(self, category: str, source_key: str) -> bool:
        existing = (
            self.db.supabase.table("deliverables")
            .select("id, content_json, source_url")
            .eq("category", category)
            .execute()
            .data
            or []
        )
        for row in existing:
            content = row.get("content_json") or {}
            if source_key and (
                row.get("source_url") == source_key
                or content.get("source_url") == source_key
                or content.get("url") == source_key
            ):
                return True
        return False

    def _passes_quick_job_prefilter(self, raw_job_text: str) -> tuple[bool, str]:
        text = raw_job_text.lower()
        blocked_seniority = [
            r"\b(senior|sr\.?|lead|staff|principal|architect|director|vp|head of)\b",
            r"\b([6-9]|10)\+?\s*(años|years)\s+(de\s+)?(experiencia|exp\.?)\b",
        ]
        for pattern in blocked_seniority:
            if re.search(pattern, text):
                return False, "Seniority o años de experiencia por encima del perfil junior"
        if "100% presencial" in text or "presencial obligatorio" in text:
            return False, "Requiere presencialidad fija no alineada con remoto/híbrido"
        return True, "Pasa pre-filtro rápido"

    def _blocked_result(self, reason: str, **flags: bool) -> dict:
        base = {
            "executed": False,
            "saved_for_approval": False,
            "duplicate": False,
            "filtered_out": False,
            "reason": reason,
            "activity": [],
        }
        base.update(flags)
        return base

    def _recent_activity(self, agent_id: str) -> list[dict]:
        try:
            rows = (
                self.db.supabase.table("execution_logs")
                .select("action, status, details, created_at")
                .eq("agent_id", agent_id)
                .order("created_at", desc=True)
                .limit(4)
                .execute()
                .data
                or []
            )
            return [
                {
                    "action": row.get("action", ""),
                    "status": row.get("status", "success"),
                    "details": (row.get("details") or "")[:180],
                    "at": row.get("created_at"),
                }
                for row in rows
            ]
        except Exception:
            return []

    def run_job_evaluation_flow(
        self,
        raw_job_text: str,
        job_url: str,
        market: Literal["LATAM_ES", "GLOBAL_EN"] = "LATAM_ES",
        min_fit_score: int = 60,
        skip_prefilter: bool = False,
        source_platform: str = "",
    ) -> dict:
        can_run, reason = self.db.can_run_now()
        if not can_run:
            return self._blocked_result(reason)

        if self._is_duplicate_deliverable("job_application", job_url):
            return self._blocked_result("La oferta ya fue evaluada previamente.", duplicate=True)

        if not skip_prefilter:
            passed, filter_reason = self._passes_quick_job_prefilter(raw_job_text)
            if not passed:
                self.db.log_execution(
                    agent_id=self.agent_id,
                    action="job_prefiltered",
                    status="skipped",
                    details=f"URL={job_url} | Motivo={filter_reason}",
                )
                return self._blocked_result(filter_reason, filtered_out=True)

        self.db.set_agent_state(self.agent_id, status="working", task=f"Coordinando evaluación laboral: {job_url}")
        try:
            result = self.mateo.evaluate_job(raw_job_text, job_url, market)
            evaluation = result["evaluation"]
            evaluation["source_platform"] = source_platform or evaluation.get("source_platform") or "No figura en la fuente"
            evaluation["source_url"] = job_url
            fit_score = int(evaluation.get("fit_score") or 0)
            saved = False
            saved_record = None

            if evaluation.get("eligible") and fit_score >= min_fit_score:
                saved_record = self.db.save_deliverable(
                    agent_id="mateo",
                    category="job_application",
                    title=f"[{fit_score}%] {evaluation.get('role_title', 'Vacante')}",
                    content_json=evaluation,
                    source_url=job_url,
                )
                saved = not saved_record.get("duplicate")

            self.db.set_agent_state(
                self.agent_id,
                status="waiting_approval" if saved else "idle",
                task=(
                    "Borrador laboral listo para aprobación humana"
                    if saved
                    else "Vacante evaluada sin cumplir umbral para aprobación"
                ),
            )
            return {
                "executed": True,
                "saved_for_approval": saved,
                "duplicate": bool(saved_record and saved_record.get("duplicate")),
                "filtered_out": False,
                "provider": result.get("provider"),
                "tokens_used": result.get("tokens_used"),
                "evaluation": evaluation,
                "activity": self._recent_activity("mateo"),
            }
        finally:
            self._restore_idle_state()

    def run_prospect_evaluation_flow(
        self,
        prospect_info: str,
        source_url: str,
        channel: str = "web",
        min_fit_score: int = 60,
        source_platform: str = "",
    ) -> dict:
        can_run, reason = self.db.can_run_now()
        if not can_run:
            return self._blocked_result(reason)

        if self._is_duplicate_deliverable("client_lead", source_url):
            return self._blocked_result("Este prospecto/fuente ya fue evaluado previamente.", duplicate=True)

        self.db.set_agent_state(self.agent_id, status="working", task=f"Coordinando prospección: {source_url}")
        try:
            result = self.valeria.evaluate_prospect(prospect_info, source_url, channel, source_platform)
            evaluation = result["evaluation"]
            evaluation["source_url"] = source_url
            evaluation["source_platform"] = source_platform or evaluation.get("source_platform") or "No figura en la fuente"
            fit_score = int(evaluation.get("fit_score") or 0)
            saved = False
            saved_record = None

            if evaluation.get("recommended") and fit_score >= min_fit_score:
                saved_record = self.db.save_deliverable(
                    agent_id="valeria",
                    category="client_lead",
                    title=(
                        f"[{fit_score}%] {evaluation.get('prospect_name', 'Prospecto')} - "
                        f"{evaluation.get('opportunity_type', 'Propuesta')}"
                    ),
                    content_json=evaluation,
                    source_url=source_url,
                )
                saved = not saved_record.get("duplicate")

            self.db.set_agent_state(
                self.agent_id,
                status="waiting_approval" if saved else "idle",
                task=(
                    "Propuesta de cliente lista para aprobación humana"
                    if saved
                    else "Prospecto evaluado sin cumplir umbral para aprobación"
                ),
            )
            return {
                "executed": True,
                "saved_for_approval": saved,
                "duplicate": bool(saved_record and saved_record.get("duplicate")),
                "filtered_out": False,
                "provider": result.get("provider"),
                "tokens_used": result.get("tokens_used"),
                "evaluation": evaluation,
                "activity": self._recent_activity("valeria"),
            }
        finally:
            self._restore_idle_state()

    def _restore_idle_state(self) -> None:
        response = (
            self.db.supabase.table("agent_states")
            .select("status")
            .eq("agent_id", self.agent_id)
            .maybe_single()
            .execute()
        )
        if (response.data or {}).get("status") == "working":
            self.db.set_agent_state(self.agent_id, status="idle", task="En espera de instrucciones")

    def run_batch_evaluation(
        self,
        item_type: Literal["job", "client"],
        items: list[dict],
        market: Literal["LATAM_ES", "GLOBAL_EN"] = "GLOBAL_EN",
        channel: Literal["whatsapp", "linkedin", "web", "referral"] = "web",
        min_fit_score: int = 60,
        max_items_per_batch: int = 25,
    ) -> dict:
        can_run, reason = self.db.can_run_now()
        if not can_run:
            return {
                "processed": 0,
                "saved_for_approval": 0,
                "duplicates": 0,
                "filtered_out": 0,
                "total_tokens": 0,
                "reason": reason,
                "results": [],
            }

        saved_count = duplicates_count = filtered_count = total_tokens = 0
        results: list[dict] = []
        for idx, item in enumerate(items[:max_items_per_batch], start=1):
            platform = str(item.get("source_platform") or item.get("source") or "").strip()
            if item_type == "job":
                url = str(item.get("job_url") or item.get("url") or f"batch-job-{idx}").strip()
                res = self.run_job_evaluation_flow(
                    raw_job_text=str(item.get("raw_job_text") or item.get("text") or "").strip(),
                    job_url=url,
                    market=item.get("market") or market,
                    min_fit_score=min_fit_score,
                    source_platform=platform,
                )
            else:
                url = str(item.get("source_url") or item.get("url") or item.get("client_ref") or f"batch-client-{idx}").strip()
                res = self.run_prospect_evaluation_flow(
                    prospect_info=str(item.get("raw_client_text") or item.get("prospect_info") or item.get("text") or "").strip(),
                    source_url=url,
                    channel=str(item.get("channel") or channel),
                    min_fit_score=min_fit_score,
                    source_platform=platform,
                )

            if res.get("duplicate"):
                duplicates_count += 1
            elif res.get("filtered_out"):
                filtered_count += 1
            elif res.get("saved_for_approval"):
                saved_count += 1
            total_tokens += int(res.get("tokens_used") or 0)
            results.append({"index": idx, "url": url, **res})

        return {
            "processed": len(items[:max_items_per_batch]),
            "saved_for_approval": saved_count,
            "duplicates": duplicates_count,
            "filtered_out": filtered_count,
            "total_tokens": total_tokens,
            "results": results,
        }

    def execute_approved_deliverable(self, item: dict, operator: str) -> dict:
        """Prepara el paso final sin ejecutar mutaciones externas: registra la acción y su canal."""
        content = item.get("content_json") or {}
        category = item.get("category")
        if category == "job_application":
            channel = content.get("application_channel") or "manual_review"
            instructions = content.get("application_instructions") or ""
            action = "job_application_prepared"
            details = (
                f"Operador={operator} | Canal={channel} | "
                f"Instrucciones del aviso={instructions[:400] or 'no provistas'}"
            )
            outcome = {
                "executed": False,
                "external_action": "none",
                "reason": "La postulación queda preparada con datos verificados; el envío requiere acción humana.",
                "application_channel": channel,
                "application_instructions": instructions,
                "short_pitch": (content.get("tailored_summary") or "")[:600],
                "match_arguments": content.get("match_arguments") or [],
            }
        else:
            variants = content.get("outreach_variants") or []
            action = "client_outreach_prepared"
            details = f"Operador={operator} | Variantes={len(variants)} | Tarifa={content.get('hourly_rate_usd')}"
            outcome = {
                "executed": False,
                "external_action": "none",
                "reason": "Se generaron variantes de contacto; ningún mensaje fue enviado automáticamente.",
                "outreach_variants": variants,
                "hourly_rate_usd": content.get("hourly_rate_usd"),
                "rate_justification": content.get("rate_justification") or "",
            }

        self.db.log_execution(
            agent_id=str(item.get("agent_id") or "sara"),
            action=action,
            status="prepared_for_human",
            details=details,
        )
        return outcome

    def get_agent_activity(self, agent_id: str) -> list[dict]:
        return self._recent_activity(agent_id)
