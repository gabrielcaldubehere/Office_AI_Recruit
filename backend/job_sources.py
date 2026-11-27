import html
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
from urllib.request import Request, urlopen

UPWORK_RSS_URL = os.getenv("UPWORK_RSS_URL", "")
FREELANCER_RSS_URL = "https://www.freelancer.com/rss.xml"

NOT_STATED = "No figura en la fuente"
UPWORK_RSS_DEPRECATED = "Upwork discontinuó RSS el 20/08/2024: usá lote estructurado o UPWORK_RSS_URL propio."
MAX_SOURCE_AGE_DAYS = int(os.getenv("SOURCE_MAX_AGE_DAYS", "15"))

BLOCKED_SENIORITY = re.compile(
    r"\b(senior|sr\.?|lead|staff|principal|architect|expert|director|head of)\b",
    re.IGNORECASE,
)
REQUIRED_SIGNAL = re.compile(
    r"\b(react|typescript|javascript|node|full[\s-]?stack|frontend|front[\s-]?end|"
    r"python|fastapi|sql|supabase|web app|website|dashboard|booking|turnos)\b",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", text).strip()


def parsed_published_at(value: Any) -> datetime | None:
    if value in (None, "", NOT_STATED):
        return None
    if isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 1_000_000_000_000:
            stamp /= 1000
        return datetime.fromtimestamp(stamp, tz=timezone.utc)
    text = str(value).strip()
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def age_check(item: dict[str, Any], max_days: int | None = None) -> tuple[bool, str]:
    limit = int(max_days or MAX_SOURCE_AGE_DAYS)
    published = parsed_published_at(
        item.get("published_at") or item.get("pubDate") or item.get("date")
        or item.get("created_at") or item.get("timestamp")
    )
    if not published:
        return False, "Sin fecha verificable; descartado sin inventar antigüedad"
    age = max(0, (datetime.now(timezone.utc) - published).days)
    if age > limit:
        return False, f"Publicación con {age} días de antigüedad; límite {limit}"
    return True, f"Antigüedad {age} días (límite {limit})"


def prefilter(item: dict[str, Any]) -> tuple[bool, str]:
    within_age, age_reason = age_check(item)
    if not within_age:
        return False, age_reason
    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "raw_client_text", "raw_job_text", "description", "text")
    )
    if BLOCKED_SENIORITY.search(text):
        return False, "Senioridad por encima del perfil junior"
    if not REQUIRED_SIGNAL.search(text):
        return False, "Sin señal de stack/alcance alineado al perfil"
    return True, "Pasa pre-filtro sin tokens"


def normalize_item(
    item: dict[str, Any],
    platform: str,
    item_type: str = "client",
) -> dict[str, Any]:
    source_url = str(
        item.get("source_url") or item.get("url") or item.get("job_url") or item.get("link") or NOT_STATED
    )
    reference = str(item.get("client_ref") or item.get("id") or source_url)
    text = _clean(
        str(item.get("raw_client_text") or item.get("raw_job_text") or item.get("description") or item.get("text") or "")
    )
    company = str(item.get("company_or_client_name") or item.get("company") or NOT_STATED)
    payload: dict[str, Any] = {
        "title": str(item.get("title") or ""),
        "published_at": item.get("published_at") or item.get("pubDate") or item.get("date") or item.get("created_at") or None,
        "source_platform": platform,
        "source": platform,
        "source_url": source_url,
        "company_or_client_name": company,
        "contact_channel": str(item.get("contact_channel") or NOT_STATED),
        "contact_ref": str(item.get("contact_ref") or NOT_STATED),
    }
    if item_type == "job":
        payload.update({
            "job_url": source_url if source_url != NOT_STATED else f"batch-job-{reference}",
            "raw_job_text": text,
            "market": item.get("market") or "GLOBAL_EN",
        })
    else:
        payload.update({
            "client_ref": reference,
            "raw_client_text": text,
            "channel": item.get("channel") or "web",
            "market": item.get("market") or "LATAM_ES",
        })
    return payload


def load_structured_batch(path: str, platform: str, item_type: str = "client") -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    if isinstance(raw, dict):
        raw = raw.get("items", [])
    result: list[dict[str, Any]] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        normalized = normalize_item(entry, platform, item_type)
        passed, reason = prefilter(normalized)
        if passed:
            result.append(normalized)
        else:
            result.append({**normalized, "prefiltered_out": True, "prefilter_reason": reason})
    return result


def _fetch_rss(url: str, platform: str, item_type: str, limit: int) -> list[dict[str, Any]]:
    request = Request(url, headers={"User-Agent": "AIOffice/1.0 (+local)"})
    with urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    items: list[dict[str, Any]] = []
    for entry in root.iter("item"):
        title = _clean(entry.findtext("title", default=""))
        description = _clean(entry.findtext("description", default=""))
        normalized = normalize_item(
            {
                "title": title,
                "source_url": entry.findtext("link", default=""),
                "description": f"{title} {description}",
                "company_or_client_name": entry.findtext("author", default="") or NOT_STATED,
                "published_at": entry.findtext("pubDate", default=""),
            },
            platform,
            item_type,
        )
        passed, reason = prefilter(normalized)
        if passed:
            items.append(normalized)
        if len(items) >= limit:
            break
    return items


def fetch_upwork_rss(limit: int = 10, item_type: str = "client") -> list[dict[str, Any]]:
    url = os.getenv("UPWORK_RSS_URL", UPWORK_RSS_URL)
    if not url:
        return []
    return _fetch_rss(url, "Upwork", item_type, limit)


def fetch_freelancer_rss(limit: int = 10, item_type: str = "client") -> list[dict[str, Any]]:
    return _fetch_rss(os.getenv("FREELANCER_RSS_URL", FREELANCER_RSS_URL), "Freelancer", item_type, limit)


def collect_freelance_platforms(
    upwork_limit: int = 10,
    freelancer_limit: int = 10,
    item_type: str = "client",
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for fetch in (fetch_upwork_rss, fetch_freelancer_rss):
        limit = upwork_limit if fetch is fetch_upwork_rss else freelancer_limit
        try:
            collected.extend(fetch(limit=limit, item_type=item_type))
        except Exception:
            continue
    return deduplicate(collected)


def deduplicate(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("source_url") or item.get("client_ref") or "").strip()
        if not key or key == NOT_STATED or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
