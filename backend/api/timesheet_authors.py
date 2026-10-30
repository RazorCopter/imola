"""Chi risulta autore di un consuntivo.

Di norma l'autore è chi scrive: `created_by` coincide con l'utente della richiesta. L'Admin
però censisce consuntivi anche per conto del fornitore (Imola), quindi può indicare un altro
utente nel campo `utente` del payload. La capability `timesheets.assign_author` è riservata
(vedi `core.capabilities.RESERVED_CAPABILITIES`): nessun altro ruolo può ottenerla.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core import capabilities, roles
from core.permissions import CanAssignTimesheetAuthor


def _roles_that_can_consuntivare() -> set[str]:
    return {
        role
        for role in roles.ALL_ROLES
        if capabilities.CREATE_TIMESHEETS in capabilities.capabilities_for_role(role)
    }


def assignable_authors():
    """Utenti attivi che potrebbero consuntivare in prima persona, ordinati per username."""
    user_model = get_user_model()
    allowed = _roles_that_can_consuntivare()
    users = user_model.objects.filter(is_active=True).prefetch_related("groups")
    return [
        user
        for user in users.order_by("username")
        if user.is_superuser or (set(user.groups.values_list("name", flat=True)) & allowed)
    ]


def author_payload(user) -> dict:
    return {
        "id": user.pk,
        "username": user.username,
        "full_name": user.get_full_name() or user.username,
        "roles": sorted(roles.roles_of(user)),
    }


def resolve_author(request, default=None):
    """Autore da scrivere in `created_by`: l'utente indicato se l'Admin lo ha scelto.

    Senza il campo `utente` resta `default` (di norma l'utente della richiesta), così i
    client esistenti non cambiano comportamento.
    """
    raw = request.data.get("utente", request.data.get("utente_id"))
    fallback = default if default is not None else request.user
    if raw in (None, ""):
        return fallback
    if not capabilities.has_capability(request.user, capabilities.ASSIGN_TIMESHEET_AUTHOR):
        raise DjangoValidationError(
            {"utente": "Solo l'Admin può registrare consuntivi a nome di un altro utente."}
        )
    author = next((user for user in assignable_authors() if str(user.pk) == str(raw)), None)
    if author is None:
        raise DjangoValidationError({"utente": "Utente non valido per la consuntivazione."})
    return author


class TimesheetAuthorsResponseSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())


class TimesheetAuthorListView(APIView):
    """Utenti selezionabili come autori di un consuntivo. Solo Admin."""

    permission_classes = [CanAssignTimesheetAuthor]
    serializer_class = TimesheetAuthorsResponseSerializer

    @extend_schema(responses={200: TimesheetAuthorsResponseSerializer})
    def get(self, request):
        return Response({"results": [author_payload(user) for user in assignable_authors()]})
