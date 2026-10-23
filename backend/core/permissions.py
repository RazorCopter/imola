"""Permessi applicati a livello di API (non solo di interfaccia)."""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from core import capabilities


class IsAuthenticatedRole(BasePermission):
    message = "Operazione non consentita per il tuo ruolo."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)


class HasCapability(IsAuthenticatedRole):
    """Base per permission server-side associate a una capability canonica."""

    capability = ""

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and capabilities.has_capability(
            request.user, self.capability
        )


class IsAdmin(HasCapability):
    capability = capabilities.MANAGE_PRIVILEGES


class CanResetData(HasCapability):
    capability = capabilities.RESET_DATA


class CanManageUsers(HasCapability):
    capability = capabilities.MANAGE_USERS


class CanManagePrivileges(HasCapability):
    capability = capabilities.MANAGE_PRIVILEGES


class CanCreateProjects(HasCapability):
    capability = capabilities.CREATE_PROJECTS


class ReadOnlyOrCanCreateProjects(IsAuthenticatedRole):
    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.method in SAFE_METHODS or capabilities.has_capability(
            request.user, capabilities.CREATE_PROJECTS
        )


class CanEditWallet(HasCapability):
    capability = capabilities.EDIT_WALLET


class CanAdjustAccounting(HasCapability):
    capability = capabilities.ADJUST_ACCOUNTING


class CanResolveAnomalies(HasCapability):
    capability = capabilities.RESOLVE_ANOMALIES


class CanExport(HasCapability):
    capability = capabilities.EXPORT_DATA


class ReadOnlyOrLedgerWriter(IsAuthenticatedRole):
    """Compatibilità endpoint correnti: lettura autenticata, mutation contabile granulare."""

    capability = capabilities.ADJUST_ACCOUNTING

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return capabilities.has_capability(request.user, self.capability)


class ReferentCanAnnotate(ReadOnlyOrLedgerWriter):
    """Come sopra, ma il Referente BMED può annotare i propri progetti.

    Il permesso di oggetto consente al referente solo i campi di annotazione, filtrati dal
    serializer (note, punti verificati). La verifica di appartenenza è qui.
    """

    annotation_fields = {"notes", "verification_points", "planned_end_date", "expected_version"}

    def has_permission(self, request, view) -> bool:
        if IsAuthenticatedRole.has_permission(self, request, view) is False:
            return False
        if request.method in SAFE_METHODS:
            return True
        if capabilities.has_capability(request.user, capabilities.EDIT_PROJECTS):
            return True
        if (
            capabilities.has_capability(request.user, capabilities.ANNOTATE_OWN_PROJECTS)
            and request.method == "PATCH"
        ):
            return set(request.data or {}) <= self.annotation_fields
        return False

    @staticmethod
    def can_annotate(user, obj) -> bool:
        if capabilities.has_capability(user, capabilities.EDIT_PROJECTS):
            return True
        if not capabilities.has_capability(user, capabilities.ANNOTATE_OWN_PROJECTS):
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


class CanUploadImports(HasCapability):
    """Il fornitore può caricare estratti; restano in DRY_RUN fino all'approvazione."""

    capability = capabilities.UPLOAD_IMPORTS


class CanApplyImports(HasCapability):
    capability = capabilities.APPLY_IMPORTS
