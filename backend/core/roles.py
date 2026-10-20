"""Ruoli applicativi, mappati su gruppi Django."""

from __future__ import annotations

from django.contrib.auth.models import Group

ADMIN = "admin"
MANAGER = "responsabile_bmed"
REFERENT = "referente_bmed"
SUPPLIER = "fornitore"

ALL_ROLES = (ADMIN, MANAGER, REFERENT, SUPPLIER)

LABELS = {
    ADMIN: "Amministratore",
    MANAGER: "Responsabile BMED",
    REFERENT: "Referente BMED",
    SUPPLIER: "Fornitore (Imola)",
}


def ensure_groups() -> list[Group]:
    """Crea i gruppi mancanti. Idempotente, invocata dalle migrazioni dati e dal setup."""
    return [Group.objects.get_or_create(name=role)[0] for role in ALL_ROLES]


def roles_of(user) -> set[str]:
    if user is None or not user.is_authenticated:
        return set()
    roles = set(user.groups.values_list("name", flat=True)) & set(ALL_ROLES)
    if user.is_superuser:
        roles.add(ADMIN)
    return roles


def has_role(user, *roles: str) -> bool:
    return bool(roles_of(user) & set(roles))


def is_admin(user) -> bool:
    return has_role(user, ADMIN)


def can_write_ledger(user) -> bool:
    """Scrittura su progetti, wallet, canone."""
    return has_role(user, ADMIN, MANAGER)
