"""Term module — named linux sessions inside the belle container."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from modules_system.module_base import ModuleBase, ModuleMeta

from .config import TermConfig
from .provider import TermProvider
from .schema import TERM_SCHEMA

__all__ = ["TermModule", "TermProvider", "TermConfig"]

MODULE_VERSION = "0.1.0"


class TermModule(ModuleBase):
    @property
    def name(self) -> str:
        return "term"

    @property
    def version(self) -> str:
        return MODULE_VERSION

    @property
    def meta(self) -> ModuleMeta:
        return ModuleMeta(
            dependencies=["db", "auth", "log", "fs"],
            cache_rules={},
            timeout_defaults={"sessions_list": 5.0, "session_create": 5.0},
            load_on="all",
            is_system=False,
            display_name="Terminal",
            is_example=False,
        )

    def __init__(self, config: TermConfig | None = None) -> None:
        self._config = config or TermConfig.from_env()
        self._log: Any | None = None
        self._provider: TermProvider | None = None

    def on_load(self, state: Any) -> None:
        self._log = state.log
        from modules.db.provider import DatabaseProvider

        database = state.services.resolve(DatabaseProvider)
        self.apply_schema(state)
        self._provider = TermProvider(database, self._log, self._config, getattr(state, "fs", None))
        state.services.register(TermProvider, self._provider)
        if self._log is not None:
            self._log.info("term_module_loaded", extra={"version": self.version})

    def apply_schema(self, state: Any) -> None:
        from copy import deepcopy

        from modules.db.provider import DatabaseProvider

        from .schema import TERM_AUTH_SCHEMA

        database = state.services.resolve(DatabaseProvider)
        database.register_schema(
            "term",
            deepcopy(TERM_SCHEMA),
            schema_name="term",
            ddl_dir=str(Path(__file__).resolve().parent / "ddl"),
        )
        # Auth-права по образцу llm: registry.register_sync + сид Everyone прямым
        # SQL в auth.* (идемпотентно, ON CONFLICT DO NOTHING). Everyone — чтобы
        # существующие пользователи не потеряли доступ к терминалу.
        try:
            from modules.auth.provider import AuthProvider

            auth = state.services.resolve(AuthProvider)
            if auth.registry is not None:
                auth.registry.register_sync("term", TERM_AUTH_SCHEMA, is_builtin=False)
            database.execute(
                "INSERT INTO auth.group_roles (group_id, role_id) "
                "SELECT g.id, r.id FROM auth.groups g CROSS JOIN auth.roles r "
                "WHERE g.name = %s AND r.name = %s "
                "ON CONFLICT (group_id, role_id) DO NOTHING",
                "Everyone",
                "term_user",
            )
        except Exception as exc:
            if self._log is not None:
                self._log.warning("term_auth_schema_skipped", extra={"error": str(exc)})

    def on_unload(self) -> None:
        self._provider = None
        self._log = None
