from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


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

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
