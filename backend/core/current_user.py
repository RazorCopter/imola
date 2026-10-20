"""Utente della richiesta corrente, per popolare created_by/updated_by."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

_current_user: ContextVar[Any | None] = ContextVar("current_user", default=None)


def set_current_user(user: AbstractBaseUser | None) -> None:
    _current_user.set(user if user is not None and user.is_authenticated else None)


def get_current_user() -> Any | None:
    return _current_user.get()


@contextmanager
def acting_as(user: Any | None):
    """Usato dai comandi di management e dai test."""
    token = _current_user.set(user)
    try:
        yield
    finally:
        _current_user.reset(token)
