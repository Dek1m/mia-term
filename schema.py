"""Term schema."""
from __future__ import annotations

from typing import Any

__all__ = ["TERM_SCHEMA"]

TERM_SCHEMA: dict[str, Any] = {
    "schema": "term",
    "sessions": {
        "columns": {
            "user_id": "UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE",
            "title": "TEXT NOT NULL",
            "cwd": "TEXT NOT NULL",
            "status": "TEXT NOT NULL DEFAULT 'idle'",
            "created_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        },
    },
}
