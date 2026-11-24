import os  # Como `process` en Node.js: permite leer variables de entorno del sistema
import json  # Como `JSON` en JS: convierte strings JSON a diccionarios de Python y viceversa
from typing import Optional  # Como `string | null` en TypeScript: indica que un parámetro es opcional
from dotenv import load_dotenv  # Carga el archivo .env en memoria (similar a `dotenv/config`)
from openai import OpenAI  # Cliente oficial compatible con endpoints OpenAI-compatible

# Cargamos las variables definidas en el archivo .env
load_dotenv()


class LLMRouter:
    """
    Enrutador multi-proveedor gratuito con fallback automático.
    En TypeScript sería algo similar a una `class LLMRouter` con métodos `async ask(...)`.
    """

    def __init__(self) -> None:
        # En Python, `__init__` es el equivalente al `constructor()` de una clase en TypeScript.
        # `self` equivale a `this` en JavaScript/TypeScript.
        self.providers: list[dict[str, str]] = []

        # 1. Proveedor principal rápido (Groq): ideal para lotes de Mateo/Valeria/Elena
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            self.providers.append({
                "name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": groq_key,
                "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            })

        # 2. Proveedor de razonamiento / contexto amplio (Google Gemini via endpoint OpenAI)
        gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if gemini_key:
            self.providers.append({
                "name": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                "api_key": gemini_key,
                "model": (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip(),
            })

        # 3. Respaldo gratuito (OpenRouter): entra si fallan los anteriores o hay límite
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            self.providers.append({
                "name": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": openrouter_key,
                "model": os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            })

    def load_skill(self, skill_filename: str) -> str:
        """
        Lee un archivo .md desde /skills/ solo cuando se necesita (Lazy Loading de Skill).
        Ahorra tokens al no meter todas las reglas de todos los agentes en cada llamada.
        """
        # Construimos la ruta relativa desde backend/ hacia ../skills/<archivo>
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        skill_path = os.path.join(base_dir, "skills", skill_filename)

        # `with open(...) as f:` abre y cierra el archivo de forma segura (evita fugas de memoria)
        with open(skill_path, "r", encoding="utf-8") as file:
            return file.read()

    def ask(
        self,
        prompt: str,
        skill_file: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> dict:
        """
        Envía el prompt al primer proveedor disponible.
        Si ocurre un error (por ejemplo rate limit 429), prueba el siguiente proveedor.
        """
        if not self.providers:
            raise RuntimeError("No hay API keys configuradas en .env (GROQ, GEMINI u OPENROUTER).")

        # Combinamos las reglas de la Skill (si se pidió una) con el prompt de la tarea
        system_instruction = ""
        if skill_file:
            system_instruction = self.load_skill(skill_file)

        last_error: Optional[Exception] = None

        # `for item in lista:` equivale a `for (const item of lista)` en TypeScript
        for provider in self.providers:
            try:
                client = OpenAI(
                    api_key=provider["api_key"],
                    base_url=provider["base_url"],
                )

                # Armamos los mensajes igual que en el chat completions de OpenAI/TS
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                # Parámetros extra si pedimos respuesta estricta en JSON
                extra_params = {"response_format": {"type": "json_object"}} if json_mode else {}

                response = client.chat.completions.create(
                    model=provider["model"],
                    messages=messages,
                    temperature=temperature,
                    **extra_params,  # `**` desempaqueta un diccionario como argumentos nombrados (como `...opts` en JS)
                )

                content = response.choices[0].message.content or ""

                # Estimación simple de tokens si el proveedor devuelve `usage`
                tokens_used = 0
                if response.usage and response.usage.total_tokens:
                    tokens_used = response.usage.total_tokens

                parsed_json = None
                if json_mode:
                    parsed_json = json.loads(content)

                return {
                    "provider": provider["name"],
                    "model": provider["model"],
                    "raw_text": content,
                    "json_data": parsed_json,
                    "tokens_used": tokens_used,
                }

            except Exception as exc:
                # Guardamos el error y continuamos con el siguiente proveedor de la lista
                last_error = exc
                continue

        # Si ningún proveedor respondió bien, lanzamos el último error ocurrido
        raise RuntimeError(f"Todos los proveedores fallaron. Último error: {last_error}")