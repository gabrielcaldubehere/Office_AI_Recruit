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


DEFAULT_JSON_MAX_TOKENS = 2200
MIN_JSON_MAX_TOKENS = 1800
JSON_OUTPUT_RULE = (
    "\n\nJSON OUTPUT RULES: reply with exactly one valid JSON object and no markdown fences. "
    "Keep every string field concise (<= 400 characters or <= 80 words unless the schema asks for detail); "
    "avoid long verbatim quotes. Close all strings and braces; never truncate the object."
)
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"
GROQ_FALLBACK_MODELS = ("openai/gpt-oss-120b", "qwen/qwen3.8-27b")
OPENROUTER_DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
OPENROUTER_FALLBACK_MODELS = (
    "baidu/ernie-5.5-flash-preview:free",
    "particle-ai/particle-1:free",
    "nvidia/nemotron-3.5-lightning:free",
)


def _clean_env(name: str, default: str = "") -> str:
    value = (os.getenv(name) or default).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


def _model_list(raw: str, defaults: tuple[str, ...]) -> list[str]:
    models: list[str] = []
    for item in raw.split(","):
        model = item.strip().strip('"').strip("'").strip()
        if model and model not in models:
            models.append(model)
    return models or list(defaults)


def _status_code(exc: Exception) -> Optional[int]:
    for source in (exc, getattr(exc, "response", None)):
        if source is None:
            continue
        for attr in ("status_code", "http_status"):
            value = getattr(source, attr, None)
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and 100 <= value <= 599:
                return value
            if isinstance(value, str) and value.isdigit() and 100 <= int(value) <= 599:
                return int(value)
    match = re.search(r"\b([1-5]\d{2})\b", str(exc))
    if match:
        status = int(match.group(1))
        if 100 <= status <= 599:
            return status
    return None


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, LLMResponseError):
        return True
    status = _status_code(exc)
    if status == 404 or status == 429 or (status is not None and status >= 500):
        return True
    lowered = str(exc).lower()
    return any(token in lowered for token in (
        "model_not_found",
        "does not exist",
        "rate limit",
        "rate_limit",
        "too many requests",
        "overloaded",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "internal server",
        "timed out",
        "timeout",
        "unterminated",
        "unexpected end of json",
        "invalid json",
        "json decode",
        "expecting value",
        "empty response",
        "no content",
    ))


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
        self.providers: list[dict[str, Any]] = []
        self.token_guard = token_guard
        self.event_logger = event_logger
        self._configure_providers()

    def _configure_providers(self) -> None:
        self.provider_warnings: list[str] = []
        groq_primary = _model_list(
            _clean_env("GROQ_MODEL", GROQ_DEFAULT_MODEL), (GROQ_DEFAULT_MODEL,)
        )[0]
        openrouter_primary = _model_list(
            _clean_env("OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL), (OPENROUTER_DEFAULT_MODEL,)
        )[0]
        openrouter_fallbacks = _model_list(
            _clean_env("OPENROUTER_FALLBACK_MODELS"), OPENROUTER_FALLBACK_MODELS
        )
        configs: list[dict[str, Any]] = [
            {
                "name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": _clean_env("GROQ_API_KEY"),
                "models": [groq_primary] + [
                    model for model in GROQ_FALLBACK_MODELS if model != groq_primary
                ],
            },
            {
                "name": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                "api_key": _clean_env("GEMINI_API_KEY"),
                "models": [_clean_env("GEMINI_MODEL", "gemini-2.5-flash")],
            },
            {
                "name": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": _clean_env("OPENROUTER_API_KEY"),
                "models": [openrouter_primary] + [
                    model for model in openrouter_fallbacks if model != openrouter_primary
                ],
            },
        ]
        self.providers = []
        for config in configs:
            if config["name"] == "gemini":
                if not config["api_key"]:
                    self.provider_warnings.append("gemini: falta GEMINI_API_KEY en .env")
                elif not config["api_key"].startswith(("AIza", "AQ")):
                    self.provider_warnings.append(
                        "gemini: GEMINI_API_KEY no empieza con 'AIza' ni 'AQ'; revisá la clave"
                    )
                    continue
            if config["api_key"]:
                self.providers.append(config)
        for warning in self.provider_warnings:
            self._log_event({"provider": "config", "status": "warning", "details": warning})

    def _log_event(self, event: dict[str, Any]) -> None:
        if not self.event_logger:
            return
        try:
            self.event_logger(event)
        except Exception:
            pass

    def _log_attempt(
        self,
        provider: str,
        model: str,
        status: str,
        details: str,
        attempt: int,
        total: int,
        tokens: int = 0,
        will_retry: bool = False,
    ) -> None:
        self._log_event({
            "provider": provider,
            "model": model,
            "status": status,
            "details": details,
            "attempt": attempt,
            "models": total,
            "tokens": tokens,
            "will_retry": will_retry,
        })

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
            detail = " | ".join(self.provider_warnings)
            message = "No hay API keys configuradas en .env (GROQ, GEMINI u OPENROUTER)."
            raise RuntimeError(f"{message} Detalles: {detail}" if detail else message)
        system_instruction = self.load_skill(skill_file) if skill_file else ""
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({
            "role": "user",
            "content": prompt + JSON_OUTPUT_RULE if json_mode else prompt,
        })
        errors: list[str] = []
        token_limit = DEFAULT_JSON_MAX_TOKENS if max_tokens is None else max_tokens

        for provider in self.providers:
            client = OpenAI(
                api_key=provider["api_key"],
                base_url=provider["base_url"],
                timeout=60.0,
            )
            models: list[str] = provider["models"]
            for index, model in enumerate(models, start=1):
                self._check_budget()
                request: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if json_mode:
                    request["max_tokens"] = max(token_limit, MIN_JSON_MAX_TOKENS)
                elif max_tokens:
                    request["max_tokens"] = token_limit
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
                    if not content.strip():
                        raise LLMResponseError("Respuesta vacía del proveedor")
                    tokens_used = int(
                        getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
                    )
                    parsed = _extract_json(content) if json_mode else None
                    self._log_attempt(
                        provider["name"],
                        model,
                        "success",
                        f"model={model}",
                        index,
                        len(models),
                        tokens=tokens_used,
                    )
                    return {
                        "provider": provider["name"],
                        "model": model,
                        "raw_text": content,
                        "json_data": parsed,
                        "tokens_used": tokens_used,
                    }
                except LLMBudgetExceeded:
                    raise
                except Exception as exc:
                    retryable = _is_retryable(exc)
                    will_retry = retryable and index < len(models)
                    detail = f"{provider['name']}/{model}: {type(exc).__name__}: {exc}"
                    errors.append(detail)
                    self._log_attempt(
                        provider["name"],
                        model,
                        "error",
                        detail,
                        index,
                        len(models),
                        will_retry=will_retry,
                    )
                    if not retryable:
                        break
        details = errors + self.provider_warnings
        raise LLMResponseError("Todos los proveedores fallaron. " + " | ".join(details))
