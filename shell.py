"""PTY bash в home пользователя."""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import subprocess
import termios
from typing import Any

from .linux import Account

__all__ = ["LiveShell", "bridge"]


class LiveShell:
    def __init__(self, account: Account) -> None:
        self._account = account
        self._proc: subprocess.Popen[bytes] | None = None
        self._master: int | None = None

    @property
    def fd(self) -> int:
        if self._master is None:
            raise RuntimeError("shell is not started")
        return self._master

    def start(self, cols: int = 80, rows: int = 24) -> None:
        master, slave = pty.openpty()
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        account = self._account
        env = {
            "HOME": str(account.home),
            "USER": account.name,
            "LOGNAME": account.name,
            "SHELL": "/bin/bash",
            "TERM": "xterm-256color",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
        }

        def preexec() -> None:
            os.setsid()
            os.chdir(account.home)
            os.setgid(account.gid)
            try:
                os.initgroups(account.name, account.gid)
            except OSError:
                pass
            os.setuid(account.uid)

        self._proc = subprocess.Popen(
            ["/bin/bash", "-l"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            preexec_fn=preexec,
            close_fds=True,
        )
        os.close(slave)
        os.set_blocking(master, False)
        self._master = master

    def resize(self, cols: int, rows: int) -> None:
        if self._master is None:
            return
        cols = max(2, min(cols, 512))
        rows = max(2, min(rows, 256))
        fcntl.ioctl(self._master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def write(self, data: bytes) -> None:
        if self._master is None or not data:
            return
        os.write(self._master, data)

    def close(self) -> None:
        proc = self._proc
        master = self._master
        self._proc = None
        self._master = None
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGHUP)
            except OSError:
                proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        if master is not None:
            try:
                os.close(master)
            except OSError:
                pass


async def bridge(websocket: Any, shell: LiveShell) -> None:
    loop = asyncio.get_running_loop()
    incoming: asyncio.Queue[bytes | None] = asyncio.Queue()

    def on_fd() -> None:
        try:
            chunk = os.read(shell.fd, 8192)
        except OSError:
            chunk = b""
        incoming.put_nowait(chunk or None)

    loop.add_reader(shell.fd, on_fd)

    async def to_client() -> None:
        while True:
            chunk = await incoming.get()
            if chunk is None:
                break
            await websocket.send_bytes(chunk)

    async def from_client() -> None:
        while True:
            message = await websocket.receive()
            kind = message.get("type")
            if kind == "websocket.disconnect":
                break
            raw_bytes = message.get("bytes")
            if raw_bytes:
                shell.write(raw_bytes)
                continue
            text = message.get("text")
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                shell.write(text.encode("utf-8"))
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("type") == "resize":
                shell.resize(int(payload.get("cols") or 80), int(payload.get("rows") or 24))
            elif payload.get("type") == "input":
                shell.write(str(payload.get("data") or "").encode("utf-8"))

    tasks = [
        asyncio.create_task(to_client()),
        asyncio.create_task(from_client()),
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception() if not task.cancelled() else None
            if exc is not None:
                raise exc
    finally:
        loop.remove_reader(shell.fd)
        for task in tasks:
            if not task.done():
                task.cancel()
        shell.close()
