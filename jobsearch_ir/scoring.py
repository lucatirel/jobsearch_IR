from __future__ import annotations

import html
import re
from typing import Any, Iterable

from dateutil import parser as dateparser

from .models import Job


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
    hits: list[str] = []
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
