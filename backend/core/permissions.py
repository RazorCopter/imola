"""Permessi applicati a livello di API (non solo di interfaccia)."""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from core import roles

SUPPLIER_WRITABLE_PATHS = ("/imports",)


class IsAuthenticatedRole(BasePermission):
    message = "Operazione non consentita per il tuo ruolo."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)


class IsAdmin(IsAuthenticatedRole):
    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and roles.is_admin(request.user)


class ReadOnlyOrLedgerWriter(IsAuthenticatedRole):
    """Tutti leggono; scrivono solo Admin e Responsabile BMED."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return roles.can_write_ledger(request.user)


class ReferentCanAnnotate(ReadOnlyOrLedgerWriter):
    """Come sopra, ma il Referente BMED può annotare i propri progetti.

    Il permesso di oggetto consente al referente solo i campi di annotazione, filtrati dal
    serializer (note, punti verificati). La verifica di appartenenza è qui.
    """

    annotation_fields = {"notes", "verification_points", "planned_end_date"}

    def has_permission(self, request, view) -> bool:
        if IsAuthenticatedRole.has_permission(self, request, view) is False:
            return False
        if request.method in SAFE_METHODS:
            return True
        if roles.can_write_ledger(request.user):
            return True
        if roles.has_role(request.user, roles.REFERENT) and request.method == "PATCH":
            return set(request.data or {}) <= self.annotation_fields
        return False

    @staticmethod
    def can_annotate(user, obj) -> bool:
        if roles.can_write_ledger(user):
            return True
        if not roles.has_role(user, roles.REFERENT):
            return False
        owner = getattr(obj, "client_owner", None)
        email = (getattr(owner, "email", "") or "").lower()
        user_email = (user.email or "").lower()
        if bool(email) and email == user_email:
            return True
        username = (user.username or "").lower()
        if owner and (getattr(owner, "first_name", "") or getattr(owner, "last_name", "")):
            combined = f"{owner.first_name}{owner.last_name}".lower()
            if username and (username in combined or combined in username):
                return True
        return False

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return self.can_annotate(request.user, obj)


class CanUploadImports(IsAuthenticatedRole):
    """Il fornitore può caricare estratti; restano in DRY_RUN fino all'approvazione."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return roles.has_role(request.user, roles.ADMIN, roles.MANAGER, roles.SUPPLIER)


class CanApplyImports(IsAuthenticatedRole):
    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and roles.can_write_ledger(request.user)
