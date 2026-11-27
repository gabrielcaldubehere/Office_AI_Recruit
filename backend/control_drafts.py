import json
import os
from pathlib import Path
from typing import Any

from integrations.gmail_organizer import ACCOUNT_EMAIL

BASE_DIR = Path(__file__).resolve().parent.parent
CONTROL_MARKER = "CORREO_CONTROL_OFICINA1"
ALERT_MARKER = "ALERTA_RESPUESTA_GMAIL"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
NOT_STATED = "No figura en la fuente"


def label_for_category(category: str) -> str:
    return "Postulaciones" if category == "job_application" else "Clientes"


def agent_for_category(category: str) -> str:
    return "mateo" if category == "job_application" else "valeria"


def category_for_label(label: str) -> str:
    return "job_application" if label == "Postulaciones" else "client_lead"


def _allowed_roots() -> list[Path]:
    roots = [BASE_DIR]
    configured = os.getenv("GMAIL_PDF_DIR", "").strip().strip("\"'")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = BASE_DIR / path
        resolved = path.resolve()
        if resolved.is_dir():
            roots.append(resolved)
    return roots


def _iter_references(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        candidates = value
    elif isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = json.loads(value)
            candidates = parsed if isinstance(parsed, list) else [value]
        except (TypeError, ValueError):
            candidates = [value]
    else:
        candidates = [value]
    references: list[str] = []
    for item in candidates:
        text = str(item).strip()
        if text and text not in references:
            references.append(text)
    return references


def find_existing_pdfs(*references: Any) -> list[dict[str, Any]]:
    roots = _allowed_roots()
    found: dict[str, dict[str, Any]] = {}
    for reference in references:
        for raw in _iter_references(reference):
            candidate = Path(raw).expanduser()
            paths = [candidate.resolve()] if candidate.is_absolute() else [root / candidate for root in roots]
            for path in paths:
                resolved = path.resolve()
                if not any(root == resolved or root in resolved.parents for root in roots):
                    continue
                if resolved.suffix.lower() != ".pdf" or not resolved.is_file():
                    continue
                size = resolved.stat().st_size
                if size == 0 or size > MAX_ATTACHMENT_BYTES:
                    continue
                found[str(resolved)] = {
                    "path": str(resolved),
                    "name": resolved.name,
                    "mime_type": "application/pdf",
                    "size_bytes": size,
                }
                break
    return list(found.values())


def attachments_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    return find_existing_pdfs(record.get("attachment_reference"))


def _string_list(value: Any, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    return [str(item).strip()[:400] for item in items if str(item).strip()][:limit]


def _section(title: str, lines: list[str]) -> str:
    return f"{title}\n" + "\n".join(f"- {line}" for line in lines if line)


def _source_section(item: dict[str, Any]) -> str:
    platform = str(item.get("source_platform") or NOT_STATED)
    url = str(item.get("source_url") or item.get("source_url_of_application") or NOT_STATED)
    posted = item.get("published_at") or item.get("posted_at") or item.get("created_at") or NOT_STATED
    fit = item.get("fit_score")
    fit_text = f"{fit}%" if fit is not None else NOT_STATED
    return _section("Qué se buscó y cómo se filtró", [
        f"Plataforma verificada: {platform}",
        f"Fuente: {url}",
        f"Publicación informada por la fuente: {posted}",
        "Filtro estricto de 15 días: aplicado antes del análisis; no se inventa antigüedad cuando la fuente no la informa.",
        f"Puntaje de coincidencia registrado: {fit_text}",
        "Datos trazables: solo campos presentes en la fuente o en el entregable aprobado por el operador.",
    ])


def _batch_source_section(item_type: str, result: dict[str, Any], age_filtered: int, platforms: list[str]) -> str:
    summary = result.get("reason") or "Tanda ejecutada con filtros de antigüedad y duplicados."
    counts = [
        f"Tipo de búsqueda: {'vacantes' if item_type == 'job' else 'clientes/prospectos'}",
        f"Plataformas informadas: {', '.join(platforms) if platforms else NOT_STATED}",
        f"Ítems recibidos: {int(result.get('processed') or 0) + int(age_filtered or 0)}",
        f"Fuera del filtro de 15 días: {int(age_filtered or 0)}",
        f"Procesados: {int(result.get('processed') or 0)}",
        f"Guardados para aprobación: {int(result.get('saved_for_approval') or 0)}",
        f"Duplicados: {int(result.get('duplicates') or 0)}",
        f"Descartados por filtro de perfil: {int(result.get('filtered_out') or 0)}",
        f"Tokens consumidos: {int(result.get('total_tokens') or 0)}",
        f"Resultado: {summary}",
    ]
    urls = []
    for entry in (result.get("results") or [])[:10]:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or NOT_STATED)
        flags = []
        if entry.get("saved_for_approval"):
            flags.append("guardado para aprobación")
        if entry.get("duplicate"):
            flags.append("duplicado")
        if entry.get("filtered_out"):
            flags.append("filtrado")
        urls.append(f"{url} ({', '.join(flags) if flags else 'sin cambio'}); índice={entry.get('index')}")
    section = _section("Qué se buscó y cómo se filtró", counts)
    if urls:
        section += "\n" + _section("Fuentes procesadas (trazabilidad real)", urls)
    return section


def _client_copy_section(item: dict[str, Any]) -> str:
    variants = item.get("outreach_variants") or []
    lines = []
    for variant in variants[:3]:
        if not isinstance(variant, dict):
            continue
        lines.append(
            f"[{variant.get('approach', 'variante')}] {variant.get('subject', '')} :: "
            f"{str(variant.get('body', ''))[:1600]}"
        )
    if not lines:
        lines.append(str(item.get("outreach_draft") or item.get("summary") or NOT_STATED)[:2500])
    rate = item.get("hourly_rate_usd")
    rate_lines = [
        f"Tarifa única propuesta: {rate} USD/hora" if rate is not None else "Tarifa: no solicitada o no informada en la fuente",
        f"Justificación: {item.get('rate_justification') or NOT_STATED}",
        f"Horas diarias estimadas: {item.get('estimated_hours_per_day') or NOT_STATED}",
        f"Plazo estimado: {item.get('estimated_timeline') or NOT_STATED}",
    ]
    modalities = item.get("delivery_modalities") or []
    for modality in modalities[:2]:
        if isinstance(modality, dict):
            rate_lines.append(f"{modality.get('model', 'Modelo')}: {modality.get('description', '')}")
    rate_lines.append(f"Previsualizaciones: {item.get('preview_policy') or NOT_STATED}")
    rate_lines.append(f"Presupuesto detallado posterior: {item.get('detailed_budget_note') or NOT_STATED}")
    rate_lines.append("Plazos y tarifa quedan sujetos a revisión humana; no se commitió ningún deadline automáticamente.")
    return (
        _section("Copia de la propuesta preparada", lines)
        + "\n"
        + _section("Presupuesto, plazos y modelo de entrega", rate_lines)
    )


def _job_copy_section(item: dict[str, Any]) -> str:
    lines = [
        f"Enlace de postulación: {item.get('source_url_of_application') or item.get('source_url') or NOT_STATED}",
        f"Empresa: {item.get('company_or_client_name') or NOT_STATED}",
        f"Contacto o canal: {item.get('contact_ref') or item.get('contact_channel') or NOT_STATED}",
        f"Puesto: {item.get('role_title') or item.get('title') or NOT_STATED}",
        f"CV/PDF referenciado: {item.get('cv_reference') or NOT_STATED}",
        f"Pitch corto: {str(item.get('tailored_summary') or item.get('summary') or '')[:1200] or NOT_STATED}",
        f"Instrucciones literales del aviso: {str(item.get('application_instructions') or '')[:1200] or NOT_STATED}",
    ]
    arguments = _string_list(item.get("match_arguments"), limit=5)
    if arguments:
        lines.append("Argumentos de coincidencia: " + " | ".join(arguments))
    return _section("Copia de la postulación preparada y datos verificados", lines)


def _attachment_section(item: dict[str, Any], attachments: list[dict[str, Any]]) -> str:
    if attachments:
        lines = [
            f"{entry['name']} — {entry['mime_type']} — {entry['size_bytes']} bytes — {entry['path']}"
            for entry in attachments
        ]
        return _section("Adjuntos PDF verificados en disco", lines)
    references = _iter_references(item.get("attachment_reference") or item.get("cv_reference"))
    if references:
        return _section("Adjuntos PDF verificados en disco", [
            f"No se adjunta nada: la referencia {reference} no corresponde a un PDF existente dentro de las rutas permitidas."
            for reference in references[:5]
        ])
    return _section("Adjuntos PDF verificados en disco", [
        "No hay ningún PDF generado en disco para este registro; no se inventa ni se adjunta archivo alguno."
    ])


def _base_spec(
    *,
    marker: str,
    key: str,
    title: str,
    category: str,
    label: str,
    subject: str,
    body: str,
    item: dict[str, Any],
    operator: str,
    attachments: list[dict[str, Any]],
    status: str = "pending_approval",
) -> dict[str, Any]:
    notes = (
        f"{marker} | key={key[:500]} | Destinatario={ACCOUNT_EMAIL} | "
        "Borrador pendiente de aprobación; sin envío automático."
    )
    return {
        "agent_id": agent_for_category(category),
        "category": category,
        "title": title[:500],
        "recipient": ACCOUNT_EMAIL,
        "source_platform": str(item.get("source_platform") or NOT_STATED),
        "source_url": item.get("source_url") or None,
        "source_url_of_application": item.get("source_url_of_application") or item.get("source_url") or None,
        "company_or_client_name": str(item.get("company_or_client_name") or NOT_STATED),
        "contact_channel": "Correo de control interno",
        "contact_ref": ACCOUNT_EMAIL,
        "contact_ref_pending": False,
        "full_text": f"Asunto: {subject}\n\n{body}"[:8000],
        "summary": f"[{label}] {subject}"[:1200],
        "cv_reference": item.get("cv_reference"),
        "attachment_reference": json.dumps(attachments, ensure_ascii=False) if attachments else "",
        "hourly_rate_usd": item.get("hourly_rate_usd"),
        "rate_model": item.get("rate_model"),
        "status": status,
        "gmail_label": label,
        "gmail_thread_id": item.get("gmail_thread_id") or None,
        "last_response_at": item.get("last_response_at") or None,
        "operator": operator,
        "notes": notes[:1000],
        "_marker": marker,
        "_key": key,
    }


def build_batch_control_spec(
    *,
    item_type: str,
    result: dict[str, Any],
    age_filtered: int,
    platforms: list[str],
    operator: str,
) -> dict[str, Any]:
    label = label_for_category("job_application" if item_type == "job" else "client_lead")
    key = f"lote|{item_type}|{int(result.get('processed') or 0)}|{int(age_filtered or 0)}|{int(result.get('total_tokens') or 0)}"
    title = f"[Borrador control][{label}] Resumen de lote {'vacantes' if item_type == 'job' else 'clientes'}"
    subject = title
    body = "\n\n".join([
        f"Operador que ejecutó la tanda: {operator}",
        _batch_source_section(item_type, result, age_filtered, platforms),
        _section("Copia/estado de la tanda", [
            "No se envió nada a contactos externos; los entregables quedan en pending_approval hasta revisión humana.",
            "El guarda de tokens al 85% y el modo público de solo lectura siguen activos.",
        ]),
        _attachment_section({}, []),
    ])
    return _base_spec(
        marker=CONTROL_MARKER,
        key=key,
        title=title,
        category="job_application" if item_type == "job" else "client_lead",
        label=label,
        subject=subject,
        body=body,
        item={"source_platform": ", ".join(platforms) if platforms else NOT_STATED},
        operator=operator,
        attachments=[],
    )


def build_approval_control_spec(item: dict[str, Any], record: dict[str, Any], operator: str) -> dict[str, Any]:
    category = str(item.get("category") or record.get("category") or "client_lead")
    label = label_for_category(category)
    attachments = find_existing_pdfs(
        item.get("pdf_path"),
        item.get("proposal_pdf"),
        item.get("budget_pdf"),
        item.get("cv_reference"),
        item.get("attachment_reference"),
        record.get("attachment_reference"),
    )
    content = dict(item)
    content.update({key: value for key, value in (record or {}).items() if value})
    subject = f"[Borrador control][{label}] Copia de {item.get('title') or 'entregable aprobado'}"
    copy_section = _client_copy_section(content) if category == "client_lead" else _job_copy_section(content)
    body = "\n\n".join([
        f"Operador que aprobó: {operator}",
        _source_section(content),
        copy_section,
        _attachment_section(content, attachments),
        _section("Estado de la acción", [
            "Sin envío externo automático; el usuario debe revisar, copiar o crear el borrador y enviarlo manualmente.",
            "La aprobación humana solo preparó el contenido con datos verificados.",
        ]),
    ])
    key = f"aprobacion|{record.get('id') or item.get('id') or item.get('source_url') or item.get('title')}"
    return _base_spec(
        marker=CONTROL_MARKER,
        key=key,
        title=f"[Borrador control][{label}] {item.get('title') or 'Entregable aprobado'}",
        category=category,
        label=label,
        subject=subject,
        body=body,
        item=content,
        operator=operator,
        attachments=attachments,
    )


def build_response_alert_spec(update: dict[str, Any], matched_record: dict[str, Any] | None) -> dict[str, Any]:
    label = str(update.get("gmail_label") or "Clientes")
    category = category_for_label(label)
    message_id = str(update.get("gmail_message_id") or "")
    sender = str(update.get("from") or NOT_STATED)
    subject = str(update.get("subject") or "(sin asunto)")
    snippet = str(update.get("snippet") or "").strip()[:500]
    if category == "client_lead":
        suggestion = "Leer el hilo en Gmail, confirmar alcance y tarifa, y responder manualmente con presupuesto detallado."
    else:
        suggestion = "Leer el hilo en Gmail, verificar quién escribió y responder manualmente desde la cuenta autorizada."
    if matched_record:
        status = "respondido"
        trace = f"Registro vinculado: {matched_record.get('title') or matched_record.get('id') or NOT_STATED}"
    else:
        status = "novedad_detectada"
        trace = "No hay registro previo vinculado al hilo; revisar manualmente antes de clasificar."
    title = f"[Aviso respuesta][{label}] {subject[:120] or 'Nueva respuesta'}"
    email_subject = f"[Aviso de respuesta][{label}] {subject[:120] or 'Nueva respuesta'}"
    body = "\n\n".join([
        "Sara detectó un mensaje entrante en una etiqueta permitida.",
        _section("Datos verificados del mensaje", [
            f"Etiqueta: {label}",
            f"Remitente externo: {sender}",
            f"Asunto del hilo: {subject}",
            f"Fecha informada por Gmail: {update.get('date') or NOT_STATED}",
            f"Vista previa literal: {snippet or NOT_STATED}",
            f"ThreadId: {update.get('gmail_thread_id') or NOT_STATED}",
            f"MessageId: {message_id or NOT_STATED}",
            trace,
        ]),
        _section("Acción sugerida (manual)", [suggestion]),
        _attachment_section({}, []),
        "No se respondió ni se modificó el hilo automáticamente; este aviso queda pendiente de aprobación.",
    ])
    item = {
        "source_platform": f"Gmail/{label}",
        "source_url": None,
        "company_or_client_name": sender,
        "gmail_thread_id": update.get("gmail_thread_id"),
        "last_response_at": update.get("date") or None,
    }
    alert_status = "pending_approval" if matched_record else status
    spec = _base_spec(
        marker=ALERT_MARKER,
        key=f"respuesta|{message_id}",
        title=title,
        category=category,
        label=label,
        subject=email_subject,
        body=body,
        item=item,
        operator="sara",
        attachments=[],
        status=alert_status,
    )
    spec["_response_status"] = status
    spec["gmail_message_id"] = message_id or None
    return spec


def store_control_draft(db: Any, spec: dict[str, Any]) -> dict[str, Any] | None:
    marker = spec["_marker"]
    key = spec["_key"]
    for existing in db.list_outreach():
        notes = str(existing.get("notes") or "")
        if marker in notes and f"key={key}" in notes:
            return existing
    payload = {key: value for key, value in spec.items() if not key.startswith("_")}
    try:
        return db.add_outreach_record(payload)
    except Exception as exc:
        if payload.get("status") != "novedad_detectada":
            raise
        fallback = dict(payload)
        fallback["status"] = "pending_approval"
        fallback["notes"] = f"{fallback.get('notes', '')} | fallback=migracion_003_pendiente: {exc}"[:1000]
        return db.add_outreach_record(fallback)
