from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from core.current_user import set_current_user


class CurrentUserMiddleware:
    """Rende disponibile l'utente della richiesta ai modelli."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        set_current_user(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)
