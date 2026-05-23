from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Job


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
        f.write("# Aurora Job Monitor — nuove offerte\n\n")
        f.write(f"Generato: {datetime.now().isoformat(timespec='seconds')}\n\n")
        if not jobs_sorted:
            f.write("Nessuna nuova offerta sopra soglia in questo run.\n")
            return

        f.write("| Priorità | Organizzazione | Ruolo | Sede | Scadenza | Score | Motivo | Azione | Link |\n")
        f.write("|---|---|---|---:|---:|---:|---|---|---|\n")
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
