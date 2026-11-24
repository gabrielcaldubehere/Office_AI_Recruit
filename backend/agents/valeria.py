from typing import Literal
from pydantic import BaseModel, Field

from database import DatabaseManager
from llm_router import LLMRouter


class ClientOpportunityEvaluation(BaseModel):
    prospect_name: str
    niche: str
    opportunity_type: str
    fit_score: int = Field(ge=0, le=100)
    recommended: bool
    pain_points: list[str]
    proposed_solution: str
    outreach_draft: str
    missing_info: list[str]
    next_steps: list[str]


class ValeriaHunterAgent:
    """Agente especializado en detectar y estructurar oportunidades de clientes."""

    def __init__(self, db: DatabaseManager, router: LLMRouter) -> None:
        self.db = db
        self.router = router
        self.agent_id = "valeria"

    def evaluate_prospect(
        self,
        prospect_info: str,
        source_url: str,
        channel: Literal["whatsapp", "linkedin", "web", "referral"] = "web",
    ) -> dict:
        self.db.set_agent_state(
            self.agent_id,
            status="working",
            current_task=f"Analizando prospecto ({channel}): {source_url}",
        )

        try:
            prompt = (
                f"Canal de origen: {channel}\n"
                f"URL o referencia única: {source_url}\n"
                f"Información del prospecto:\n{prospect_info}\n\n"
                "Evalúa esta oportunidad de forma objetiva y genera el JSON solicitado."
            )

            llm_response = self.router.ask(
                prompt=prompt,
                skill_file="valeria_client_hunter.md",
                temperature=0.2,
                json_mode=True,
            )

            raw_json = llm_response.get("json_data") or {}
            parsed = ClientOpportunityEvaluation(**raw_json)
            tokens_used = int(llm_response.get("tokens_used") or 0)

            self.db.add_tokens_used(tokens_used)
            self.db.log_execution(
                agent_id=self.agent_id,
                action="prospect_evaluated",
                status="success",
                details=(
                    f"Prospecto={parsed.prospect_name} | Score={parsed.fit_score} | "
                    f"Provider={llm_response.get('provider')} | Tokens={tokens_used}"
                ),
            )

            return {
                "evaluation": parsed.model_dump(),
                "provider": llm_response.get("provider"),
                "model": llm_response.get("model"),
                "tokens_used": tokens_used,
            }

        except Exception as exc:
            self.db.log_execution(
                agent_id=self.agent_id,
                action="prospect_evaluated",
                status="error",
                details=str(exc),
            )
            raise
        finally:
            self.db.set_agent_state(
                self.agent_id,
                status="idle",
                current_task="En espera de instrucciones",
            )