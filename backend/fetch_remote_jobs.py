import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal
from urllib.request import Request, urlopen

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

for env_path in (BACKEND_DIR / ".env", ROOT_DIR / ".env"):
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)

from agents.sara import SaraOrchestrator  # noqa: E402


REMOTEOK_API_URL = "https://remoteok.com/api"
WWR_RSS_FEEDS = [
    ("WeWorkRemotely", "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss"),
    ("WeWorkRemotely", "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss"),
    ("WeWorkRemotely", "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss"),
]

STACK_KEYWORDS = (
    "react",
    "node",
    "nodejs",
    "node.js",
    "fullstack",
    "full stack",
    "full-stack",
    "frontend",
    "front-end",
    "backend",
    "back-end",
    "typescript",
    "javascript",
    "python",
    "junior",
    "jr",
)


def _clean_html(raw_html: str) -> str:
    """Limpia etiquetas HTML básicas de descripciones RSS para ahorrar tokens."""
    unescaped = html.unescape(raw_html or "")
    no_tags = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", no_tags).strip()


def fetch_remoteok_jobs(limit: int = 15) -> list[dict]:
    """Obtiene vacantes desde el feed JSON público de RemoteOK."""
    req = Request(
        REMOTEOK_API_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (AI-Office-Sara-Batch-Collector/1.1)",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=20) as response:
        raw_payload = json.loads(response.read().decode("utf-8", errors="replace"))

    if not isinstance(raw_payload, list):
        return []

    collected: list[dict] = []
    for entry in raw_payload:
        if not isinstance(entry, dict):
            continue
        position = (entry.get("position") or "").strip()
        if not position:
            continue

        company = (entry.get("company") or "Empresa no especificada").strip()
        location = (entry.get("location") or "Remote").strip()
        tags = entry.get("tags") or []
        tags_str = ", ".join(str(t) for t in tags if t)
        description = _clean_html(entry.get("description") or "")
        url = (entry.get("url") or entry.get("apply_url") or "").strip()
        salary_min = entry.get("salary_min")
        salary_max = entry.get("salary_max")

        searchable = f"{position} {company} {location} {tags_str} {description}".lower()
        if not any(kw in searchable for kw in STACK_KEYWORDS):
            continue

        salary_info = ""
        if salary_min or salary_max:
            salary_info = f"\nSalario publicado: {salary_min or '?'} - {salary_max or '?'}"

        raw_job_text = (
            f"Fuente: RemoteOK\n"
            f"Puesto: {position}\n"
            f"Empresa: {company}\n"
            f"Ubicación / Modalidad: {location}\n"
            f"Tags: {tags_str}{salary_info}\n"
            f"Descripción:\n{description[:2200]}"
        )

        job_url = url or f"https://remoteok.com/remote-jobs/{entry.get('id', len(collected) + 1)}"
        collected.append({
            "source": "RemoteOK",
            "job_url": job_url,
            "raw_job_text": raw_job_text,
            "market": "GLOBAL_EN",
        })

        if len(collected) >= limit:
            break

    return collected


def fetch_wwr_jobs(limit_per_feed: int = 8) -> list[dict]:
    """Obtiene vacantes desde los feeds RSS públicos de We Work Remotely."""
    collected: list[dict] = []
    seen_links: set[str] = set()

    for source_name, feed_url in WWR_RSS_FEEDS:
        try:
            req = Request(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (AI-Office-Sara-Batch-Collector/1.1)"},
            )
            with urlopen(req, timeout=20) as response:
                xml_bytes = response.read()

            root = ET.fromstring(xml_bytes)
            count_in_feed = 0
            for item in root.findall("./channel/item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                region = (item.findtext("region") or "Remote").strip()
                description = _clean_html(item.findtext("description") or "")

                if not title or not link or link in seen_links:
                    continue

                searchable = f"{title} {region} {description}".lower()
                if not any(kw in searchable for kw in STACK_KEYWORDS):
                    continue

                seen_links.add(link)
                raw_job_text = (
                    f"Fuente: {source_name}\n"
                    f"Puesto / Empresa: {title}\n"
                    f"Región / Modalidad: {region}\n"
                    f"Descripción:\n{description[:2200]}"
                )
                collected.append({
                    "source": source_name,
                    "job_url": link,
                    "raw_job_text": raw_job_text,
                    "market": "GLOBAL_EN",
                })
                count_in_feed += 1
                if count_in_feed >= limit_per_feed:
                    break
        except Exception as exc:
            print(f"[WARN] No se pudo leer feed {feed_url}: {exc}", file=sys.stderr)

    return collected


def run_collector(
    remoteok_limit: int = 12,
    wwr_limit_per_feed: int = 5,
    min_fit_score: int = 60,
    max_items_per_batch: int = 25,
    market: Literal["LATAM_ES", "GLOBAL_EN"] = "GLOBAL_EN",
) -> dict:
    sara = SaraOrchestrator()
    jobs = fetch_remoteok_jobs(limit=remoteok_limit) + fetch_wwr_jobs(limit_per_feed=wwr_limit_per_feed)

    if not jobs:
        return {
            "fetched": 0,
            "processed": 0,
            "saved_for_approval": 0,
            "duplicates": 0,
            "filtered_out": 0,
            "total_tokens": 0,
            "message": "No se encontraron vacantes coincidentes en los feeds en esta corrida.",
        }

    batch_result = sara.run_batch_evaluation(
        item_type="job",
        items=jobs,
        market=market,
        min_fit_score=min_fit_score,
        max_items_per_batch=max_items_per_batch,
    )
    return {
        "fetched": len(jobs),
        **batch_result,
    }


if __name__ == "__main__":
    summary = run_collector(
        remoteok_limit=int(os.getenv("REMOTEOK_LIMIT", "12")),
        wwr_limit_per_feed=int(os.getenv("WWR_LIMIT_PER_FEED", "5")),
        min_fit_score=int(os.getenv("BATCH_MIN_FIT_SCORE", "60")),
        max_items_per_batch=int(os.getenv("BATCH_MAX_ITEMS", "25")),
        market="GLOBAL_EN",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))