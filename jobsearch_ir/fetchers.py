from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import Job
from .scoring import clean_text, contains_any, norm, parse_date

USER_AGENT = "AuroraJobMonitor/0.1 (+personal job search; polite; no-login)"


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
