import base64
import os
from email.message import EmailMessage
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
    "https://www.googleapis.com/auth/gmail.send",
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
        thread_id = message.get("threadId")
        return {
            "gmail_message_id": message_id,
            "gmail_thread_id": thread_id or "",
            "gmail_label": label_name,
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
        }

    def send_approved_email(self, to: str, subject: str, body: str, label_name: str) -> dict[str, str]:
        if label_name not in ALLOWED_LABELS:
            raise GmailAccessError(f"Etiqueta no permitida: {label_name}")
        if not to or "@" not in to:
            raise GmailAccessError("No hay correo de contacto verificado en la fuente; no se envía nada.")
        self.verify_account()
        message = EmailMessage()
        message["To"] = to
        message["From"] = ACCOUNT_EMAIL
        message["Subject"] = subject
        message.set_content(body)
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = self.service().users().messages().send(userId="me", body={"raw": encoded}).execute()
        return self.register_sent_action(sent.get("id", ""), label_name)

    def detect_new_responses(
        self,
        known_message_ids: set[str],
        known_thread_ids: set[str],
    ) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        for label_name in ALLOWED_LABELS:
            for item in self.list_label_messages(label_name):
                message_id = item.get("id")
                thread_id = item.get("threadId")
                if not message_id or message_id in known_message_ids:
                    continue
                message = self.get_message(message_id)
                headers = {
                    h["Name"].lower(): h["Value"]
                    for h in message.get("payload", {}).get("headers", [])
                }
                updates.append({
                    "gmail_message_id": message_id,
                    "gmail_thread_id": thread_id or "",
                    "gmail_label": label_name,
                    "subject": headers.get("subject", ""),
                    "from": headers.get("from", ""),
                    "date": headers.get("date", ""),
                    "snippet": message.get("snippet", "")[:300],
                    "known_thread": bool(thread_id and thread_id in known_thread_ids),
                })
        return updates
