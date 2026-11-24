import re
from typing import Literal, Optional

from database import DatabaseManager
from llm_router import LLMRouter
from agents.mateo import MateoRecruiterAgent
from agents.valeria import ValeriaHunterAgent


class SaraOrchestrator:
    """Directora / Orquestadora: filtra, evita duplicados, coordina agentes y controla tokens."""

    def __init__(self) -> None:
        self.db = DatabaseManager()
        self.router = LLMRouter()
        self.mateo = MateoRecruiterAgent(self.db)
        self.valeria = ValeriaHunterAgent(self.db, self.router)
        self.agent_id = "sara"

    def _is_duplicate_deliverable(self, category: str, source_key: str) -> bool:
        """Evita re-evaluar o duplicar una misma URL/referencia ya guardada en deliverables."""
        existing = (
            self.db.supabase.table("deliverables")
            .select("id, content_json")
            .eq("category", category)
            .execute()
            .data
            or []
        )
        for row in existing:
            content = row.get("content_json") or {}
            if content.get("source_url") == source_key or content.get("url") == source_key:
                return True
        return False

    def _passes_quick_job_prefilter(self, raw_job_text: str) -> tuple[bool, str]:
        """Filtro rápido sin LLM para descartar seniorities o modalidades claramente incompatibles."""
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

    def run_job_evaluation_flow(
        self,
        raw_job_text: str,
        job_url: str,
        market: Literal["LATAM_ES", "GLOBAL_EN"] = "LATAM_ES",
        min_fit_score: int = 60,
        skip_prefilter: bool = False,
    ) -> dict:
        can_run, reason = self.db.can_run_now()
        if not can_run:
            return {
                "executed": False,
                "saved_for_approval": False,
                "duplicate": False,
                "filtered_out": False,
                "reason": reason,
            }

        if self._is_duplicate_deliverable("job_application", job_url):
            return {
                "executed": False,
                "saved_for_approval": False,
                "duplicate": True,
                "filtered_out": False,
                "reason": "La oferta ya fue evaluada previamente.",
            }

        if not skip_prefilter:
            passed, filter_reason = self._passes_quick_job_prefilter(raw_job_text)
            if not passed:
                self.db.log_execution(
                    agent_id=self.agent_id,
                    action="job_prefiltered",
                    status="skipped",
                    details=f"URL={job_url} | Motivo={filter_reason}",
                )
                return {
                    "executed": False,
                    "saved_for_approval": False,
                    "duplicate": False,
                    "filtered_out": True,
                    "reason": filter_reason,
                }

        self.db.set_agent_state(
            self.agent_id,
            status="working",
            current_task=f"Coordinando evaluación laboral con Mateo: {job_url}",
        )
        try:
            result = self.mateo.evaluate_job(
                raw_job_text=raw_job_text,
                job_url=job_url,
                market=market,
            )
            evaluation = result["evaluation"]
            fit_score = int(evaluation.get("fit_score") or 0)
            saved = False

            if evaluation.get("eligible") and fit_score >= min_fit_score:
                payload_json = {**evaluation, "source_url": job_url}
                title = f"[{fit_score}%] {evaluation.get('role_title', 'Vacante')}"
                self.db.supabase.table("deliverables").insert({
                    "agent_id": "mateo",
                    "category": "job_application",
                    "title": title,
                    "content_json": payload_json,
                    "status": "pending_approval",
                }).execute()
                saved = True

            self.db.set_agent_state(
                self.agent_id,
                status="waiting_approval" if saved else "idle",
                current_task=(
                    "Borrador laboral listo para aprobación humana"
                    if saved
                    else "Vacante evaluada sin cumplir umbral para aprobación"
                ),
            )
            return {
                "executed": True,
                "saved_for_approval": saved,
                "duplicate": False,
                "filtered_out": False,
                "provider": result.get("provider"),
                "tokens_used": result.get("tokens_used"),
                "evaluation": evaluation,
            }
        finally:
            current_status = (
                self.db.supabase.table("agent_states")
                .select("status")
                .eq("agent_id", self.agent_id)
                .single()
                .execute()
                .data
                .get("status")
            )
            if current_status == "working":
                self.db.set_agent_state(
                    self.agent_id,
                    status="idle",
                    current_task="En espera de instrucciones",
                )

    def run_prospect_evaluation_flow(
        self,
        prospect_info: str,
        source_url: str,
        channel: Literal["whatsapp", "linkedin", "web", "referral"] = "web",
        min_fit_score: int = 60,
    ) -> dict:
        can_run, reason = self.db.can_run_now()
        if not can_run:
            return {
                "executed": False,
                "saved_for_approval": False,
                "duplicate": False,
                "filtered_out": False,
                "reason": reason,
            }

        if self._is_duplicate_deliverable("client_lead", source_url):
            return {
                "executed": False,
                "saved_for_approval": False,
                "duplicate": True,
                "filtered_out": False,
                "reason": "Este prospecto/fuente ya fue evaluado previamente.",
            }

        self.db.set_agent_state(
            self.agent_id,
            status="working",
            current_task=f"Coordinando prospección con Valeria: {source_url}",
        )
        try:
            result = self.valeria.evaluate_prospect(
                prospect_info=prospect_info,
                source_url=source_url,
                channel=channel,
            )
            evaluation = result["evaluation"]
            fit_score = int(evaluation.get("fit_score") or 0)
            saved = False

            if evaluation.get("recommended") and fit_score >= min_fit_score:
                payload_json = {
                    **evaluation,
                    "source_url": source_url,
                    "channel": channel,
                }
                title = (
                    f"[{fit_score}%] "
                    f"{evaluation.get('prospect_name', 'Prospecto')} - "
                    f"{evaluation.get('opportunity_type', 'Propuesta')}"
                )
                self.db.supabase.table("deliverables").insert({
                    "agent_id": "valeria",
                    "category": "client_lead",
                    "title": title,
                    "content_json": payload_json,
                    "status": "pending_approval",
                }).execute()
                saved = True

            self.db.set_agent_state(
                self.agent_id,
                status="waiting_approval" if saved else "idle",
                current_task=(
                    "Propuesta de cliente lista para aprobación humana"
                    if saved
                    else "Prospecto evaluado sin cumplir umbral para aprobación"
                ),
            )
            return {
                "executed": True,
                "saved_for_approval": saved,
                "duplicate": False,
                "filtered_out": False,
                "provider": result.get("provider"),
                "tokens_used": result.get("tokens_used"),
                "evaluation": evaluation,
            }
        finally:
            current_status = (
                self.db.supabase.table("agent_states")
                .select("status")
                .eq("agent_id", self.agent_id)
                .single()
                .execute()
                .data
                .get("status")
            )
            if current_status == "working":
                self.db.set_agent_state(
                    self.agent_id,
                    status="idle",
                    current_task="En espera de instrucciones",
                )

    def run_batch_evaluation(
        self,
        item_type: Literal["job", "prospect"],
        items: list[dict],
        market: Literal["LATAM_ES", "GLOBAL_EN"] = "LATAM_ES",
        channel: Literal["whatsapp", "linkedin", "web", "referral"] = "web",
        min_fit_score: int = 60,
        max_items_per_batch: int = 25,
    ) -> dict:
        """Procesa un lote controlado de vacantes o prospectos y devuelve métricas claras."""
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

        sliced_items = items[:max_items_per_batch]
        saved_count = 0
        duplicates_count = 0
        filtered_count = 0
        total_tokens = 0
        results: list[dict] = []

        for idx, item in enumerate(sliced_items, start=1):
            if item_type == "job":
                url = (item.get("job_url") or item.get("url") or f"batch-job-{idx}").strip()
                text = (item.get("raw_job_text") or item.get("text") or "").strip()
                item_market = item.get("market") or market
                res = self.run_job_evaluation_flow(
                    raw_job_text=text,
                    job_url=url,
                    market=item_market,
                    min_fit_score=min_fit_score,
                )
            else:
                url = (item.get("source_url") or item.get("url") or f"batch-prospect-{idx}").strip()
                info = (item.get("prospect_info") or item.get("text") or "").strip()
                item_channel = item.get("channel") or channel
                res = self.run_prospect_evaluation_flow(
                    prospect_info=info,
                    source_url=url,
                    channel=item_channel,
                    min_fit_score=min_fit_score,
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
            "processed": len(sliced_items),
            "saved_for_approval": saved_count,
            "duplicates": duplicates_count,
            "filtered_out": filtered_count,
            "total_tokens": total_tokens,
            "results": results,
        }