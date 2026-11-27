import base64
import os
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
]
ALLOWED_LABELS = ("Clientes", "Postulaciones")
ACCOUNT_EMAIL = "caldubeheregabriel@gmail.com"

BACKEND_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = Path(os.getenv("GMAIL_CREDENTIALS_PATH", str(BACKEND_DIR / "credentials.json")))
TOKEN_PATH = Path(os.getenv("GMAIL_TOKEN_PATH", str(BACKEND_DIR / "gmail_token.json")))


class GmailAccessError(RuntimeError):
    pass


class GmailOrganizer:
    def __init__(self, allow_interactive_auth: bool = False) -> None:
        self._service: Any = None
        self._labels: dict[str, str] = {}
        self._allow_interactive_auth = allow_interactive_auth

    @property
    def enabled(self) -> bool:
        return CREDENTIALS_PATH.exists() or TOKEN_PATH.exists()

    def service(self) -> Any:
        if self._service is not None:
            return self._service
        if not CREDENTIALS_PATH.exists() and not TOKEN_PATH.exists():
            raise GmailAccessError(
                "Gmail no configurado: definí GMAIL_CREDENTIALS_PATH y GMAIL_TOKEN_PATH con archivos locales."
            )
        creds: Optional[Credentials] = None
        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            if not CREDENTIALS_PATH.exists() or not self._allow_interactive_auth:
                raise GmailAccessError(
                    "Token Gmail ausente o vencido. Autorizá una vez de forma local con "
                    "GMAIL_ALLOW_INTERACTIVE_AUTH=true y luego reiniciá el backend."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            os.chmod(TOKEN_PATH, 0o600)
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    def verify_account(self) -> str:
        profile = self.service().users().getProfile(userId="me").execute()
        email = str(profile.get("emailAddress") or "").lower()
        if email != ACCOUNT_EMAIL:
            raise GmailAccessError(
                f"La cuenta autorizada ({email or 'desconocida'}) no es la permitida ({ACCOUNT_EMAIL})."
            )
        return email

    def ensure_labels(self) -> dict[str, str]:
        service = self.service()
        if self._labels:
            return dict(self._labels)
        existing = service.users().labels().list(userId="me").execute().get("labels", [])
        for label in existing:
            if label.get("name") in ALLOWED_LABELS:
                self._labels[label["name"]] = label["id"]
        for name in ALLOWED_LABELS:
            if name not in self._labels:
                created = service.users().labels().create(
                    userId="me",
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                ).execute()
                self._labels[name] = created["id"]
        return dict(self._labels)

    def apply_label(self, message_id: str, label_name: str) -> None:
        if label_name not in ALLOWED_LABELS:
            raise GmailAccessError(f"Etiqueta no permitida: {label_name}")
        labels = self.ensure_labels()
        self.service().users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [labels[label_name]]},
        ).execute()

    def apply_label_to_thread(self, thread_id: str, label_name: str) -> None:
        if not thread_id:
            return
        if label_name not in ALLOWED_LABELS:
            raise GmailAccessError(f"Etiqueta no permitida: {label_name}")
        labels = self.ensure_labels()
        self.service().users().threads().modify(
            userId="me",
            id=thread_id,
            body={"addLabelIds": [labels[label_name]]},
        ).execute()

    def list_label_messages(self, label_name: str, query: str = "") -> list[dict[str, Any]]:
        if label_name not in ALLOWED_LABELS:
            raise GmailAccessError(f"Etiqueta no permitida: {label_name}")
        labels = self.ensure_labels()
        result = self.service().users().messages().list(
            userId="me",
            labelIds=[labels[label_name]],
            q=query,
            maxResults=50,
        ).execute()
        return result.get("messages", [])

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self.service().users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "To", "Date", "Message-ID"],
        ).execute()

    def register_sent_action(self, message_id: str, label_name: str) -> dict[str, str]:
        if label_name not in ALLOWED_LABELS:
            raise GmailAccessError(f"Etiqueta no permitida: {label_name}")
        self.apply_label(message_id, label_name)
        message = self.get_message(message_id)
        headers = {
            h["Name"].lower(): h["Value"]
            for h in message.get("payload", {}).get("headers", [])
        }
        thread_id = message.get("threadId") or ""
        self.apply_label_to_thread(thread_id, label_name)
        return {
            "gmail_message_id": message_id,
            "gmail_thread_id": thread_id or "",
            "gmail_label": label_name,
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
        }

    def create_control_draft(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        if str(to).lower() != ACCOUNT_EMAIL:
            raise GmailAccessError("Los borradores de control solo pueden dirigirse a la cuenta autorizada.")
        self.verify_account()
        message = EmailMessage()
        message["To"] = to
        message["From"] = ACCOUNT_EMAIL
        message["Subject"] = subject[:250]
        message.set_content(body[:30000])
        attached: list[dict[str, Any]] = []
        for item in attachments or []:
            path = Path(str(item.get("path") or "")).expanduser()
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            payload = path.read_bytes()
            if not payload:
                continue
            message.add_attachment(
                payload,
                maintype="application",
                subtype="pdf",
                filename=path.name,
            )
            attached.append({"name": path.name, "mime_type": "application/pdf", "size_bytes": len(payload)})
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft = self.service().users().drafts().create(
            userId="me",
            body={"message": {"raw": encoded}},
        ).execute()
        return {
            "draft_id": str(draft.get("id") or ""),
            "to": to,
            "subject": subject[:250],
            "attachments": attached,
            "external_action": "draft_created",
        }

    def detect_new_responses(
        self,
        known_message_ids: set[str],
        known_thread_ids: set[str],
    ) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for label_name in ALLOWED_LABELS:
            for item in self.list_label_messages(label_name):
                message_id = item.get("id")
                thread_id = item.get("threadId") or ""
                if not message_id or message_id in known_message_ids or message_id in seen:
                    continue
                seen.add(message_id)
                message = self.get_message(message_id)
                headers = {
                    h["Name"].lower(): h["Value"]
                    for h in message.get("payload", {}).get("headers", [])
                }
                sender = headers.get("from", "")
                sender_address = parseaddr(sender)[1].strip().lower()
                if not sender_address or sender_address == ACCOUNT_EMAIL:
                    continue
                updates.append({
                    "gmail_message_id": message_id,
                    "gmail_thread_id": thread_id,
                    "gmail_label": label_name,
                    "subject": headers.get("subject", ""),
                    "from": sender,
                    "from_address": sender_address,
                    "date": headers.get("date", ""),
                    "snippet": message.get("snippet", "")[:500],
                    "known_thread": bool(thread_id and thread_id in known_thread_ids),
                })
        return updates
