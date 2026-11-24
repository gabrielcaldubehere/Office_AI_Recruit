import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

for env_path in (BACKEND_DIR / ".env", ROOT_DIR / ".env"):
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)

from agents.luciano import LucianoMentorAgent, MentorMode  # noqa: E402
from agents.sara import SaraOrchestrator  # noqa: E402
from auth import (  # noqa: E402
    create_session_token,
    require_authenticated_operator,
    verify_password,
)
from database import DatabaseManager  # noqa: E402


def _parse_cors_origins() -> List[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="AI Office Backend API",
    description="Orquestación multi-agente (Sara, Mateo, Valeria, Luciano), briefing público y aprobación humana.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DatabaseManager()
sara = SaraOrchestrator()
luciano = LucianoMentorAgent(db)


# ---------------------------------------------------------------------------
# Modelos de entrada (Pydantic)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, description="Usuario de operador")
    password: str = Field(min_length=1, description="Contraseña en texto plano verificada contra hash")


class BatchItemInput(BaseModel):
    job_url: Optional[str] = None
    raw_job_text: Optional[str] = None
    client_ref: Optional[str] = None
    raw_client_text: Optional[str] = None
    source: Optional[str] = None
    market: Optional[Literal["LATAM_ES", "GLOBAL_EN"]] = None


class BatchEvaluateRequest(BaseModel):
    item_type: Literal["job", "client"] = Field(description="Tipo de lote: 'job' o 'client'")
    items: List[BatchItemInput] = Field(min_length=1, max_length=50)
    market: Literal["LATAM_ES", "GLOBAL_EN"] = Field(default="GLOBAL_EN")
    min_fit_score: int = Field(default=60, ge=0, le=100)
    max_items_per_batch: int = Field(default=25, ge=1, le=50)


class ReviewActionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: Optional[str] = Field(default="", max_length=1000)


class MentorSessionRequest(BaseModel):
    mode: MentorMode = Field(description="explain | quiz | interview_prep | client_negotiation")
    topic: str = Field(min_length=3, max_length=2000)
    user_context: Optional[str] = Field(default="", max_length=3000)
    num_questions: int = Field(default=5, ge=1, le=10)


# ---------------------------------------------------------------------------
# Rutas públicas (Portfolio / Briefing sin ejecución de acciones)
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "ai-office-api",
    }


@app.get("/api/office/public-summary")
def get_public_office_summary() -> Dict[str, Any]:
    """
    Devuelve el estado de los agentes y un resumen del día para mostrar la oficina
    como proyecto/portfolio sin habilitar acciones ni exponer datos sensibles.
    """
    try:
        agents_raw = db.get_agent_states() if hasattr(db, "get_agent_states") else []
        pending_items = (
            db.list_deliverables(status="pending_approval")
            if hasattr(db, "list_deliverables")
            else []
        )

        job_items = [
            item for item in pending_items
            if item.get("category") in ("job_application", "job")
        ]
        client_items = [
            item for item in pending_items
            if item.get("category") not in ("job_application", "job")
        ]

        sara_message = (
            f"Hoy Mateo ha encontrado {len(job_items)} posiciones laborales que te podrían interesar "
            f"y Valeria encontró {len(client_items)} oportunidades de clientes esperando tu aprobación."
        )

        return {
            "mode": "public_showcase",
            "actions_enabled": False,
            "agents": agents_raw,
            "daily_briefing": {
                "sara_message": sara_message,
                "jobs_count": len(job_items),
                "clients_count": len(client_items),
                "jobs_preview": [
                    {
                        "id": item.get("id"),
                        "title": item.get("title") or "Posición laboral detectada",
                        "source": item.get("source") or "Portal",
                        "fit_score": item.get("fit_score"),
                        "summary": (item.get("summary") or "")[:180],
                    }
                    for item in job_items[:10]
                ],
                "clients_preview": [
                    {
                        "id": item.get("id"),
                        "title": item.get("title") or "Oportunidad de cliente",
                        "source": item.get("source") or "Canal",
                        "summary": (item.get("summary") or "")[:180],
                    }
                    for item in client_items[:10]
                ],
            },
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo construir el resumen público de la oficina: {exc}",
        )


# ---------------------------------------------------------------------------
# Autenticación de operador
# ---------------------------------------------------------------------------

