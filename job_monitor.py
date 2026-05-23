#!/usr/bin/env python3
"""
Aurora Job Monitor
==================

Monitora fonti lavoro pubbliche/API/RSS, deduplica offerte già viste,
calcola uno score coerente con il profilo di Aurora Olivola e produce
un report CSV + Markdown con le nuove opportunità.

Nota legale/pratica:
- preferisce API ufficiali e RSS;
- evita login automation e scraping aggressivo;
- LinkedIn va gestito con alert ufficiali/export manuali, non con crawler.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

USER_AGENT = "AuroraJobMonitor/0.1 (+personal job search; polite; no-login)"


@dataclass
class Job:
    source: str
    title: str
    organisation: str = ""
    location: str = ""
    deadline: str = ""
    published: str = ""
    url: str = ""
    summary: str = ""
    raw_id: str = ""
    score: int = 0
    priority: str = ""
    reason: str = ""
    action: str = ""

    @property
    def fingerprint(self) -> str:
        base = self.url or f"{self.source}|{self.title}|{self.organisation}|{self.location}"
        return hashlib.sha256(base.strip().lower().encode("utf-8")).hexdigest()


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def db_connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_jobs (
            fingerprint TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            title TEXT,
            organisation TEXT,
            location TEXT,
            url TEXT,
            source TEXT,
            score INTEGER,
            payload_json TEXT
        )
        """
    )
    return conn


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def norm(value: str) -> str:
    return clean_text(value).casefold()


def contains_any(text: str, terms: Iterable[str]) -> list[str]:
    hay = norm(text)
    hits = []
    for term in terms:
        t = term.casefold()
        if t in hay:
            hits.append(term)
    return hits


def parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        return dateparser.parse(value).date().isoformat()
    except Exception:
        return clean_text(value)


def score_job(job: Job, cfg: dict[str, Any]) -> Job:
    profile = cfg["profile"]
    weights = cfg["scoring"]
    blob = " ".join([job.title, job.organisation, job.location, job.summary])

    score = 0
    reasons: list[str] = []

    high_locs = contains_any(job.location + " " + job.summary, profile["preferred_locations"]["high"])
    med_locs = contains_any(job.location + " " + job.summary, profile["preferred_locations"]["medium"])
    if high_locs:
        score += int(weights["location_high"])
        reasons.append(f"sede forte: {', '.join(high_locs[:3])}")
    elif med_locs:
        score += int(weights["location_medium"])
        reasons.append(f"sede accettabile: {', '.join(med_locs[:3])}")

    org_hits = contains_any(job.organisation, profile["strong_organisations"])
    if org_hits:
        score += int(weights["strong_org"])
        reasons.append(f"organizzazione target: {org_hits[0]}")

    role_hits = contains_any(job.title + " " + job.summary, profile["target_roles"])
    if role_hits:
        score += int(weights["role_keyword"])
        reasons.append(f"ruolo coerente: {', '.join(role_hits[:3])}")

    language_blob = norm(blob)
    if "english" in language_blob and ("italian" in language_blob or "italiano" in language_blob):
        score += int(weights["english_italian"])
        reasons.append("inglese + italiano")
    if "french" in language_blob or "français" in language_blob or "francese" in language_blob:
        score += int(weights["french_plus"])
        reasons.append("francese valorizzabile")

    too_senior_patterns = [r"\b5\+? years\b", r"\b6\+? years\b", r"\b7\+? years\b", r"\b8\+? years\b", r"senior", r"head of", r"director"]
    if any(re.search(p, language_blob) for p in too_senior_patterns):
        score += int(weights["too_senior"])
        reasons.append("possibile seniority alta")

    if any(x in language_blob for x in ["fundraising", "donor acquisition", "major gifts"]):
        score += int(weights["generic_fundraising_or_comms"])
        reasons.append("possibile fundraising puro")

    if any(x in language_blob for x in ["unpaid internship", "unpaid intern", "stage non retribuito"]):
        score += int(weights["unpaid_internship"])
        reasons.append("stage non pagato")

    job.score = score
    job.reason = "; ".join(reasons) if reasons else "match da verificare manualmente"

    if score >= int(weights["priority_a_score"]):
        job.priority = "A — candidatura prioritaria"
        job.action = "Leggere annuncio completo e preparare CV/cover mirati"
    elif score >= int(weights["priority_b_score"]):
        job.priority = "B — interessante da verificare"
        job.action = "Aprire link, controllare seniority e requisiti obbligatori"
    elif score >= int(weights["min_report_score"]):
        job.priority = "C — backup"
        job.action = "Tenere in lista solo se non emergono candidature migliori"
    else:
        job.priority = "No / rumore"
        job.action = "Scartare salvo elementi nascosti nell’annuncio"

    return job


