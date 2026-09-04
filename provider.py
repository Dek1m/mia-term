"""Term RPC — linux-сессии внутри контейнера belle, без PTY."""
from __future__ import annotations

import asyncio
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.task_decorator import task

from .config import TermConfig

__all__ = ["TermProvider", "TermError", "ForbiddenError"]

_ALLOWED = frozenset({
    "ls", "pwd", "id", "echo", "date", "whoami", "uname", "cat", "head", "tail", "wc", "env",
})


class TermError(Exception):
    def __init__(self, message: str, code: str = "TERM_ERROR", human: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.human = human or message


class ForbiddenError(TermError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, "FORBIDDEN", message)


class NotFoundError(TermError):
    def __init__(self, entity: str = "Session") -> None:
        super().__init__(f"{entity} not found", "NOT_FOUND", f"{entity} not found")


class TermProvider:
    def __init__(self, database: Any, log: Any, config: TermConfig) -> None:
        self._db = database
        self._log = log
        self._config = config

    def _uid(self, session_user_id: str | None) -> str:
        if not session_user_id:
            raise ForbiddenError("Authentication required")
        return str(session_user_id)

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

    def _user_root(self, user_id: str) -> Path:
        root = Path(self._config.root) / user_id.replace("-", "")
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @task(type="database", api=True, name="sessions_list")
    def sessions_list(self, _session_user_id: str | None = None) -> dict[str, Any]:
        uid = self._uid(_session_user_id)
        rows = self._db.fetch(
            "SELECT * FROM term.sessions WHERE user_id = %s ORDER BY created_at DESC",
            uid,
        )
        return {"items": [self._public(row) for row in rows]}

    @task(type="database", api=True, name="session_create")
    def session_create(self, title: str | None = None, _session_user_id: str | None = None) -> dict[str, Any]:
        uid = self._uid(_session_user_id)
        cwd = str(self._user_root(uid))
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

    @task(type="database", api=True, name="session_delete")
    def session_delete(self, session_id: str, _session_user_id: str | None = None) -> dict[str, Any]:
        uid = self._uid(_session_user_id)
        self._row(session_id, uid)
        self._db.execute("DELETE FROM term.sessions WHERE id = %s AND user_id = %s", session_id, uid)
        return {"ok": True}

    @task(type="cpu", api=True, name="exec")
    async def exec(
        self,
        session_id: str,
        argv: list[str] | None = None,
        command: str | None = None,
        _session_user_id: str | None = None,
    ) -> dict[str, Any]:
        uid = self._uid(_session_user_id)
        row = self._row(session_id, uid)
        parts = list(argv or [])
        if not parts and command:
            parts = shlex.split(command)
        if not parts:
            raise TermError("Empty command", "VALIDATION", "Command is required")
        binary = shutil.which(parts[0]) or parts[0]
        resolved = Path(binary).resolve()
        if resolved.name not in _ALLOWED or resolved.parent.as_posix() not in {"/bin", "/usr/bin"}:
            raise ForbiddenError("Command is not allowed")
        cwd = Path(str(row["cwd"])).resolve()
        root = self._user_root(uid)
        try:
            cwd.relative_to(root)
        except ValueError as exc:
            raise ForbiddenError("cwd outside sandbox") from exc
        argv_run = [str(resolved), *parts[1:]]

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                argv_run,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._config.timeout_sec,
                check=False,
                env={"PATH": "/usr/bin:/bin", "HOME": str(root), "LANG": "C"},
            )

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired as exc:
            raise TermError("Timed out", "TIMEOUT", "Command timed out") from exc
        stdout = (proc.stdout or "")[: self._config.output_limit]
        stderr = (proc.stderr or "")[: self._config.output_limit]
        self._db.execute(
            "UPDATE term.sessions SET status = 'idle', updated_at = NOW() WHERE id = %s",
            session_id,
        )
        if self._log is not None:
            self._log.info(
                "term_exec",
                extra={"session_id": session_id, "argv0": resolved.name, "exit": proc.returncode},
            )
        return {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode}
