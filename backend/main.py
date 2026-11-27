import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
from automation import AutomationController  # noqa: E402
from auth import create_session_token, verify_password  # noqa: E402
import control_drafts  # noqa: E402
from database import DatabaseManager  # noqa: E402
from fetch_remote_jobs import fetch_remoteok_jobs, fetch_wwr_jobs  # noqa: E402
from gmail_bridge import GmailBridge  # noqa: E402
from job_sources import (  # noqa: E402
    UPWORK_RSS_DEPRECATED,
    age_check,
    collect_freelance_platforms,
    deduplicate,
    fetch_freelancer_rss,
    fetch_upwork_rss,
    load_structured_batch,
)


def _parse_cors_origins() -> List[str]:
    raw = os.getenv("CORS_ORIGINS") or os.getenv("ALLOWED_ORIGINS") or ""
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ]
    if "*" in origins:
        return ["*"]
    return origins


app = FastAPI(
    title="AI Office Backend API",
    description="Oficina 1: Sara, Mateo, Valeria y Luciano. Briefing público y acciones con aprobación humana.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials="*" not in _parse_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DatabaseManager()
sara = SaraOrchestrator(db)
luciano = LucianoMentorAgent(db, sara.router)
gmail_bridge = GmailBridge(db)
bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class BatchItemInput(BaseModel):
    job_url: Optional[str] = None
    raw_job_text: Optional[str] = None
    client_ref: Optional[str] = None
    raw_client_text: Optional[str] = None
    source: Optional[str] = None
    source_platform: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    company_or_client_name: Optional[str] = None
    contact_channel: Optional[str] = None
    contact_ref: Optional[str] = None
    market: Optional[Literal["LATAM_ES", "GLOBAL_EN"]] = None
    channel: Optional[str] = None


class BatchEvaluateRequest(BaseModel):
    item_type: Literal["job", "client"]
    items: List[BatchItemInput] = Field(min_length=1, max_length=50)
    market: Literal["LATAM_ES", "GLOBAL_EN"] = "GLOBAL_EN"
    min_fit_score: int = Field(default=60, ge=0, le=100)
    max_items_per_batch: int = Field(default=25, ge=1, le=50)


class ReviewActionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: Optional[str] = Field(default="", max_length=1000)


class MentorSessionRequest(BaseModel):
    mode: MentorMode
    topic: str = Field(min_length=3, max_length=2000)
    user_context: Optional[str] = Field(default="", max_length=3000)
    num_questions: int = Field(default=5, ge=1, le=10)


class AgentStateOut(BaseModel):
    agent_id: str
    display_name: Optional[str] = None
    role: Optional[str] = None
    status: str
    current_task: Optional[str] = None


class TraceabilityOut(BaseModel):
    source_platform: str
    source_url: Optional[str] = None
    company_or_client_name: str
    contact_channel: str
    contact_ref: str
    contact_pending: bool = False


class PreviewItemOut(BaseModel):
    id: str
    title: str
    source: str
    fit_score: Optional[int] = None
    summary: str
    category: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    traceability: TraceabilityOut


class DailyBriefingOut(BaseModel):
    sara_message: str
    jobs_count: int
    clients_count: int
    jobs_preview: List[PreviewItemOut]
    clients_preview: List[PreviewItemOut]
    reports_ready: int


class FollowUpSummaryOut(BaseModel):
    sent: int = 0
    awaiting_reply: int = 0
    responded: int = 0
    novedades: int = 0
    closed: int = 0
    total: int = 0


class TokenAlertOut(BaseModel):
    alert: bool
    exhausted: bool
    used: int
    limit: int
    remaining: int
    ratio: float
    threshold: float
    message: str


class FindingOut(BaseModel):
    agent: str
    title: str
    source_platform: str
    source_url: Optional[str] = None
    application_status: str
    message: str


class AdvisorOut(BaseModel):
    token_alert: TokenAlertOut
    suggestions: List[str]
    findings: List[FindingOut]


class AutomationPauseRequest(BaseModel):
    reason: str = Field(default="Pausado manualmente por el operador", max_length=500)


class AutomationActionOut(BaseModel):
    status: Dict[str, Any]


class PublicSummaryOut(BaseModel):
    mode: str
    actions_enabled: bool
    agents: List[AgentStateOut]
    daily_briefing: DailyBriefingOut
    follow_up: FollowUpSummaryOut
    advisor: AdvisorOut


class LoginOut(BaseModel):
    access_token: str
    token_type: str
    operator: str


class MeOut(BaseModel):
    authenticated: bool
    operator: str
    role: str


class DeliverableOut(BaseModel):
    id: str
    agent_id: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    fit_score: Optional[int] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    traceability: TraceabilityOut


class OutreachRecordOut(BaseModel):
    id: str
    agent_id: str
    category: str
    title: str
    recipient: str
    source_platform: str
    source_url: Optional[str] = None
    source_url_of_application: Optional[str] = None
    company_or_client_name: str
    contact_channel: str
    contact_ref: str
    contact_ref_pending: bool = False
    full_text: str
    summary: str
    cv_reference: Optional[str] = None
    attachment_reference: Optional[str] = None
    draft_attachments: List[Dict[str, Any]] = Field(default_factory=list)
    hourly_rate_usd: Optional[int] = None
    rate_model: Optional[str] = None
    status: str
    gmail_message_id: Optional[str] = None
    gmail_thread_id: Optional[str] = None
    gmail_label: Optional[str] = None
    last_response_at: Optional[str] = None
    notes: Optional[str] = None
    operator: Optional[str] = None
    created_at: Optional[str] = None


class OutreachListOut(BaseModel):
    operator: str
    count: int
    items: List[OutreachRecordOut]
    reason: Optional[str] = None


class OutreachStatusRequest(BaseModel):
    status: Literal[
        "enviado",
        "espera_respuesta",
        "respondido",
        "novedad_detectada",
        "cerrado",
        "pending_approval",
        "approved",
        "rejected",
    ]
    notes: Optional[str] = Field(default="", max_length=1000)


class GmailStatusOut(BaseModel):
    enabled: bool
    account: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    reason: Optional[str] = None


class GmailSyncOut(BaseModel):
    checked: bool
    updates: List[Dict[str, Any]] = Field(default_factory=list)
    reason: Optional[str] = None


class GmailRegisterRequest(BaseModel):
    outreach_id: str = Field(min_length=1)
    gmail_message_id: str = Field(min_length=1)
    label: Literal["Clientes", "Postulaciones"]


class GmailRegisterOut(BaseModel):
    external_action: str
    gmail: Optional[Dict[str, str]] = None
    outreach: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class GmailDraftRequest(BaseModel):
    outreach_id: str = Field(min_length=1)
    operator_confirmed: bool = Field(default=False)


class GmailDraftOut(BaseModel):
    external_action: str
    draft_id: str = ""
    to: str = ""
    subject: str = ""
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    reason: Optional[str] = None


class SourceCollectRequest(BaseModel):
    platform: Literal["upwork", "freelancer", "remoteok", "wwr", "all"] = "all"
    item_type: Literal["client", "job"] = "client"
    upwork_limit: int = Field(default=10, ge=1, le=25)
    freelancer_limit: int = Field(default=10, ge=1, le=25)
    evaluate: bool = False
    market: Literal["LATAM_ES", "GLOBAL_EN"] = "LATAM_ES"
    min_fit_score: int = Field(default=60, ge=0, le=100)
    max_items_per_batch: int = Field(default=25, ge=1, le=50)


class StructuredBatchRequest(SourceCollectRequest):
    path: str = Field(min_length=1)
    platform_name: str = "Fuente estructurada"


class SourceCollectOut(BaseModel):
    platform: str
    fetched: int
    prefiltered_out: int
    items: List[Dict[str, Any]]
    evaluate: bool
    notes: List[str] = Field(default_factory=list)
    batch: Optional[Dict[str, Any]] = None


class DeliverablesOut(BaseModel):
    operator: str
    status: str
    count: int
    items: List[DeliverableOut]


class ReviewOut(BaseModel):
    status: str
    operator: str
    deliverable: Dict[str, Any]
    execution: Optional[Dict[str, Any]] = None
    message: str


class BatchOut(BaseModel):
    operator: str
    result: Dict[str, Any]
    age_filtered: int = 0


class LucianoOut(BaseModel):
    operator: str
    provider: Optional[str] = None
    tokens_used: Optional[int] = None
    session: Dict[str, Any]
    activity: List[Dict[str, Any]] = Field(default_factory=list)


def require_operator(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    from auth import decode_and_verify_token

    token = credentials.credentials if credentials else None
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere iniciar sesión como operador para ejecutar acciones.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_and_verify_token(token)


NOT_STATED = "No figura en la fuente"


def _trace(item: Dict[str, Any]) -> TraceabilityOut:
    return TraceabilityOut(
        source_platform=str(item.get("source_platform") or item.get("source") or NOT_STATED),
        source_url=item.get("source_url") or item.get("url"),
        company_or_client_name=str(
            item.get("company_or_client_name") or item.get("company") or item.get("prospect_name") or NOT_STATED
        ),
        contact_channel=str(item.get("contact_channel") or item.get("channel") or NOT_STATED),
        contact_ref=str(item.get("contact_ref") or NOT_STATED),
        contact_pending=bool(item.get("contact_pending", item.get("contact_ref", NOT_STATED) == NOT_STATED)),
    )


def _preview(item: Dict[str, Any]) -> PreviewItemOut:
    return PreviewItemOut(
        id=str(item.get("id") or ""),
        title=str(item.get("title") or "Oportunidad detectada"),
        source=str(item.get("source_platform") or item.get("source") or NOT_STATED),
        fit_score=item.get("fit_score") if isinstance(item.get("fit_score"), int) else None,
        summary=str(item.get("summary") or "")[:180],
        category=item.get("category"),
        content=item.get("content"),
        traceability=_trace(item),
    )


def _outreach_out(record: Dict[str, Any]) -> OutreachRecordOut:
    contact_ref = str(record.get("contact_ref") or NOT_STATED)
    return OutreachRecordOut(
        id=str(record.get("id") or ""),
        agent_id=str(record.get("agent_id") or "sara"),
        category=str(record.get("category") or "client_lead"),
        title=str(record.get("title") or "Registro de seguimiento"),
        recipient=str(record.get("recipient") or contact_ref),
        source_platform=str(record.get("source_platform") or NOT_STATED),
        source_url=record.get("source_url"),
        source_url_of_application=record.get("source_url_of_application"),
        company_or_client_name=str(record.get("company_or_client_name") or NOT_STATED),
        contact_channel=str(record.get("contact_channel") or NOT_STATED),
        contact_ref=contact_ref,
        contact_ref_pending=bool(record.get("contact_ref_pending", contact_ref == NOT_STATED)),
        full_text=str(record.get("full_text") or ""),
        summary=str(record.get("summary") or ""),
        cv_reference=record.get("cv_reference"),
        attachment_reference=record.get("attachment_reference"),
        draft_attachments=control_drafts.attachments_from_record(record),
        hourly_rate_usd=record.get("hourly_rate_usd"),
        rate_model=record.get("rate_model"),
        status=str(record.get("status") or "pending_approval"),
        gmail_message_id=record.get("gmail_message_id"),
        gmail_thread_id=record.get("gmail_thread_id"),
        gmail_label=record.get("gmail_label"),
        last_response_at=record.get("last_response_at"),
        notes=record.get("notes"),
        operator=record.get("operator"),
        created_at=record.get("created_at"),
    )


def _content_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    content = item.get("content_json") or {}
    if not isinstance(content, dict):
        content = {}
    for key in item.get("_context_fields") or []:
        content.setdefault(key, item.get(key))
    return content


def _build_outreach_record(item: Dict[str, Any], operator: str) -> Dict[str, Any]:
    content = _content_from_item(item)
    is_job = item.get("category") == "job_application"
    trace = _trace({**item, **content})
    title = str(item.get("title") or content.get("role_title") or "Registro de seguimiento")
    if is_job:
        full_text = "\n".join(
            [
                str(content.get("tailored_summary") or ""),
                *[str(arg) for arg in (content.get("match_arguments") or [])],
                str(content.get("application_instructions") or ""),
            ]
        ).strip()
        rate_model = None
        cv_reference = content.get("cv_reference")
    else:
        variants = content.get("outreach_variants") or []
        full_text = str(
            content.get("outreach_draft")
            or (variants[0].get("body") if variants and isinstance(variants[0], dict) else "")
            or item.get("summary")
            or ""
        )
        rate_model = "; ".join(
            str(m.get("model") or "")
            for m in (content.get("delivery_modalities") or [])
            if isinstance(m, dict) and m.get("model")
        ) or None
        cv_reference = None
    return {
        "agent_id": str(item.get("agent_id") or ("mateo" if is_job else "valeria")),
        "category": "job_application" if is_job else "client_lead",
        "title": title,
        "recipient": trace.contact_ref,
        "source_platform": trace.source_platform,
        "source_url": trace.source_url,
        "source_url_of_application": content.get("source_url") or item.get("source_url"),
        "company_or_client_name": trace.company_or_client_name,
        "contact_channel": trace.contact_channel,
        "contact_ref": trace.contact_ref,
        "contact_ref_pending": trace.contact_pending,
        "full_text": full_text[:8000],
        "summary": str(item.get("summary") or content.get("summary") or "")[:1200],
        "cv_reference": cv_reference,
        "hourly_rate_usd": content.get("hourly_rate_usd"),
        "rate_model": rate_model,
        "operator": operator,
        "status": "pending_approval",
        "notes": "Registro preparado tras aprobación humana; sin envío externo automático.",
    }


def _store_control_draft(spec: Dict[str, Any], action: str, details: str) -> Optional[Dict[str, Any]]:
    try:
        stored = control_drafts.store_control_draft(db, spec)
        if not stored:
            return None
        db.log_execution(
            agent_id="sara",
            action=action,
            status="success",
            details=details[:1000],
        )
        return _outreach_out(stored)
    except Exception as exc:
        db.log_execution(
            agent_id="sara",
            action=action,
            status="error",
            details=str(exc)[:1000],
        )
        return None


def _attach_batch_control_draft(
    result: Dict[str, Any],
    item_type: str,
    items: List[Any],
    operator: str,
    age_filtered: int = 0,
) -> None:
    if not db.outreach_available:
        return
    platforms: List[str] = []
    for item in items:
        if isinstance(item, dict):
            platform = str(item.get("source_platform") or item.get("source") or "").strip()
        else:
            platform = str(getattr(item, "source_platform", "") or getattr(item, "source", "") or "").strip()
        if platform and platform not in platforms:
            platforms.append(platform)
    spec = control_drafts.build_batch_control_spec(
        item_type=item_type,
        result=result,
        age_filtered=age_filtered,
        platforms=platforms,
        operator=operator,
    )
    control = _store_control_draft(
        spec,
        "gmail_control_batch_prepared",
        f"item_type={item_type} | agenda={control_drafts.ACCOUNT_EMAIL} | sin envío automático",
    )
    if control:
        result["control_draft"] = control


def _follow_up_summary() -> FollowUpSummaryOut:
    records = db.list_outreach()
    counts = {
        "enviado": 0,
        "espera_respuesta": 0,
        "respondido": 0,
        "novedad_detectada": 0,
        "cerrado": 0,
    }
    for record in records:
        status = str(record.get("status") or "")
        if status in counts:
            counts[status] += 1
    return FollowUpSummaryOut(
        sent=counts["enviado"],
        awaiting_reply=counts["espera_respuesta"],
        responded=counts["respondido"],
        novedades=counts["novedad_detectada"],
        closed=counts["cerrado"],
        total=len(records),
    )


def _application_status(item: Dict[str, Any]) -> str:
    mapping = {
        "enviado": "Enviado/registrado; falta confirmar respuesta",
        "espera_respuesta": "Postulado y en espera de respuesta",
        "respondido": "Respondido; Sara detectó novedades en Gmail",
        "novedad_detectada": "Novedad detectada en un hilo sin registro previo; requiere revisión manual",
        "cerrado": "Cerrado",
        "pending_approval": "Pendiente de aprobación del operador",
        "approved": "Aprobado; pendiente de registro humano",
        "rejected": "Rechazado por el operador",
    }
    source_url = str(item.get("source_url") or item.get("job_url") or item.get("url") or "")
    title = str(item.get("title") or "")
    records = db.list_outreach() if db.outreach_available else []
    for record in records:
        record_urls = (
            str(record.get("source_url") or ""),
            str(record.get("source_url_of_application") or ""),
        )
        if (source_url and source_url in record_urls) or (
            title and title == str(record.get("title") or "")
        ):
            status = str(record.get("status") or "")
            return mapping.get(status, f"Registrado como {status or 'sin estado'}")
    trace = _trace(item)
    if not trace.source_url and trace.contact_ref == NOT_STATED:
        return "No postulado aún / sin contacto o enlace directo"
    return "Pendiente de aprobación del operador"


def _advisor_summary(jobs: List[Dict[str, Any]], clients: List[Dict[str, Any]]) -> AdvisorOut:
    budget = db.token_budget()
    token_alert = TokenAlertOut(
        alert=bool(budget["alert"]),
        exhausted=bool(budget["exhausted"]),
        used=int(budget["used"]),
        limit=int(budget["limit"]),
        remaining=int(budget["remaining"]),
        ratio=float(budget["ratio"]),
        threshold=float(budget["threshold"]),
        message=str(budget["message"]),
    )
    findings: List[FindingOut] = []
    for is_job, group in ((True, jobs), (False, clients)):
        for item in group[:6]:
            trace = _trace(item)
            title = str(item.get("title") or "Oportunidad detectada")
            agent = "Mateo" if is_job else "Valeria"
            status = _application_status(item)
            findings.append(FindingOut(
                agent=agent,
                title=title,
                source_platform=trace.source_platform,
                source_url=trace.source_url,
                application_status=status,
                message=f"{agent} encontró “{title}” en {trace.source_platform}. {status}.",
            ))
    suggestions: List[str] = []
    if token_alert.alert:
        suggestions.append(token_alert.message)
    if jobs:
        suggestions.append(f"Aprobá primero {len(jobs)} propuesta(s) laboral(es) de Mateo; son las más recientes.")
    if clients:
        suggestions.append(f"Después revisá {len(clients)} cliente(s) de Valeria con tarifa y modalidades calculadas.")
    if db.outreach_available:
        responded = db.list_outreach(status="respondido")
        if responded:
            suggestions.append(f"Hay {len(responded)} respuesta(s) en Gmail que requieren continuación humana.")
        novedades = db.list_outreach(status="novedad_detectada")
        if novedades:
            suggestions.append(
                f"Sara detectó {len(novedades)} novedad(es) en hilos sin registro previo; revisá Seguimiento."
            )
    if not suggestions:
        suggestions.append("Sara no ve pendientes críticos: podés seguir en modo público o iniciar sesión para lanzar nuevas corridas.")
    return AdvisorOut(token_alert=token_alert, suggestions=suggestions[:5], findings=findings[:8])


def _auto_job_cycle() -> Dict[str, Any]:
    limit = max(1, int(os.getenv("AUTO_JOB_LIMIT", "10")))
    collected: List[Dict[str, Any]] = []
    for source_name, fetch in (
        ("RemoteOK", lambda: fetch_remoteok_jobs(limit=limit)),
        ("WeWorkRemotely", lambda: fetch_wwr_jobs(limit_per_feed=max(1, limit // 3))),
        ("Freelancer/Upwork", lambda: collect_freelance_platforms(
            upwork_limit=limit,
            freelancer_limit=limit,
            item_type="job",
        )),
    ):
        try:
            collected.extend(fetch())
        except Exception as exc:
            db.log_execution(
                agent_id="mateo",
                action="auto_source_error",
                status="error",
                details=f"{source_name}: {exc}",
            )
    items = deduplicate(collected)
    result = sara.run_batch_evaluation(
        item_type="job",
        items=items,
        market="GLOBAL_EN",
        min_fit_score=int(os.getenv("AUTO_MIN_FIT_SCORE", "60")),
        max_items_per_batch=limit,
    )
    _attach_batch_control_draft(result, "job", items, "automatización")
    return {"source": "automatic", "fetched": len(items), "result": result}


def _auto_client_cycle() -> Dict[str, Any]:
    limit = max(1, int(os.getenv("AUTO_CLIENT_LIMIT", "10")))
    try:
        collected = collect_freelance_platforms(
            upwork_limit=limit,
            freelancer_limit=limit,
            item_type="client",
        )
    except Exception as exc:
        db.log_execution(
            agent_id="valeria",
            action="auto_source_error",
            status="error",
            details=str(exc),
        )
        collected = []
    items = deduplicate(collected)
    result = sara.run_batch_evaluation(
        item_type="client",
        items=items,
        market="LATAM_ES",
        min_fit_score=int(os.getenv("AUTO_MIN_FIT_SCORE", "60")),
        max_items_per_batch=limit,
    )
    _attach_batch_control_draft(result, "client", items, "automatización")
    return {"source": "automatic", "fetched": len(items), "result": result}


automation = AutomationController(
    db,
    {"mateo": _auto_job_cycle, "valeria": _auto_client_cycle},
)


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "ai-office-api"}


@app.get("/api/office/public-summary", response_model=PublicSummaryOut)
def get_public_office_summary() -> PublicSummaryOut:
    """Vista pública: estados y reportes del día, sin exponer acciones operativas."""
    try:
        agents_raw = db.get_agent_states()
        pending_items = db.list_deliverables(status="pending_approval")
        jobs = [i for i in pending_items if i.get("category") in ("job_application", "job")]
        clients = [i for i in pending_items if i.get("category") not in ("job_application", "job")]
        report_count = len(pending_items)

        return PublicSummaryOut(
            mode="public_showcase",
            actions_enabled=False,
            agents=[
                AgentStateOut(
                    agent_id=str(a.get("agent_id") or ""),
                    display_name=a.get("display_name"),
                    role=a.get("role"),
                    status=str(a.get("status") or "idle"),
                    current_task=a.get("current_task") or "En espera de instrucciones",
                )
                for a in agents_raw
            ],
            daily_briefing=DailyBriefingOut(
                sara_message=(
                    f"Hoy Mateo tiene {len(jobs)} vacantes y Valeria {len(clients)} oportunidades "
                    f"en espera de aprobación. Hay {report_count} reportes listos para revisar."
                ),
                jobs_count=len(jobs),
                clients_count=len(clients),
                jobs_preview=[_preview(i) for i in jobs[:10]],
                clients_preview=[_preview(i) for i in clients[:10]],
                reports_ready=report_count,
            ),
            follow_up=_follow_up_summary(),
            advisor=_advisor_summary(jobs, clients),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo construir el resumen público de la oficina: {exc}",
        )


@app.post("/api/auth/login", response_model=LoginOut)
def login_operator(payload: LoginRequest) -> LoginOut:
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
    try:
        automation.start(trigger="login")
    except Exception as exc:
        db.log_execution(
            agent_id="sara",
            action="automation_start_error",
            status="error",
            details=f"login: {exc}",
        )
    return LoginOut(
        access_token=create_session_token(username=payload.username),
        token_type="bearer",
        operator=payload.username,
    )


@app.get("/api/auth/me", response_model=MeOut)
def get_current_operator(operator: Dict[str, Any] = Depends(require_operator)) -> MeOut:
    return MeOut(
        authenticated=True,
        operator=str(operator.get("sub") or ""),
        role=str(operator.get("role") or "admin"),
    )


@app.get("/api/deliverables", response_model=DeliverablesOut)
def list_deliverables(
    deliverable_status: Optional[str] = "pending_approval",
    operator: Dict[str, Any] = Depends(require_operator),
) -> DeliverablesOut:
    items = db.list_deliverables(status=deliverable_status)
    return DeliverablesOut(
        operator=str(operator.get("sub") or ""),
        status=deliverable_status or "all",
        count=len(items),
        items=[
            DeliverableOut(
                id=str(i.get("id") or ""),
                agent_id=i.get("agent_id"),
                category=i.get("category"),
                title=i.get("title"),
                source=i.get("source"),
                source_url=i.get("source_url"),
                fit_score=i.get("fit_score"),
                summary=i.get("summary"),
                status=i.get("status"),
                content={k: v for k, v in i.items() if k == "content_json" or k in (i.get("_context_fields") or [])},
                traceability=_trace(i),
            )
            for i in items
        ],
    )


@app.post("/api/office/batch-evaluate", response_model=BatchOut)
def run_batch_evaluation(
    payload: BatchEvaluateRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> BatchOut:
    try:
        raw_items = [item.model_dump(exclude_none=True) for item in payload.items]
        recent_items: List[Dict[str, Any]] = []
        for item in raw_items:
            within_age, _ = age_check(item)
            if within_age:
                recent_items.append(item)
        if not recent_items:
            return BatchOut(
                operator=str(operator.get("sub") or ""),
                result={
                    "processed": 0,
                    "saved_for_approval": 0,
                    "duplicates": 0,
                    "filtered_out": len(raw_items),
                    "total_tokens": 0,
                    "reason": "Todas las fuentes quedaron fuera del filtro estricto de 15 días",
                    "results": [],
                },
                age_filtered=len(raw_items),
            )
        result = sara.run_batch_evaluation(
            item_type=payload.item_type,
            items=recent_items,
            market=payload.market,
            min_fit_score=payload.min_fit_score,
            max_items_per_batch=payload.max_items_per_batch,
        )
        _attach_batch_control_draft(
            result,
            payload.item_type,
            recent_items,
            str(operator.get("sub") or ""),
            age_filtered=len(raw_items) - len(recent_items),
        )
        return BatchOut(
            operator=str(operator.get("sub") or ""),
            result=result,
            age_filtered=len(raw_items) - len(recent_items),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al ejecutar evaluación por lote: {exc}",
        )


@app.post("/api/deliverables/{deliverable_id}/review", response_model=ReviewOut)
def review_deliverable(
    deliverable_id: str,
    payload: ReviewActionRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> ReviewOut:
    item = db.get_deliverable(deliverable_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entregable no encontrado.")
    operator_name = str(operator.get("sub") or "operador")

    updated = db.update_deliverable_status(
        deliverable_id=deliverable_id,
        status=payload.decision,
        reviewer_notes=payload.notes or "",
    )
    db.set_agent_state(
        "sara",
        status="working" if payload.decision == "approved" else "idle",
        task=f"Revisión humana: {payload.decision} sobre {item.get('title') or deliverable_id}",
    )

    execution_result = None
    if payload.decision == "approved":
        execution_result = sara.execute_approved_deliverable(
            item=updated or item,
            operator=operator_name,
        )
        record = db.add_outreach_record(_build_outreach_record(updated or item, operator_name))
        if record:
            execution_result["outreach_record"] = _outreach_out(record)
            spec = control_drafts.build_approval_control_spec(updated or item, record, operator_name)
            control = _store_control_draft(
                spec,
                "gmail_control_approval_prepared",
                f"deliverable={deliverable_id} | agenda={control_drafts.ACCOUNT_EMAIL} | sin envío automático",
            )
            if control:
                execution_result["control_draft"] = control

    pending = db.list_deliverables(status="pending_approval")
    db.set_agent_state(
        "sara",
        status="waiting_approval" if pending else "idle",
        task=(
            f"Hay {len(pending)} reportes listos para revisión humana"
            if pending
            else "Sin entregables pendientes; en espera de nuevas instrucciones"
        ),
    )
    return ReviewOut(
        status=payload.decision,
        operator=str(operator.get("sub") or ""),
        deliverable=updated or item,
        execution=execution_result,
        message=(
            "Aprobación registrada. El paso final quedó preparado con datos verificados; "
            "ninguna acción externa fue enviada automáticamente."
            if payload.decision == "approved"
            else "Entregable rechazado y registrado."
        ),
    )


@app.post("/api/agents/luciano/session", response_model=LucianoOut)
def run_luciano_session(
    payload: MentorSessionRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> LucianoOut:
    try:
        result = luciano.run_session(
            mode=payload.mode,
            topic=payload.topic,
            user_context=payload.user_context or "",
            num_questions=payload.num_questions,
        )
        return LucianoOut(operator=str(operator.get("sub") or ""), **result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error ejecutando sesión con Luciano: {exc}",
        )


@app.get("/api/outreach", response_model=OutreachListOut)
def list_outreach_history(
    status_filter: Optional[str] = None,
    agent_id: Optional[str] = None,
    operator: Dict[str, Any] = Depends(require_operator),
) -> OutreachListOut:
    operator_name = str(operator.get("sub") or "")
    diagnostics = db.outreach_schema_status()
    if not diagnostics["available"]:
        return OutreachListOut(
            operator=operator_name,
            count=0,
            items=[],
            reason=str(diagnostics["message"]),
        )
    try:
        records = db.list_outreach(status=status_filter, agent_id=agent_id)
    except Exception as exc:
        return OutreachListOut(
            operator=operator_name,
            count=0,
            items=[],
            reason=f"No se pudo leer public.outreach_log: {exc}",
        )
    return OutreachListOut(
        operator=operator_name,
        count=len(records),
        items=[_outreach_out(record) for record in records],
    )


@app.patch("/api/outreach/{record_id}/status", response_model=OutreachRecordOut)
def update_outreach_status_endpoint(
    record_id: str,
    payload: OutreachStatusRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> OutreachRecordOut:
    if not db.outreach_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(db.outreach_schema_status()["message"]),
        )
    record = db.get_outreach_record(record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de seguimiento no encontrado.")
    notes = payload.notes or f"Estado actualizado por {operator.get('sub') or 'operador'}"
    updated = db.update_outreach_status(record_id, status=payload.status, notes=notes)
    return _outreach_out(updated or {**record, "status": payload.status, "notes": notes})


@app.get("/api/gmail/status", response_model=GmailStatusOut)
def get_gmail_status(operator: Dict[str, Any] = Depends(require_operator)) -> GmailStatusOut:
    return GmailStatusOut(**gmail_bridge.status())


@app.post("/api/gmail/sync", response_model=GmailSyncOut)
def sync_gmail_responses(operator: Dict[str, Any] = Depends(require_operator)) -> GmailSyncOut:
    return GmailSyncOut(**gmail_bridge.sync_responses())


@app.post("/api/gmail/register-sent", response_model=GmailRegisterOut)
def register_gmail_sent_action(
    payload: GmailRegisterRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> GmailRegisterOut:
    if not db.outreach_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(db.outreach_schema_status()["message"]),
        )
    record = db.get_outreach_record(payload.outreach_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de seguimiento no encontrado.")
    result = gmail_bridge.register_approved_action(record, payload.label, payload.gmail_message_id)
    fresh = db.get_outreach_record(payload.outreach_id)
    if fresh:
        result["outreach"] = _outreach_out(fresh)
    return GmailRegisterOut(**result)


@app.post("/api/gmail/create-control-draft", response_model=GmailDraftOut)
def create_gmail_control_draft(
    payload: GmailDraftRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> GmailDraftOut:
    if not payload.operator_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmá explícitamente la creación del borrador de control.",
        )
    if not gmail_bridge.status().get("enabled"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(gmail_bridge.status().get("reason") or "Gmail no disponible"),
        )
    if not db.outreach_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(db.outreach_schema_status()["message"]),
        )
    record = db.get_outreach_record(payload.outreach_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Borrador de control no encontrado.")
    try:
        result = gmail_bridge.create_control_draft(record)
        return GmailDraftOut(**result)
    except Exception as exc:
        db.log_execution(
            agent_id="sara",
            action="gmail_control_draft_created",
            status="error",
            details=str(exc)[:1000],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo crear el borrador: {exc}",
        )


@app.post("/api/sources/collect", response_model=SourceCollectOut)
def collect_sources(
    payload: SourceCollectRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> SourceCollectOut:
    notes: List[str] = []
    items: List[Dict[str, Any]] = []
    if payload.platform == "upwork":
        if not os.getenv("UPWORK_RSS_URL", ""):
            notes.append(UPWORK_RSS_DEPRECATED)
        else:
            try:
                items = fetch_upwork_rss(limit=payload.upwork_limit, item_type=payload.item_type)
            except Exception as exc:
                notes.append(f"Upwork RSS no disponible: {exc}")
    elif payload.platform == "freelancer":
        try:
            items = fetch_freelancer_rss(limit=payload.freelancer_limit, item_type=payload.item_type)
        except Exception as exc:
            notes.append(f"Freelancer RSS no disponible: {exc}")
    elif payload.platform == "remoteok":
        if payload.item_type != "job":
            notes.append("RemoteOK solo published job posts; se usa para empleos.")
        else:
            try:
                items = fetch_remoteok_jobs(limit=payload.upwork_limit)
            except Exception as exc:
                notes.append(f"RemoteOK no disponible: {exc}")
    elif payload.platform == "wwr":
        if payload.item_type != "job":
            notes.append("We Work Remotely solo publica empleos; se usa para empleos.")
        else:
            try:
                items = fetch_wwr_jobs(limit_per_feed=max(1, payload.freelancer_limit // 2))
            except Exception as exc:
                notes.append(f"We Work Remotely no disponible: {exc}")
    else:
        if not os.getenv("UPWORK_RSS_URL", ""):
            notes.append(UPWORK_RSS_DEPRECATED)
        try:
            items = collect_freelance_platforms(
                upwork_limit=payload.upwork_limit,
                freelancer_limit=payload.freelancer_limit,
                item_type=payload.item_type,
            )
            if payload.item_type == "job":
                items.extend(fetch_remoteok_jobs(limit=payload.upwork_limit))
                items.extend(fetch_wwr_jobs(limit_per_feed=max(1, payload.freelancer_limit // 2)))
                items = deduplicate(items)
        except Exception as exc:
            notes.append(f"Fuentes RSS no disponibles: {exc}")
    filtered = [item for item in items if not item.get("prefiltered_out")]
    batch = None
    if payload.evaluate and filtered:
        batch = sara.run_batch_evaluation(
            item_type=payload.item_type,
            items=[{key: value for key, value in item.items() if key not in ("prefiltered_out", "prefilter_reason")} for item in filtered],
            market=payload.market,
            min_fit_score=payload.min_fit_score,
            max_items_per_batch=payload.max_items_per_batch,
        )
    return SourceCollectOut(
        platform=payload.platform,
        fetched=len(items),
        prefiltered_out=len(items) - len(filtered),
        items=filtered,
        evaluate=payload.evaluate,
        notes=notes,
        batch=batch,
    )


@app.post("/api/sources/structured-batch", response_model=SourceCollectOut)
def load_structured_source_batch(
    payload: StructuredBatchRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> SourceCollectOut:
    candidate = Path(payload.path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    resolved = candidate.resolve()
    root = ROOT_DIR.resolve()
    if not str(resolved).startswith(str(root)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La ruta debe estar dentro del proyecto.")
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo de lote no encontrado.")
    items = load_structured_batch(str(resolved), payload.platform_name, payload.item_type)
    filtered = [item for item in items if not item.get("prefiltered_out")]
    batch = None
    if payload.evaluate and filtered:
        batch = sara.run_batch_evaluation(
            item_type=payload.item_type,
            items=[{key: value for key, value in item.items() if key not in ("prefiltered_out", "prefilter_reason")} for item in filtered],
            market=payload.market,
            min_fit_score=payload.min_fit_score,
            max_items_per_batch=payload.max_items_per_batch,
        )
    return SourceCollectOut(
        platform=payload.platform_name,
        fetched=len(items),
        prefiltered_out=len(items) - len(filtered),
        items=filtered,
        evaluate=payload.evaluate,
        notes=[UPWORK_RSS_DEPRECATED] if not os.getenv("UPWORK_RSS_URL", "") else [],
        batch=batch,
    )


@app.get("/api/automation/status", response_model=AutomationActionOut)
def get_automation_status(operator: Dict[str, Any] = Depends(require_operator)) -> AutomationActionOut:
    return AutomationActionOut(status=automation.status())


@app.post("/api/automation/start", response_model=AutomationActionOut)
def start_automation(operator: Dict[str, Any] = Depends(require_operator)) -> AutomationActionOut:
    return AutomationActionOut(status=automation.start(trigger="operator"))


@app.post("/api/automation/pause", response_model=AutomationActionOut)
def pause_automation(
    payload: AutomationPauseRequest,
    operator: Dict[str, Any] = Depends(require_operator),
) -> AutomationActionOut:
    return AutomationActionOut(status=automation.pause(payload.reason))


@app.post("/api/automation/resume", response_model=AutomationActionOut)
def resume_automation(operator: Dict[str, Any] = Depends(require_operator)) -> AutomationActionOut:
    return AutomationActionOut(status=automation.resume())


@app.post("/api/automation/stop", response_model=AutomationActionOut)
def stop_automation(operator: Dict[str, Any] = Depends(require_operator)) -> AutomationActionOut:
    return AutomationActionOut(status=automation.stop())
