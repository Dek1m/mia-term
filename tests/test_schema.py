"""TERM_AUTH_SCHEMA: контракт прав и @task permission модуля term."""
from __future__ import annotations

import inspect

from term.schema import TERM_AUTH_SCHEMA


def test_auth_schema_shape() -> None:
    perms = TERM_AUTH_SCHEMA["permissions"]
    roles = TERM_AUTH_SCHEMA["roles"]
    assert [p["name"] for p in perms] == ["term:access"]
    assert all(p["description"] for p in perms)
    assert [r["name"] for r in roles] == ["term_user"]
    assert roles[0]["permissions"] == ["term:access"]
    assert roles[0]["description"]


def test_rpc_tasks_require_term_access() -> None:
    """sessions_list/session_create/session_delete — permission term:access."""
    import term.provider as provider_mod

    source = inspect.getsource(provider_mod)
    for name in ("sessions_list", "session_create", "session_delete"):
        assert f'name="{name}", permission="term:access"' in source, name
