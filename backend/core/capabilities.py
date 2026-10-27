"""Catalogo canonico e risoluzione persistente delle capability per ruolo."""

from __future__ import annotations

from typing import Final

from core import roles

RESET_DATA: Final = "data.reset"
MANAGE_USERS: Final = "users.manage"
MANAGE_PRIVILEGES: Final = "privileges.manage"
CREATE_PROJECTS: Final = "projects.create"
EDIT_PROJECTS: Final = "projects.edit"
VALIDATE_PROJECT_CLOSURE: Final = "projects.validate_closure"
ANNOTATE_OWN_PROJECTS: Final = "projects.annotate_own"
CREATE_TIMESHEETS: Final = "timesheets.create"
EDIT_WALLET: Final = "wallet.edit"
MANAGE_CANONE: Final = "canone.manage"
ADJUST_ACCOUNTING: Final = "accounting.adjust"
UPLOAD_IMPORTS: Final = "imports.upload"
APPLY_IMPORTS: Final = "imports.apply"
EXPORT_DATA: Final = "exports.run"
RESOLVE_ANOMALIES: Final = "anomalies.resolve"

ALL_CAPABILITIES: Final = frozenset(
    {
        RESET_DATA,
        MANAGE_USERS,
        MANAGE_PRIVILEGES,
        CREATE_PROJECTS,
        EDIT_PROJECTS,
        VALIDATE_PROJECT_CLOSURE,
        ANNOTATE_OWN_PROJECTS,
        CREATE_TIMESHEETS,
        EDIT_WALLET,
        MANAGE_CANONE,
        ADJUST_ACCOUNTING,
        UPLOAD_IMPORTS,
        APPLY_IMPORTS,
        EXPORT_DATA,
        RESOLVE_ANOMALIES,
    }
)

ROLE_DEFAULTS: Final = {
    roles.ADMIN: ALL_CAPABILITIES,
    roles.MANAGER: frozenset(
        {
            CREATE_PROJECTS,
            EDIT_PROJECTS,
            VALIDATE_PROJECT_CLOSURE,
            ANNOTATE_OWN_PROJECTS,
            CREATE_TIMESHEETS,
            EDIT_WALLET,
            MANAGE_CANONE,
            ADJUST_ACCOUNTING,
            UPLOAD_IMPORTS,
            APPLY_IMPORTS,
            EXPORT_DATA,
            RESOLVE_ANOMALIES,
        }
    ),
    roles.REFERENT: frozenset({ANNOTATE_OWN_PROJECTS, EXPORT_DATA}),
    roles.SUPPLIER: frozenset(
        {
            CREATE_PROJECTS,
            VALIDATE_PROJECT_CLOSURE,
            CREATE_TIMESHEETS,
            UPLOAD_IMPORTS,
            EXPORT_DATA,
        }
    ),
}

RESERVED_CAPABILITIES: Final = frozenset({RESET_DATA, MANAGE_USERS, MANAGE_PRIVILEGES})


def capabilities_for_role(role: str) -> set[str]:
    """Legge gli override dal DB a ogni richiesta; in assenza usa i default canonici."""
    if role == roles.ADMIN:
        return set(ALL_CAPABILITIES)
    defaults = set(ROLE_DEFAULTS.get(role, ()))
    from core.models import RoleCapabilityOverride

    overrides = RoleCapabilityOverride.objects.filter(role=role).values_list(
        "capability", "enabled"
    )
    for capability, enabled in overrides:
        if capability in RESERVED_CAPABILITIES:
            continue
        if enabled:
            defaults.add(capability)
        else:
            defaults.discard(capability)
    return defaults - set(RESERVED_CAPABILITIES)


def capabilities_for(user) -> set[str]:
    """Restituisce l'unione delle capability effettive dei ruoli correnti."""
    effective: set[str] = set()
    for role in roles.roles_of(user):
        effective.update(capabilities_for_role(role))
    return effective


def has_capability(user, capability: str) -> bool:
    return capability in capabilities_for(user)
