import os
from typing import Any

from database import DatabaseManager
from integrations.gmail_organizer import ALLOWED_LABELS, GmailAccessError, GmailOrganizer


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
            records = self.db.list_outreach()
            known_messages = {str(r.get("gmail_message_id")) for r in records if r.get("gmail_message_id")}
            known_threads = {str(r.get("gmail_thread_id")) for r in records if r.get("gmail_thread_id")}
            updates = self.organizer.detect_new_responses(known_messages, known_threads)
            for update in updates:
                match = next(
                    (r for r in records if r.get("gmail_thread_id") == update["gmail_thread_id"]),
                    None,
                )
                if match and match.get("id"):
                    self.db.link_outreach_gmail(
                        record_id=str(match["id"]),
                        message_id=update["gmail_message_id"],
                        thread_id=update["gmail_thread_id"],
                        label=update["gmail_label"],
                        status="respondido",
                        notes=f"Nueva respuesta: {update['from']} — {update['subject']}",
                        response_at=update["date"] or None,
                    )
                self.db.log_execution(
                    agent_id="sara",
                    action="gmail_response_detected",
                    status="success",
                    details=(
                        f"{update['gmail_label']} | {update['from']} | {update['subject'][:120]} | "
                        f"hilo_conocido={update['known_thread']}"
                    ),
                )
            return {"checked": True, "updates": updates}
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
