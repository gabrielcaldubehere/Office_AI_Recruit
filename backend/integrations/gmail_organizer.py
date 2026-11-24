import base64
import os
import re
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BACKEND_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = Path(os.getenv("GMAIL_CREDENTIALS_PATH", BACKEND_DIR / "credentials.json"))
TOKEN_PATH = Path(os.getenv("GMAIL_TOKEN_PATH", BACKEND_DIR / "gmail_token.json"))

# Permisos acotados: gestionar etiquetas, leer alertas y enviar solo borradores aprobados
SCOPES = [
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

# Jerarquía de carpetas (etiquetas anidadas en Gmail)
DEFAULT_LABEL_TREE = [
    "AI-Office",
    "AI-Office/Empleos",
    "AI-Office/Empleos/RemoteOK",
    "AI-Office/Empleos/WeWorkRemotely",
    "AI-Office/Empleos/GetOnBoard",
    "AI-Office/Empleos/Himalayas",
    "AI-Office/Clientes",
    "AI-Office/Clientes/Workana",
    "AI-Office/Clientes/Directos-PyMEs",
]


class GmailOrganizer:
    """Gestiona etiquetas por portal/cliente, lectura de alertas y envíos aprobados vía OAuth2."""

    def __init__(self) -> None:
        self.service = self._authenticate()
        self._label_cache: dict[str, str] = {}

    def _authenticate(self):
        creds: Optional[Credentials] = None
        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDENTIALS_PATH.exists():
                    raise FileNotFoundError(
                        f"Falta {CREDENTIALS_PATH}. Descargá el JSON OAuth2 Desktop desde Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
                creds = flow.run_local_server(port=0)

            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def _refresh_label_cache(self) -> dict[str, str]:
        resp = self.service.users().labels().list(userId="me").execute()
        labels = resp.get("labels", [])
        self._label_cache = {lbl["name"]: lbl["id"] for lbl in labels}
        return self._label_cache

    def ensure_label_hierarchy(self, labels: list[str] = DEFAULT_LABEL_TREE) -> dict[str, str]:
        """Crea la carpeta madre y todas las subcarpetas de Empleos y Clientes si no existen."""
        existing = self._refresh_label_cache()
        for label_name in labels:
            if label_name in existing:
                continue
            body = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
            created = self.service.users().labels().create(userId="me", body=body).execute()
            existing[label_name] = created["id"]
        self._label_cache = existing
        return existing

    def resolve_label_name(self, category: str, source: str) -> str:
        """Devuelve la ruta exacta, ej: 'AI-Office/Empleos/GetOnBoard' o 'AI-Office/Clientes/Workana'."""
        clean_source = re.sub(r"[^a-zA-Z0-9_-]", "", source or "General") or "General"
        root_branch = "Empleos" if category == "job_application" else "Clientes"
        full_name = f"AI-Office/{root_branch}/{clean_source}"
        if full_name not in self._label_cache:
            self.ensure_label_hierarchy(["AI-Office", f"AI-Office/{root_branch}", full_name])
        return full_name

    def apply_label_to_message(self, message_id: str, label_name: str) -> None:
        if label_name not in self._label_cache:
            self.ensure_label_hierarchy([label_name])
        label_id = self._label_cache[label_name]
        self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()

    def fetch_alerts_from_label(self, label_name: str, max_results: int = 15) -> list[dict]:
        """Lee mensajes no leídos dentro de una subcarpeta (ej: GetOnBoard o Workana) para pasarlos a Sara."""
        if label_name not in self._label_cache:
            self._refresh_label_cache()
        label_id = self._label_cache.get(label_name)
        if not label_id:
            return []

        res = (
            self.service.users()
            .messages()
            .list(userId="me", labelIds=[label_id, "UNREAD"], maxResults=max_results)
            .execute()
        )
        messages = res.get("messages", [])
        extracted: list[dict] = []

        for msg_meta in messages:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_meta["id"], format="full")
                .execute()
            )
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("subject", "(Sin asunto)")
            snippet = msg.get("snippet", "")
            urls = re.findall(r"https?://[^\s<>\"']+", snippet)

            extracted.append({
                "message_id": msg_meta["id"],
                "subject": subject,
                "snippet": snippet,
                "detected_url": urls[0] if urls else f"gmail://{msg_meta['id']}",
            })
        return extracted

    def send_approved_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        category: str,
        source: str,
    ) -> dict:
        """Envía un correo solo tras aprobación humana y lo archiva bajo su etiqueta correspondiente."""
        label_name = self.resolve_label_name(category=category, source=source)

        message = EmailMessage()
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body_text)

        raw_encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = (
            self.service.users()
            .messages()
            .send(userId="me", body={"raw": raw_encoded})
            .execute()
        )
        self.apply_label_to_message(sent["id"], label_name)
        return {"message_id": sent["id"], "label": label_name}
    