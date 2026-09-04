"""Ошибки term."""
from __future__ import annotations

__all__ = ["TermError", "ForbiddenError", "NotFoundError"]


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
