"""Catalogo statico delle capability applicative e default per ruolo.

Le capability sono il contratto canonico condiviso da API e frontend. In questa tranche i
valori effettivi derivano dai gruppi/ruoli Django esistenti; la configurabilità persistente è
rinviata e non richiede migrazioni.
"""

from __future__ import annotations

from typing import Final

from core import roles

RESET_DATA: Final = "data.reset"
MANAGE_USERS: Final = "users.manage"
MANAGE_PRIVILEGES: Final = "privileges.manage"
CREATE_PROJECTS: Final = "projects.create"
EDIT_PROJECTS: Final = "projects.edit"
ANNOTATE_OWN_PROJECTS: Final = "projects.annotate_own"
CREATE_TIMESHEETS: Final = "timesheets.create"
EDIT_WALLET: Final = "wallet.edit"
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
        ANNOTATE_OWN_PROJECTS,
        CREATE_TIMESHEETS,
        EDIT_WALLET,
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
            ANNOTATE_OWN_PROJECTS,
            CREATE_TIMESHEETS,
            EDIT_WALLET,
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
            CREATE_TIMESHEETS,
            UPLOAD_IMPORTS,
            EXPORT_DATA,
        }
    ),
}


def capabilities_for(user) -> set[str]:
    """Restituisce le capability effettive derivanti dai ruoli correnti dell'utente."""
    effective: set[str] = set()
    for role in roles.roles_of(user):
        effective.update(ROLE_DEFAULTS.get(role, ()))
    return effective


def has_capability(user, capability: str) -> bool:
    return capability in capabilities_for(user)
