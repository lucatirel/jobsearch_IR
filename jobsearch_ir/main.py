from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .config import load_config
from .fetchers import fetch_html_public_pages, fetch_reliefweb, fetch_rss
from .report import notify, write_outputs
from .storage import already_seen, db_connect, persist_job


def gather_jobs(cfg: dict[str, Any], since_days: int) -> list[Any]:
    fetched: list[Any] = []
    for fetcher in [fetch_reliefweb, fetch_rss, fetch_html_public_pages]:
        try:
            if fetcher is fetch_reliefweb:
                fetched.extend(fetcher(cfg, since_days))
            else:
                fetched.extend(fetcher(cfg))
        except Exception as exc:
            print(f"[WARN] {fetcher.__name__} failed: {exc}", file=sys.stderr)
    return fetched


def filter_and_persist(conn: Any, jobs: list[Any], cfg: dict[str, Any], include_seen: bool) -> list[Any]:
    min_score = int(cfg["scoring"].get("min_report_score", 4))
    selected: list[Any] = []
    for job in jobs:
        if not job.title:
            continue
        from .scoring import score_job

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
