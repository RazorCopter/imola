"""Autenticazione di sessione.

Nessun logout automatico lato client: se la sessione scade l'API risponde 401 con
`code=session_expired` e il frontend mostra un modale di re-login che conserva il lavoro
in corso e ritenta la richiesta.
"""

from __future__ import annotations

from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import capabilities, roles
from core.auth.providers import get_auth_provider
from core.throttles import LoginRateThrottle


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"}, trim_whitespace=False)


class SessionSerializer(serializers.Serializer):
    username = serializers.CharField()
    full_name = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    roles = serializers.ListField(child=serializers.CharField())
    capabilities = serializers.ListField(child=serializers.CharField())
    is_admin = serializers.BooleanField()
    can_write = serializers.BooleanField()


def session_payload(user) -> dict:
    user_roles = sorted(roles.roles_of(user))
    return {
        "username": user.username,
        "full_name": user.get_full_name() or user.username,
        "email": user.email or "",
        "roles": user_roles,
        "capabilities": sorted(capabilities.capabilities_for(user)),
        "is_admin": roles.is_admin(user),
        "can_write": roles.can_write_ledger(user),
    }


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]
    throttle_scope = "login"
    serializer_class = LoginSerializer

    @extend_schema(request=LoginSerializer, responses={200: SessionSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = get_auth_provider()
        result = provider.login(request, **serializer.validated_data)
        if not result.ok:
            return Response(
                {
                    "type": "https://supplier-ledger.local/errors/credenziali-non-valide",
                    "title": "Autenticazione necessaria",
                    "status": status.HTTP_401_UNAUTHORIZED,
                    "code": "credenziali-non-valide",
                    "detail": result.detail or "Credenziali non valide.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
                content_type="application/problem+json",
            )
        response = Response(session_payload(result.user))
        response["X-CSRFToken"] = get_token(request)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        get_auth_provider().logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionView(APIView):
    """Stato della sessione corrente: usata all'avvio del frontend."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SessionSerializer})
    def get(self, request):
        get_token(request)  # assicura il cookie CSRF
        return Response(session_payload(request.user))