@app.post("/api/auth/login")
def login_operator(payload: LoginRequest) -> Dict[str, Any]:
    expected_user = os.getenv("OFFICE_ADMIN_USER", "gabriel").strip()
    expected_hash = os.getenv("OFFICE_ADMIN_PASSWORD_HASH", "").strip()

    if not expected_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OFFICE_ADMIN_PASSWORD_HASH no está configurado en el servidor.",
        )

    if payload.username != expected_user or not verify_password(payload.password, expected_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )

    token = create_session_token(username=payload.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "operator": payload.username,
    }


@app.get("/api/auth/me")
def get_current_operator(operator: Dict[str, Any] = Depends(require_authenticated_operator)) -> Dict[str, Any]:
    return {
        "authenticated": True,
        "operator": operator.get("sub"),
        "role": operator.get("role", "admin"),
    }


# ---------------------------------------------------------------------------
# Rutas protegidas (Requieren inicio de sesión del operador)
# ---------------------------------------------------------------------------

@app.get("/api/deliverables")
def list_deliverables(
    deliverable_status: Optional[str] = "pending_approval",
    operator: Dict[str, Any] = Depends(require_authenticated_operator),
) -> Dict[str, Any]:
    if not hasattr(db, "list_deliverables"):
        raise HTTPException(status_code=501, detail="Método list_deliverables no disponible.")
    items = db.list_deliverables(status=deliverable_status)
    return {
        "operator": operator.get("sub"),
        "status": deliverable_status,
        "count": len(items),
        "items": items,
    }


@app.post("/api/office/batch-evaluate")
def run_batch_evaluation(
    payload: BatchEvaluateRequest,
    operator: Dict[str, Any] = Depends(require_authenticated_operator),
) -> Dict[str, Any]:
    """Ejecuta evaluación por lote de vacantes o clientes solo para el operador autenticado."""
    try:
        serialized_items = [item.model_dump(exclude_none=True) for item in payload.items]
        result = sara.run_batch_evaluation(
            item_type=payload.item_type,
            items=serialized_items,
            market=payload.market,
            min_fit_score=payload.min_fit_score,
            max_items_per_batch=payload.max_items_per_batch,
        )
        return {
            "operator": operator.get("sub"),
            "result": result,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al ejecutar evaluación por lote: {exc}",
        )


@app.post("/api/deliverables/{deliverable_id}/review")
def review_deliverable(
    deliverable_id: str,
    payload: ReviewActionRequest,
    operator: Dict[str, Any] = Depends(require_authenticated_operator),
) -> Dict[str, Any]:
    """
    Aprueba o rechaza un entregable. Cuando se aprueba, ejecuta el paso final
    de automatización / preparación con intervención humana previa.
    """
    if not hasattr(db, "get_deliverable") or not hasattr(db, "update_deliverable_status"):
        raise HTTPException(status_code=501, detail="Métodos de entregables no configurados.")

    item = db.get_deliverable(deliverable_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entregable no encontrado.")

    updated = db.update_deliverable_status(
        deliverable_id=deliverable_id,
        status=payload.decision,
        reviewer_notes=payload.notes or "",
    )

    execution_result = None
    if payload.decision == "approved":
        if hasattr(sara, "execute_approved_deliverable"):
            execution_result = sara.execute_approved_deliverable(
                item=updated,
                operator=operator.get("sub", "gabriel"),
            )
        elif hasattr(db, "log_execution"):
            db.log_execution(
                agent_id="sara",
                action="deliverable_approved_final_step",
                status="success",
                details=f"Aprobado entregable {deliverable_id} por {operator.get('sub')}",
            )
            execution_result = {"executed": True, "deliverable_id": deliverable_id}

    return {
        "status": payload.decision,
        "operator": operator.get("sub"),
        "deliverable": updated,
        "execution": execution_result,
    }


@app.post("/api/agents/luciano/session")
def run_luciano_session(
    payload: MentorSessionRequest,
    operator: Dict[str, Any] = Depends(require_authenticated_operator),
) -> Dict[str, Any]:
    """Ejecuta una sesión con Luciano (explicación, quiz MC, entrevistas o presupuestos)."""
    try:
        result = luciano.run_session(
            mode=payload.mode,
            topic=payload.topic,
            user_context=payload.user_context or "",
            num_questions=payload.num_questions,
        )
        return {
            "operator": operator.get("sub"),
            **result,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error ejecutando sesión con Luciano: {exc}",
        )