"""Astrazione del provider di autenticazione.

In v1 è attivo solo il provider locale (sessione Django + CSRF). Il provider OIDC per
Microsoft Entra ID è dichiarato ma non registrato: aggiungere la dipendenza e impostare
AUTH_PROVIDER=entra_id quando il rapporto con l'IDP sarà configurato.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest


@dataclass(frozen=True)
class AuthResult:
    user: Any | None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.user is not None


class AuthProvider(Protocol):
    name: str

    def login(self, request: HttpRequest, **credentials: str) -> AuthResult: ...

    def logout(self, request: HttpRequest) -> None: ...

    @property
    def interactive(self) -> bool: ...


class LocalSessionProvider:
    """Login con username e password, sessione Django."""

    name = "local"
    interactive = True

    def login(self, request: HttpRequest, **credentials: str) -> AuthResult:
        user = authenticate(
            request,
            username=credentials.get("username", ""),
            password=credentials.get("password", ""),
        )
        if user is None:
            return AuthResult(None, "Credenziali non valide.")
        if not user.is_active:
            return AuthResult(None, "Utenza disattivata.")
        login(request, user)
        return AuthResult(user)

    def logout(self, request: HttpRequest) -> None:
        logout(request)


class EntraIdOidcProvider:
    """Segnaposto per l'accesso federato: non implementato in v1."""

    name = "entra_id"
    interactive = False

    def login(self, request: HttpRequest, **credentials: str) -> AuthResult:
        raise NotImplementedError("Il provider Microsoft Entra ID non è attivo in questa versione.")

    def logout(self, request: HttpRequest) -> None:
        logout(request)


_PROVIDERS: dict[str, type] = {
    LocalSessionProvider.name: LocalSessionProvider,
    EntraIdOidcProvider.name: EntraIdOidcProvider,
}


def get_auth_provider() -> AuthProvider:
    name = getattr(settings, "AUTH_PROVIDER", "local")
    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        raise RuntimeError(f"Provider di autenticazione sconosciuto: {name}")
    return provider_cls()
