import json
import os
import re
from typing import Any, Callable, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class LLMBudgetExceeded(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


def _extract_json(content: str) -> Any:
    if not content or not str(content).strip():
        raise LLMResponseError("Respuesta vacía del proveedor")
    text = str(content).strip()
    lower = text.lower()
    if lower.startswith("<!doctype") or lower.startswith("<html"):
        raise LLMResponseError("Respuesta HTML en vez de JSON")
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    decoder = json.JSONDecoder()
    errors: list[str] = []
    for match in re.finditer(r"[{[]", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
            return value
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
    raise LLMResponseError("Sin JSON válido: " + ("; ".join(errors[:2]) or "sin bloques interpretables"))


class LLMRouter:
    def __init__(
        self,
        token_guard: Optional[Callable[[], tuple[bool, str]]] = None,
        event_logger: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        self.providers: list[dict[str, str]] = []
        self.token_guard = token_guard
        self.event_logger = event_logger
        self._configure_providers()

    def _configure_providers(self) -> None:
        configs = [
            {
                "name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": os.getenv("GROQ_API_KEY", ""),
                "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            },
            {
                "name": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                "api_key": (os.getenv("GEMINI_API_KEY") or "").strip(),
                "model": (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip(),
            },
            {
                "name": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": os.getenv("OPENROUTER_API_KEY", ""),
                "model": os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            },
        ]
        self.providers = [config for config in configs if config["api_key"]]

    def _log_event(self, event: dict[str, Any]) -> None:
        if not self.event_logger:
            return
        try:
            self.event_logger(event)
        except Exception:
            pass

    def _check_budget(self) -> None:
        if not self.token_guard:
            return
        allowed, reason = self.token_guard()
        if not allowed:
            self._log_event({"provider": "budget", "status": "blocked", "details": reason})
            raise LLMBudgetExceeded(reason)

    def load_skill(self, skill_filename: str) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        skill_path = os.path.join(base_dir, "skills", skill_filename)
        with open(skill_path, "r", encoding="utf-8") as file:
            return file.read()

    def ask(
        self,
        prompt: str,
        skill_file: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        if not self.providers:
            raise RuntimeError("No hay API keys configuradas en .env (GROQ, GEMINI u OPENROUTER).")
        system_instruction = self.load_skill(skill_file) if skill_file else ""
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        errors: list[str] = []

        for provider in self.providers:
            self._check_budget()
            client = OpenAI(api_key=provider["api_key"], base_url=provider["base_url"], timeout=60.0)
            request: dict[str, Any] = {
                "model": provider["model"],
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens:
                request["max_tokens"] = max_tokens
            try:
                try:
                    response = client.chat.completions.create(
                        response_format={"type": "json_object"},
                        **request,
                    ) if json_mode else client.chat.completions.create(**request)
                except TypeError as exc:
                    if json_mode and "response_format" in str(exc).lower():
                        response = client.chat.completions.create(**request)
                    else:
                        raise
                content = response.choices[0].message.content or ""
                tokens_used = int(getattr(getattr(response, "usage", None), "total_tokens", 0) or 0)
                parsed = _extract_json(content) if json_mode else None
                self._log_event({
                    "provider": provider["name"],
                    "status": "success",
                    "tokens": tokens_used,
                    "details": f"model={provider['model']}",
                })
                return {
                    "provider": provider["name"],
                    "model": provider["model"],
                    "raw_text": content,
                    "json_data": parsed,
                    "tokens_used": tokens_used,
                }
            except LLMBudgetExceeded:
                raise
            except Exception as exc:
                detail = f"{provider['name']}: {type(exc).__name__}: {exc}"
                errors.append(detail)
                self._log_event({
                    "provider": provider["name"],
                    "status": "error",
                    "details": detail,
                })
        raise LLMResponseError("Todos los proveedores fallaron. " + " | ".join(errors))
