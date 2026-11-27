import os
from email.utils import parsedate_to_datetime
from typing import Any

import control_drafts
from database import DatabaseManager
from integrations.gmail_organizer import (
    ACCOUNT_EMAIL,
    ALLOWED_LABELS,
    GmailAccessError,
    GmailOrganizer,
)


def _normalize_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed.isoformat()
    except (TypeError, ValueError):
        return ""


class GmailBridge:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.enabled = os.getenv("GMAIL_ENABLED", "true").lower() not in ("false", "0", "no")
        self.organizer = GmailOrganizer(
            allow_interactive_auth=os.getenv("GMAIL_ALLOW_INTERACTIVE_AUTH", "false").lower()
            in ("true", "1", "yes")
        )

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "reason": "GMAIL_ENABLED=false"}
        if not self.organizer.enabled:
            return {"enabled": False, "reason": "Credenciales Gmail no configuradas en el entorno local"}
        try:
            account = self.organizer.verify_account()
            self.organizer.ensure_labels()
            return {"enabled": True, "account": account, "labels": list(ALLOWED_LABELS)}
        except Exception as exc:
            return {"enabled": False, "reason": str(exc)}

    def register_approved_action(
        self,
        record: dict[str, Any],
        label_name: str,
        message_id: str = "",
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"external_action": "none"}
        if not self.enabled or not self.organizer.enabled or not message_id:
            return result
        record_id = record.get("id")
        if not record_id:
            return result
        try:
            self.organizer.verify_account()
            info = self.organizer.register_sent_action(message_id, label_name)
            self.db.link_outreach_gmail(
                record_id=str(record_id),
                message_id=info["gmail_message_id"],
                thread_id=info["gmail_thread_id"],
                label=label_name,
                status="espera_respuesta",
                notes=f"Registro Gmail verificado: {info.get('subject') or 'sin asunto'}",
            )
            self.db.log_execution(
                agent_id="sara",
                action="gmail_action_labeled",
                status="success",
                details=f"Etiqueta={label_name} | Mensaje={message_id} | Hilo={info.get('gmail_thread_id')}",
            )
            return {"external_action": "labeled", "gmail": info}
        except Exception as exc:
            self.db.log_execution(
                agent_id="sara",
                action="gmail_action_labeled",
                status="error",
                details=str(exc),
            )
            result["error"] = str(exc)
            return result

    def sync_responses(self) -> dict[str, Any]:
        if not self.enabled or not self.organizer.enabled:
            return {"checked": False, "updates": [], "reason": "Gmail no configurado"}
        try:
            self.organizer.verify_account()
            self.organizer.ensure_labels()
            records = self.db.list_outreach()
            known_messages = {str(r.get("gmail_message_id")) for r in records if r.get("gmail_message_id")}
            known_threads = {str(r.get("gmail_thread_id")) for r in records if r.get("gmail_thread_id")}
            updates = self.organizer.detect_new_responses(known_messages, known_threads)
            enriched: list[dict[str, Any]] = []
            for update in updates:
                thread_id = str(update.get("gmail_thread_id") or "")
                matched = self.db.find_outreach_by_thread(thread_id) if thread_id else None
                response_at = _normalize_date(str(update.get("date") or ""))
                if matched and matched.get("id"):
                    self.db.update_outreach_status(
                        record_id=str(matched["id"]),
                        status="respondido",
                        notes=(
                            f"Respuesta detectada por Sara: {update.get('from')} | "
                            f"{str(update.get('subject') or '')[:200]}"
                        ),
                        response_at=response_at or None,
                    )
                spec = control_drafts.build_response_alert_spec(update, matched)
                alert = control_drafts.store_control_draft(self.db, spec)
                enriched.append({
                    **update,
                    "outreach_id": str(matched.get("id")) if matched else str(alert.get("id")) if alert else "",
                    "response_status": "respondido" if matched else "novedad_detectada",
                    "alert_draft_id": str(alert.get("id")) if alert else "",
                    "suggested_action": (
                        "Revisar el hilo en Gmail y responder manualmente desde la cuenta autorizada."
                    ),
                })
                self.db.log_execution(
                    agent_id="sara",
                    action="gmail_response_detected",
                    status="success",
                    details=(
                        f"{update.get('gmail_label')} | {update.get('from')} | "
                        f"{str(update.get('subject') or '')[:120]} | hilo_conocido={update.get('known_thread')} | "
                        f"estado={enriched[-1]['response_status']}"
                    ),
                )
            return {"checked": True, "updates": enriched}
        except GmailAccessError as exc:
            return {"checked": False, "updates": [], "reason": str(exc)}
        except Exception as exc:
            self.db.log_execution(
                agent_id="sara",
                action="gmail_response_detected",
                status="error",
                details=str(exc),
            )
            return {"checked": False, "updates": [], "reason": str(exc)}

    def create_control_draft(self, record: dict[str, Any]) -> dict[str, Any]:
        if str(record.get("recipient") or "").lower() != ACCOUNT_EMAIL:
            raise GmailAccessError("El correo de control solo puede dirigirse a la cuenta autorizada.")
        notes = str(record.get("notes") or "")
        if control_drafts.CONTROL_MARKER not in notes and control_drafts.ALERT_MARKER not in notes:
            raise GmailAccessError("El registro no es un borrador de control preparado por Sara.")
        label = str(record.get("gmail_label") or "")
        if label not in ALLOWED_LABELS:
            raise GmailAccessError("El borrador de control no tiene una etiqueta permitida.")
        subject = str(record.get("summary") or record.get("title") or "Correo de control")
        body = str(record.get("full_text") or "")
        attachments = control_drafts.attachments_from_record(record)
        result = self.organizer.create_control_draft(ACCOUNT_EMAIL, subject, body, attachments)
        self.db.update_outreach_status(
            record_id=str(record.get("id")),
            status=str(record.get("status") or "pending_approval"),
            notes=f"{notes[:900]} | gmail_draft_id={result.get('draft_id')}",
        )
        self.db.log_execution(
            agent_id="sara",
            action="gmail_control_draft_created",
            status="success",
            details=(
                f"Etiqueta={label} | Draft={result.get('draft_id')} | "
                f"Adjuntos={len(result.get('attachments') or [])} | Sin envío automático"
            ),
        )
        return result
