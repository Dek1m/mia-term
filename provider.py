"""Term RPC — именованные PTY-сессии как login в /home/{username}."""
from __future__ import annotations

import asyncio
from typing import Any

from core.task_decorator import task

from .config import TermConfig
from .errors import ForbiddenError, NotFoundError, TermError
from .linux import account_from_fs, linux_name
from .shell import LiveShell, bridge

__all__ = ["TermProvider", "TermError", "ForbiddenError", "NotFoundError"]


class TermProvider:
    def __init__(self, database: Any, log: Any, config: TermConfig, fs: Any | None = None) -> None:
        self._db = database
        self._log = log
        self._config = config
        self._fs = fs

    def _uid(self, session_user_id: str | None) -> str:
        if not session_user_id:
            raise ForbiddenError("Authentication required")
        return str(session_user_id)

    def _username(self, user_id: str) -> str:
        rows = self._db.fetch("SELECT username FROM auth.users WHERE id = %s", user_id)
        if not rows:
            raise ForbiddenError("Authentication required")
        return str(rows[0]["username"])

    def _row(self, session_id: str, user_id: str) -> dict[str, Any]:
        rows = self._db.fetch(
            "SELECT * FROM term.sessions WHERE id = %s AND user_id = %s",
            session_id,
            user_id,
        )
        if not rows:
            raise NotFoundError("Session")
        return rows[0]

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "title": row.get("title"),
            "cwd": row.get("cwd"),
            "status": row.get("status"),
            "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"),
            "updated_at": row.get("updated_at").isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at"),
        }

    @task(type="database", api=True, name="sessions_list", permission="term:access")
    def sessions_list(self, _session_user_id: str | None = None) -> dict[str, Any]:
        uid = self._uid(_session_user_id)
        rows = self._db.fetch(
            "SELECT * FROM term.sessions WHERE user_id = %s ORDER BY created_at DESC",
            uid,
        )
        return {"items": [self._public(row) for row in rows]}

    @task(type="database", api=True, name="session_create", permission="term:access")
    def session_create(self, title: str | None = None, _session_user_id: str | None = None) -> dict[str, Any]:
        uid = self._uid(_session_user_id)
        username = self._username(uid)
        cwd = f"{self._config.home_root.rstrip('/')}/{linux_name(username)}"
        if self._fs is not None:
            cwd = str(self._fs.home_for(uid))
        name = (title or "").strip() or "Terminal"
        rows = self._db.fetch(
            "INSERT INTO term.sessions (user_id, title, cwd, status) "
            "VALUES (%s, %s, %s, 'idle') RETURNING *",
            uid,
            name,
            cwd,
        )
        if not rows:
            raise TermError("Create failed", "DATABASE_ERROR")
        return self._public(rows[0])

    @task(type="database", api=True, name="session_delete", permission="term:access")
    def session_delete(self, session_id: str, _session_user_id: str | None = None) -> dict[str, Any]:
        uid = self._uid(_session_user_id)
        self._row(session_id, uid)
        self._db.execute("DELETE FROM term.sessions WHERE id = %s AND user_id = %s", session_id, uid)
        return {"ok": True}

    async def attach_pty(self, websocket: Any, session_id: str, user_id: str, username: str | None) -> None:
        # Sync DB/fs вызовы — в to_thread: attach живёт в event loop rest-процесса,
        # блокирующий psycopg/mkdir не должен останавливать остальные запросы.
        uid = self._uid(user_id)
        await asyncio.to_thread(self._row, session_id, uid)
        if self._fs is None:
            raise TermError("FS is required", "TERM_ERROR")
        info = await asyncio.to_thread(self._fs.ensure_home, uid)
        display = str(info.get("username") or username or await asyncio.to_thread(self._username, uid))
        account = account_from_fs(info, display)
        await asyncio.to_thread(
            self._db.execute,
            "UPDATE term.sessions SET status = 'open', cwd = %s, updated_at = NOW() WHERE id = %s",
            str(account.home),
            session_id,
        )
        shell = LiveShell(account)
        shell.start()
        if self._log is not None:
            self._log.info("term_pty_open", extra={"session_id": session_id, "user": account.name})
        try:
            await bridge(websocket, shell)
        finally:
            shell.close()
            await asyncio.to_thread(
                self._db.execute,
                "UPDATE term.sessions SET status = 'idle', updated_at = NOW() WHERE id = %s",
                session_id,
            )
            if self._log is not None:
                self._log.info("term_pty_close", extra={"session_id": session_id})
