"""ETag e lock ottimistico.

Ogni entità modificabile espone `version`. La GET restituisce un ETag debole derivato da
(id, version); la PATCH deve inviare `If-Match` con quell'ETag. Se la versione nel frattempo
è cambiata si risponde 412 invece di sovrascrivere il lavoro di un altro utente, e 428 se
l'intestazione manca del tutto.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework.response import Response

from core.exceptions import PreconditionRequired, StaleResource

if TYPE_CHECKING:  # pragma: no cover - solo per il type checker
    from rest_framework.generics import GenericAPIView

    MixinBase = GenericAPIView
else:
    MixinBase = object


def make_etag(obj: Any) -> str:
    return f'W/"{obj.pk}-{getattr(obj, "version", 1)}"'


def etag_matches(header: str, obj: Any) -> bool:
    """Confronto tollerante: accetta la forma debole, quella forte e il jolly."""
    if not header:
        return False
    current = make_etag(obj)
    candidates = {value.strip() for value in header.split(",")}
    return bool(candidates & {"*", current, current.replace("W/", "")})


class OptimisticLockMixin(MixinBase):
    """Da combinare con un ViewSet su entità versionate."""

    unsafe_methods = ("PUT", "PATCH", "DELETE")

    def check_precondition(self, instance: Any) -> None:
        if self.request.method not in self.unsafe_methods:
            return
        header = self.request.headers.get("If-Match", "")
        if not header:
            raise PreconditionRequired()
        if not etag_matches(header, instance):
            raise StaleResource(
                detail=(
                    "La risorsa è stata modificata da un altro utente "
                    f"(versione attuale {getattr(instance, 'version', '?')}): "
                    "ricarica i dati e riprova."
                )
            )

    def get_object(self) -> Any:
        instance = super().get_object()
        self.check_precondition(instance)
        return instance

    def finalize_response(self, request: Any, response: Any, *args: Any, **kwargs: Any) -> Any:
        response = super().finalize_response(request, response, *args, **kwargs)
        instance = getattr(self, "_etag_instance", None)
        if instance is not None and response.status_code < 400:
            response["ETag"] = make_etag(instance)
        return response

    def retrieve(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        self._etag_instance = instance
        return Response(self.get_serializer(instance).data)

    def update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=kwargs.pop("partial", False)
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        instance.refresh_from_db()
        self._etag_instance = instance
        return Response(serializer.data)

    def partial_update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        return self.update(request, *args, partial=True, **kwargs)
