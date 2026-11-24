import json
from typing import Literal

from database import DatabaseManager
from llm_router import LLMRouter


MentorMode = Literal["explain", "quiz", "interview_prep", "client_negotiation"]


class LucianoMentorAgent:
    """Mentor Técnico & Comercial: AI Engineer, Full Stack, Exámenes MC, Entrevistas y Presupuestos."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.router = LLMRouter()
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
            current_task=f"Sesión [{mode}] con Luciano sobre: {topic[:60]}",
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
            "   - Si mode='explain': explicá el concepto/código/prompt con claridad, ejemplo práctico y buenas prácticas.\n"
            "   - Si mode='quiz': generá exactamente `num_questions` preguntas multiple choice técnicas con 4 opciones cada una, "
            "una sola correcta (`correct_index` de 0 a 3) y explicación técnica de cada opción.\n"
            "   - Si mode='interview_prep': planteá un escenario de entrevista o prueba técnica realista, cómo razonarlo en voz alta, "
            "errores comunes y frases modelo para expresarte con seguridad.\n"
            "   - Si mode='client_negotiation': armá una guía práctica para cotizar (por hora/proyecto/hitos), qué aclarar por escrito "
            "y un guion profesional para defender cambios de alcance o precios sin perder al cliente.\n"
            "ESQUEMA JSON OBLIGATORIO:\n"
            "{\n"
            '  "mode": "explain | quiz | interview_prep | client_negotiation",\n'
            '  "title": "string",\n'
            '  "summary": "string",\n'
            '  "explanation_or_guide": "string (en markdown limpio para leer en UI)",\n'
            '  "code_or_prompt_example": "string (ejemplo práctico de código, prompt o guion)",\n'
            '  "quiz_questions": [\n'
            "    {\n"
            '      "question": "string",\n'
            '      "options": ["string", "string", "string", "string"],\n'
            '      "correct_index": 0,\n'
            '      "explanation": "string"\n'
            "    }\n"
            "  ],\n"
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
            response = self.router.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.35,
            )
            parsed = json.loads(response["content"])

            self.db.log_execution(
                agent_id=self.agent_id,
                action=f"mentor_{mode}",
                status="success",
                details=f"Tema={topic[:80]} | Provider={response.get('provider')}",
            )
            return {
                "provider": response.get("provider"),
                "tokens_used": response.get("tokens_used", 0),
                "session": parsed,
            }
        finally:
            self.db.set_agent_state(
                self.agent_id,
                status="idle",
                current_task="Disponible en su escritorio para mentoría y exámenes",
            )