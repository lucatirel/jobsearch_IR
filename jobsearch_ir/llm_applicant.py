from __future__ import annotations

import os
from typing import Any

from .models import Job


class LLMClient:
    def __init__(self, provider: str = "openai", api_key: str | None = None) -> None:
        self.provider = provider
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")

    def generate(self, prompt: str) -> str:
        if self.provider == "openai":
            raise RuntimeError(
                "OpenAI provider is not configured. Install the OpenAI client and set OPENAI_API_KEY, or implement another provider."
            )
        raise NotImplementedError(f"LLM provider {self.provider} is not implemented.")


def build_job_prompt(job: Job, profile: dict[str, Any], employer_name: str | None = None, role_name: str | None = None) -> str:
    employer = employer_name or job.organisation or "l'organizzazione"
    role = role_name or job.title or "la posizione"
    return (
        f"Scrivi una lettera di motivazione in italiano per una candidatura a {employer}. "
        f"Il ruolo è {role}.\n\n"
        f"Profilo candidato:\n"
        f"- Nome: {profile.get('candidate_name', 'Aurora Olivola')}\n"
        f"- Esperienza: circa 1 anno in Save the Children tra stage e contratto\n"
        f"- Interessi: policy internazionale, advocacy, programme support, child protection, migration, refugee support\n"
        f"- Lingue: italiano, inglese, francese come plus\n\n"
        f"Dettagli annuncio:\n"
        f"- Titolo: {job.title}\n"
        f"- Organizzazione: {job.organisation}\n"
        f"- Sede: {job.location}\n"
        f"- Descrizione: {job.summary[:1200]}\n\n"
        "Genera una lettera concisa, mirata e professionale, con motivazioni allineate al ruolo e al profilo."
    )


def generate_cover_letter(job: Job, profile: dict[str, Any], employer_name: str | None = None, role_name: str | None = None) -> str:
    client = LLMClient()
    prompt = build_job_prompt(job, profile, employer_name, role_name)
    return client.generate(prompt)
