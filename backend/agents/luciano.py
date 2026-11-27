from typing import Literal

from pydantic import BaseModel, Field

from database import DatabaseManager
from llm_router import LLMRouter


MentorMode = Literal["explain", "quiz", "interview_prep", "client_negotiation"]


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int = Field(ge=0, le=3)
    explanation: str


class MentorSession(BaseModel):
    mode: MentorMode
    title: str
    summary: str
    explanation_or_guide: str
    code_or_prompt_example: str = ""
    quiz_questions: list[QuizQuestion] = Field(default_factory=list)
    communication_tips: list[str] = Field(default_factory=list)


class LucianoMentorAgent:
    """Mentor técnico y comercial: explicaciones, quizzes, entrevistas y negociación."""

    def __init__(self, db: DatabaseManager, router: LLMRouter | None = None) -> None:
        self.db = db
        self.router = router or LLMRouter()
        self.agent_id = "luciano"

    def run_session(
        self,
        mode: MentorMode,
        topic: str,
        user_context: str = "",
        num_questions: int = 5,
    ) -> dict:
        self.db.set_agent_state(
            self.agent_id,
            status="working",
            task=f"Sesión [{mode}] con Luciano sobre: {topic[:60]}",
        )

        system_prompt = (
            "Sos Luciano, mentor senior de AI Engineering, Arquitectura Full Stack, "
            "preparación de entrevistas técnicas y negociación comercial para desarrolladores.\n"
            "Tu alumno es un desarrollador Full Stack Junior (React, TypeScript, Node.js, Python, FastAPI, SQL/Supabase, "
            "orquestación multi-agente y LLM routing) con mentalidad práctica y orientada a resultados.\n"
            "REGLAS ESTRICTAS:\n"
            "1. Respondé SIEMPRE en español rioplatense claro, directo, sin relleno.\n"
            "2. Devolvé ÚNICAMENTE un JSON válido (sin markdown alrededor ni texto extra).\n"
            "3. Adaptá el contenido al modo solicitado:\n"
            "   - explain: explicá el concepto/código/prompt con claridad, ejemplo y buenas prácticas.\n"
            "   - quiz: generá exactamente `num_questions` preguntas multiple choice con 4 opciones, "
            "una sola correcta (`correct_index` de 0 a 3) y explicación de cada opción.\n"
            "   - interview_prep: planteá un escenario realista, cómo razonarlo, errores comunes y frases modelo.\n"
            "   - client_negotiation: guía para cotizar por hora/proyecto/hitos, qué aclarar por escrito "
            "y un guion para defender cambios de alcance sin perder al cliente.\n"
            "ESQUEMA JSON OBLIGATORIO:\n"
            "{\n"
            '  "mode": "explain | quiz | interview_prep | client_negotiation",\n'
            '  "title": "string",\n'
            '  "summary": "string",\n'
            '  "explanation_or_guide": "string",\n'
            '  "code_or_prompt_example": "string",\n'
            '  "quiz_questions": [{"question":"string","options":["a","b","c","d"],'
            '"correct_index":0,"explanation":"string"}],\n'
            '  "communication_tips": ["string"]\n'
            "}"
        )

        user_prompt = (
            f"Modo: {mode}\n"
            f"Tema / Consulta: {topic}\n"
            f"Cantidad de preguntas (si mode='quiz'): {num_questions}\n"
            f"Contexto adicional del alumno: {user_context or 'Sin contexto extra'}"
        )

        try:
            response = self.router.ask(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                temperature=0.35,
                json_mode=True,
            )
            parsed = MentorSession.model_validate(response.get("json_data") or {})
            tokens_used = int(response.get("tokens_used") or 0)
            self.db.log_execution(
                agent_id=self.agent_id,
                action=f"mentor_{mode}",
                status="success",
                details=f"Tema={topic[:80]} | Provider={response.get('provider')}",
            )
            return {
                "provider": response.get("provider"),
                "tokens_used": tokens_used,
                "session": parsed.model_dump(),
                "activity": [
                    {
                        "action": f"sesión {mode}",
                        "topic": topic[:120],
                        "status": "completed",
                    }
                ],
            }
        except Exception as exc:
            self.db.log_execution(
                agent_id=self.agent_id,
                action=f"mentor_{mode}",
                status="error",
                details=str(exc),
            )
            raise
        finally:
            self.db.set_agent_state(
                self.agent_id,
                status="idle",
                task="Disponible en su escritorio para mentoría y exámenes",
            )