def fetch_reliefweb(cfg: dict[str, Any], since_days: int) -> list[Job]:
    src = cfg["sources"]["reliefweb"]
    if not src.get("enabled", False):
        return []

    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()
    payload = {
        "limit": int(src.get("limit", 100)),
        "query": {"value": src["query"]},
        "sort": ["date.created:desc"],
        "fields": {
            "include": [
                "id",
                "url",
                "title",
                "source.name",
                "country.name",
                "city.name",
                "date.created",
                "date.closing",
                "body-html",
            ]
        },
        "filter": {
            "field": "date.created",
            "value": {"from": f"{since}T00:00:00+00:00"},
        },
    }
    url = src["url"] + f"?appname={src.get('appname','aurora-job-monitor')}"
    r = requests.post(url, json=payload, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    data = r.json()
    out: list[Job] = []
    for item in data.get("data", []):
        fields = item.get("fields", {})
        country = ", ".join([c.get("name", "") for c in fields.get("country", []) if isinstance(c, dict)])
        city = ", ".join([c.get("name", "") for c in fields.get("city", []) if isinstance(c, dict)])
        source_names = ", ".join([s.get("name", "") for s in fields.get("source", []) if isinstance(s, dict)])
        loc = ", ".join([x for x in [city, country] if x])
        out.append(
            Job(
                source="ReliefWeb API",
                title=clean_text(fields.get("title", "")),
                organisation=source_names,
                location=loc,
                deadline=parse_date((fields.get("date", {}) or {}).get("closing", "")),
                published=parse_date((fields.get("date", {}) or {}).get("created", "")),
                url=fields.get("url") or item.get("href", ""),
                summary=clean_text(fields.get("body-html", ""))[:1200],
                raw_id=str(item.get("id", "")),
            )
        )
    return out


def fetch_rss(cfg: dict[str, Any]) -> list[Job]:
    rss_cfg = cfg["sources"].get("rss", {})
    if not rss_cfg.get("enabled", False):
        return []
    out: list[Job] = []
    for feed in rss_cfg.get("feeds", []):
        try:
            parsed = feedparser.parse(feed["url"], request_headers={"User-Agent": USER_AGENT})
            for e in parsed.entries[:100]:
                out.append(
                    Job(
                        source=f"RSS: {feed['name']}",
                        title=clean_text(getattr(e, "title", "")),
                        organisation=clean_text(getattr(e, "author", "")),
                        location="",
                        deadline="",
                        published=parse_date(getattr(e, "published", "") or getattr(e, "updated", "")),
                        url=clean_text(getattr(e, "link", "")),
                        summary=clean_text(getattr(e, "summary", ""))[:1200],
                        raw_id=clean_text(getattr(e, "id", "")),
                    )
                )
        except Exception as exc:
            print(f"[WARN] RSS failed for {feed.get('name')}: {exc}", file=sys.stderr)
    return out


def fetch_html_public_pages(cfg: dict[str, Any]) -> list[Job]:
    html_cfg = cfg["sources"].get("html_public_pages", {})
    if not html_cfg.get("enabled", False):
        return []
    delay = float(html_cfg.get("polite_delay_seconds", 2))
    out: list[Job] = []
    for page in html_cfg.get("pages", []):
        try:
            r = requests.get(page["url"], headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select(page.get("link_selector", "a")):
                title = clean_text(a.get_text(" "))
                href = a.get("href")
                if not title or not href:
                    continue
                url = urljoin(page["url"], href)
                text_blob = title + " " + url
                # Heuristic: keep plausible job links only. Final filtering is by score.
                if not contains_any(text_blob, cfg["profile"]["target_roles"]) and not any(
                    x in norm(text_blob) for x in ["job", "vacanc", "career", "position", "officer", "assistant", "policy", "programme"]
                ):
                    continue
                out.append(
                    Job(
                        source=f"Public page: {page['name']}",
                        title=title,
                        organisation=page["name"],
                        location="",
                        url=url,
                        summary="",
                    )
                )
            time.sleep(delay)
        except Exception as exc:
            print(f"[WARN] HTML page failed for {page.get('name')}: {exc}", file=sys.stderr)
    return out


def write_outputs(jobs: list[Job], cfg: dict[str, Any], base_dir: Path) -> None:
    out_cfg = cfg["output"]
    csv_path = base_dir / out_cfg["csv_path"]
    md_path = base_dir / out_cfg["markdown_path"]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    jobs_sorted = sorted(jobs, key=lambda j: j.score, reverse=True)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["priority", "organisation", "title", "location", "deadline", "score", "reason", "action", "url", "source", "published"],
        )
        writer.writeheader()
        for j in jobs_sorted:
            writer.writerow(
                {
                    "priority": j.priority,
                    "organisation": j.organisation,
                    "title": j.title,
                    "location": j.location,
                    "deadline": j.deadline,
                    "score": j.score,
                    "reason": j.reason,
                    "action": j.action,
                    "url": j.url,
                    "source": j.source,
                    "published": j.published,
                }
            )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Aurora Job Monitor — nuove offerte\n\n")
        f.write(f"Generato: {datetime.now().isoformat(timespec='seconds')}\n\n")
        if not jobs_sorted:
            f.write("Nessuna nuova offerta sopra soglia in questo run.\n")
            return
        f.write("| Priorità | Organizzazione | Ruolo | Sede | Scadenza | Score | Motivo | Azione | Link |\n")
        f.write("|---|---|---|---|---:|---:|---|---|---|\n")
        for j in jobs_sorted:
            link = f"[link]({j.url})" if j.url else ""
            f.write(
                f"| {j.priority} | {j.organisation} | {j.title} | {j.location} | {j.deadline} | {j.score} | {j.reason} | {j.action} | {link} |\n"
            )


def notify(jobs: list[Job], cfg: dict[str, Any], base_dir: Path) -> None:
    notif = cfg.get("notifications", {})
    md_path = base_dir / cfg["output"]["markdown_path"]
    if notif.get("email", {}).get("enabled"):
        print("[INFO] Email notifications are configured in config.yaml but not implemented in this starter. Use reports/latest_report.md.")
    if notif.get("telegram", {}).get("enabled"):
        print("[INFO] Telegram notifications are configured in config.yaml but not implemented in this starter. Use reports/latest_report.md.")
    print(f"[OK] Report written: {md_path}")


def already_seen(conn: sqlite3.Connection, fingerprint: str) -> bool:
    row = conn.execute("SELECT 1 FROM seen_jobs WHERE fingerprint=?", (fingerprint,)).fetchone()
    return row is not None


def persist_job(conn: sqlite3.Connection, job: Job) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(asdict(job), ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO seen_jobs
        (fingerprint, first_seen, last_seen, title, organisation, location, url, source, score, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fingerprint) DO UPDATE SET
            last_seen=excluded.last_seen,
            score=excluded.score,
            payload_json=excluded.payload_json
        """,
        (
            job.fingerprint,
            now,
            now,
            job.title,
            job.organisation,
            job.location,
            job.url,
            job.source,
            job.score,
            payload,
        ),
    )


def gather_jobs(cfg: dict[str, Any], since_days: int) -> list[Job]:
    fetched: list[Job] = []
    for fetcher in [fetch_reliefweb, fetch_rss, fetch_html_public_pages]:
        try:
            if fetcher is fetch_reliefweb:
                fetched.extend(fetcher(cfg, since_days))
            else:
                fetched.extend(fetcher(cfg))
        except Exception as exc:
            print(f"[WARN] {fetcher.__name__} failed: {exc}", file=sys.stderr)
    return fetched


def filter_and_persist(conn: sqlite3.Connection, jobs: list[Job], cfg: dict[str, Any], include_seen: bool) -> list[Job]:
    min_score = int(cfg["scoring"].get("min_report_score", 4))
    selected: list[Job] = []
    for job in jobs:
        if not job.title:
            continue
        scored = score_job(job, cfg)
        seen_before = already_seen(conn, scored.fingerprint)
        persist_job(conn, scored)

        if scored.score < min_score:
            continue
        if not include_seen and seen_before:
            continue
        selected.append(scored)
    return selected


def run(config_path: str | Path, since_days: int, include_seen: bool) -> int:
    config_path = Path(config_path)
    base_dir = config_path.parent
    cfg = load_config(config_path)
    conn = db_connect(base_dir / cfg["output"]["sqlite_path"])

    fetched = gather_jobs(cfg, since_days)
    selected = filter_and_persist(conn, fetched, cfg, include_seen)

    conn.commit()
    write_outputs(selected, cfg, base_dir)
    notify(selected, cfg, base_dir)
    print(f"[OK] Fetched={len(fetched)} Selected={len(selected)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Monitor job postings for Aurora Olivola")
    ap.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    ap.add_argument("--since-days", type=int, default=7, help="Fetch jobs published in the last N days where supported")
    ap.add_argument("--include-seen", action="store_true", help="Include previously seen matching jobs in the report")
    args = ap.parse_args()
    return run(args.config, args.since_days, args.include_seen)


if __name__ == "__main__":
    raise SystemExit(main())
