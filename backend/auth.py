import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import Header, HTTPException, status


def hash_password_pbkdf2(password: str, iterations: int = 260_000) -> str:
    """Genera un hash seguro con salt aleatorio para guardar en variables de entorno."""
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Compara una contraseña en texto plano contra un hash pbkdf2_sha256 en tiempo constante."""
    if not plain_password or not stored_hash:
        return False
    try:
        scheme, iter_str, salt, expected_hex = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        return hmac.compare_digest(derived.hex(), expected_hex)
    except Exception:
        return False


def _get_signing_secret() -> str:
    secret = os.getenv("OFFICE_AUTH_SECRET", "").strip()
    if not secret:
        # Fallback local de emergencia; en Render configurá OFFICE_AUTH_SECRET obligatorio
        secret = "dev-only-change-office-auth-secret"
    return secret


def create_session_token(username: str, expires_in_seconds: int = 86_400) -> str:
    payload = {
        "sub": username,
        "role": "admin",
        "exp": int(time.time()) + expires_in_seconds,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(
        _get_signing_secret().encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def decode_and_verify_token(token: str) -> dict:
    try:
        payload_b64, sig = token.split(".", 1)
        expected_sig = hmac.new(
            _get_signing_secret().encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Firma inválida")

        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Token expirado")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Sesión no válida o expirada: {exc}",
        )


def require_authenticated_operator(authorization: Optional[str] = Header(default=None)) -> dict:
    """Dependencia para proteger rutas que ejecutan aprobaciones, rechazos, lotes o envíos."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere iniciar sesión como operador para ejecutar acciones en la oficina.",
        )
    token = authorization.split(" ", 1)[1].strip()
    return decode_and_verify_token(token)