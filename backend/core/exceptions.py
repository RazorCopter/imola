"""Errori in formato RFC 7807 (application/problem+json) con messaggi in italiano."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, AuthenticationFailed, NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_BASE = "https://supplier-ledger.local/errors/"

TITLES: dict[int, str] = {
    400: "Richiesta non valida",
    401: "Autenticazione necessaria",
    403: "Operazione non consentita",
    404: "Risorsa non trovata",
    405: "Metodo non consentito",
    409: "Conflitto con lo stato attuale della risorsa",
    412: "La risorsa è stata modificata da un altro utente",
    413: "File troppo grande",
    428: "Intestazione If-Match obbligatoria",
    429: "Troppe richieste",
    500: "Errore interno del server",
}


class DomainError(APIException):
    """Errore di dominio con un codice stabile usato anche dal frontend."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code = "errore-di-dominio"
    default_detail = "Operazione non valida."

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.default_detail)
        self.extra = extra


class InsufficientResidual(DomainError):
    error_code = "residuo-insufficiente"
    default_detail = (
        "Le giornate richieste superano il residuo disponibile del progetto di origine."
    )


class ExpiredResidual(DomainError):
    error_code = "residuo-scaduto"
    default_detail = "Il residuo del progetto di origine è scaduto e non può essere allocato."


class OfferNotAccepted(DomainError):
    error_code = "offerta-non-accettata"
    default_detail = "Il progetto non può passare ad ATTIVO se l'offerta non è ACCETTATA."


class ClosureDateRequired(DomainError):
    error_code = "data-chiusura-obbligatoria"
    default_detail = "La data di chiusura della consuntivazione è obbligatoria."


class SessionExpired(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "session_expired"
    default_detail = "Sessione scaduta: effettua di nuovo l'accesso."


class StaleResource(APIException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "risorsa-obsoleta"
    default_detail = "La risorsa è stata modificata da un altro utente: ricarica i dati e riprova."


class PreconditionRequired(APIException):
    status_code = 428
    error_code = "precondizione-richiesta"
    default_detail = "Serve l'intestazione If-Match con la versione della risorsa."


def _flatten(detail: Any, prefix: str = "") -> list[dict[str, str]]:
    """Trasforma i dettagli di validazione DRF in una lista piatta campo/messaggio."""
    errors: list[dict[str, str]] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            errors.extend(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(detail, list):
        for value in detail:
            errors.extend(_flatten(value, prefix))
    else:
        errors.append({"campo": prefix or "__all__", "messaggio": str(detail)})
    return errors


def problem_detail_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DjangoValidationError):
        detail: Any = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        exc = APIException(detail=detail)
        exc.status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, Http404):
        exc = APIException(detail="Risorsa non trovata.")
        exc.status_code = status.HTTP_404_NOT_FOUND
    if isinstance(exc, PermissionDenied):
        exc = APIException(detail="Operazione non consentita.")
        exc.status_code = status.HTTP_403_FORBIDDEN

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    # DRF trasforma NotAuthenticated in 403 quando l'autenticazione è a sessione (manca
    # l'intestazione WWW-Authenticate). Qui si ripristina il 401 con codice
    # `session_expired`: il frontend lo usa per mostrare il modale di re-login senza
    # eseguire il logout e senza buttare via il lavoro in corso.
    if isinstance(exc, NotAuthenticated):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        exc = SessionExpired()
    elif isinstance(exc, AuthenticationFailed):
        response.status_code = status.HTTP_401_UNAUTHORIZED

    code = getattr(exc, "error_code", None) or f"http-{response.status_code}"
    detail = getattr(exc, "detail", None)
    request = context.get("request")
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE}{code}",
        "title": TITLES.get(response.status_code, "Errore"),
        "status": response.status_code,
        "code": code,
        "detail": str(detail) if not isinstance(detail, (dict, list)) else None,
        "instance": getattr(request, "path", None),
    }
    if isinstance(detail, (dict, list)):
        flattened = _flatten(detail)
        body["detail"] = flattened[0]["messaggio"] if flattened else "Richiesta non valida."
        body["errors"] = flattened
    body.update(getattr(exc, "extra", {}) or {})

    response.data = body
    response.content_type = PROBLEM_CONTENT_TYPE
    return response
