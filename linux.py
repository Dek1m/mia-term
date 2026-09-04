"""Home и gentoo-prompt. Unix-аккаунт — fs.unix_accounts, не свой useradd."""
from __future__ import annotations

import os
import pwd
from pathlib import Path
from typing import Any

from .errors import TermError

__all__ = ["Account", "account_from_fs", "linux_name"]

_MARKER = "# albedo term — gentoo-style prompt"

_PROFILE = """[[ -f ~/.bashrc ]] && . ~/.bashrc
"""


class Account:
    def __init__(self, name: str, login: str, home: Path, uid: int, gid: int) -> None:
        self.name = name
        self.login = login
        self.home = home
        self.uid = uid
        self.gid = gid


def linux_name(username: str) -> str:
    name = (username or "").strip()
    if not name.isalnum() or len(name) > 32:
        raise TermError("Invalid username", "VALIDATION", "Invalid username")
    return name


def account_from_fs(info: dict[str, Any], username: str) -> Account:
    name = linux_name(username)
    uid = int(info["unix_uid"])
    login = str(info["login"])
    home = Path(str(info.get("home") or info.get("home_path")))
    if uid < 1000:
        raise TermError("Username is reserved", "FORBIDDEN", "Username is reserved")
    try:
        gid = pwd.getpwuid(uid).pw_gid
    except KeyError:
        gid = uid
    home.mkdir(parents=True, exist_ok=True)
    bashrc = f"""{_MARKER}
export TERM=xterm-256color
export EDITOR=nano
alias ls='ls --color=auto'
alias grep='grep --colour=auto'
PS1='\\[\\033[01;32m\\]{name}@belle\\[\\033[01;34m\\] \\w \\$\\[\\033[00m\\] '
"""
    _dotfile(home / ".bashrc", bashrc, uid, gid, replace_marker=_MARKER)
    _dotfile(home / ".bash_profile", _PROFILE, uid, gid)
    return Account(name, login, home, uid, gid)


def _dotfile(path: Path, content: str, uid: int, gid: int, replace_marker: str | None = None) -> None:
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        if replace_marker is None or not raw.startswith(replace_marker):
            return
    path.write_text(content, encoding="utf-8")
    os.chown(path, uid, gid)
    os.chmod(path, 0o644)
