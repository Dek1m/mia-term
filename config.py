"""TermConfig — PTY-сессии в контейнере belle, home = {home_root}/{username}."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TermConfig:
    home_root: str = "/home"

    @classmethod
    def from_env(cls) -> TermConfig:
        return cls(
            home_root=os.environ.get("TERM_HOME_ROOT", os.environ.get("WORKSPACE_HOME_ROOT", "/home")),
        )
