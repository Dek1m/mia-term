"""Linux-аккаунт albedo-пользователя: /home/{username}, uid >= 1000."""
from __future__ import annotations

import fcntl
import os
import pwd
import subprocess
from pathlib import Path

from .errors import TermError

__all__ = ["Account", "ensure_account", "linux_name"]

_BASHRC = """# albedo term — gentoo-style prompt
export TERM=xterm-256color
export EDITOR=nano
alias ls='ls --color=auto'
alias grep='grep --colour=auto'
if [[ ${EUID} == 0 ]] ; then
  PS1='\\[\\033[01;31m\\]\\h\\[\\033[01;34m\\] \\W \\$\\[\\033[00m\\] '
else
  PS1='\\[\\033[01;32m\\]\\u@belle\\[\\033[01;34m\\] \\w \\$\\[\\033[00m\\] '
fi
"""

_PROFILE = """[[ -f ~/.bashrc ]] && . ~/.bashrc
"""

_RESERVED = frozenset({
    "root", "bin", "daemon", "sys", "sync", "games", "man", "lp", "mail",
    "news", "uucp", "proxy", "www-data", "backup", "list", "irc", "gnats",
    "nobody", "systemd", "messagebus", "sshd", "uuidd",
})


class Account:
    def __init__(self, name: str, home: Path, uid: int, gid: int) -> None:
        self.name = name
        self.home = home
        self.uid = uid
        self.gid = gid


def linux_name(username: str) -> str:
    name = (username or "").strip()
    if not name.isalnum() or len(name) > 32:
        raise TermError("Invalid username", "VALIDATION", "Invalid username")
    if name.lower() in _RESERVED:
        raise TermError("Username is reserved", "FORBIDDEN", "Username is reserved")
    return name


def ensure_account(username: str, home_root: str) -> Account:
    name = linux_name(username)
    home = Path(home_root) / name
    lock_path = Path("/tmp") / f"albedo-term-{name}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        pw = _lookup_or_create(name, home)
        if pw.pw_uid < 1000:
            raise TermError("Username is reserved", "FORBIDDEN", "Username is reserved")
        home.mkdir(parents=True, exist_ok=True)
        if home.stat().st_uid == 0:
            _chown_tree(home, pw.pw_uid, pw.pw_gid)
        _dotfile(home / ".bashrc", _BASHRC, pw.pw_uid, pw.pw_gid)
        _dotfile(home / ".bash_profile", _PROFILE, pw.pw_uid, pw.pw_gid)
        os.chown(home, pw.pw_uid, pw.pw_gid)
        return Account(name, home, pw.pw_uid, pw.pw_gid)


def _lookup_or_create(name: str, home: Path) -> pwd.struct_passwd:
    try:
        return pwd.getpwnam(name)
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "-M",
                "-d", str(home),
                "-s", "/bin/bash",
                name,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return pwd.getpwnam(name)


def _dotfile(path: Path, content: str, uid: int, gid: int) -> None:
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")
    os.chown(path, uid, gid)
    os.chmod(path, 0o644)


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        os.chown(dirpath, uid, gid)
        for name in dirnames + filenames:
            os.chown(os.path.join(dirpath, name), uid, gid)
