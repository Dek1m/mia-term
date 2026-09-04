"""TermConfig — сессии терминала в контейнере belle."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TermConfig:
    root: str = "/tmp/albedo-term"
    timeout_sec: float = 15.0
    output_limit: int = 262144

    @classmethod
    def from_env(cls) -> TermConfig:
        return cls(
            root=os.environ.get("TERM_ROOT", "/tmp/albedo-term"),
            timeout_sec=float(os.environ.get("TERM_TIMEOUT_SEC", "15")),
            output_limit=int(os.environ.get("TERM_OUTPUT_LIMIT", "262144")),
        )
