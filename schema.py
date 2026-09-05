"""Term schema: DB-таблицы (TERM_SCHEMA) и auth-права (TERM_AUTH_SCHEMA)."""
from __future__ import annotations

from typing import Any

__all__ = ["TERM_SCHEMA", "TERM_AUTH_SCHEMA"]

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

# Регистрация через AuthSchemaRegistry.register_sync("term", TERM_AUTH_SCHEMA) —
# паттерн llm/schema.py. Роль term_user сидится группе Everyone (см. __init__.py),
# чтобы существующие пользователи не потеряли доступ к терминалу.
TERM_AUTH_SCHEMA: dict[str, list[dict[str, Any]]] = {
    "permissions": [
        {"name": "term:access", "description": "PTY-сессии терминала (list/create/delete/attach)"},
    ],
    "roles": [
        {
            "name": "term_user",
            "description": "Свои PTY-сессии терминала",
            "permissions": ["term:access"],
        },
    ],
}
