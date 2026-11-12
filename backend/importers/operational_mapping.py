"""Risoluzione delle destinazioni e dei collaboratori dell'estratto operativo.

Regole fissate in docs/importazione_plan.md §3 e §4:

- la chiave è il **codice** dove il codice esiste, cioè `Project.code` per i progetti;
- è il **titolo normalizzato** dove il modello non espone un codice, cioè il sottoprogetto
  wallet e la sotto-attività del canone;
- il confronto è sempre **esatto**: nessuna euristica sui nomi simili. Ciò che non aggancia
  va in Riconciliazione, e l'associazione confermata vale anche per le settimane dopo;
- il canone pertinente si deduce da anno e semestre della data della riga;
- un collaboratore assente viene censito, con avviso; uno ambiguo richiede una scelta.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.contrib.auth.models import Group, User
from django.db.models import Q

from canone.models import Canone, CanoneSubactivity
from core import roles
from directory.models import Organization, OrganizationKind, Person
from directory.normalization import comparison_key, titlecase_name
from importers.operational_excel import Level, Problem, Section, SourceRow, normalize_key
from imports.models import ImportMapping, ImportRowSection, MappingKind
from projects.models import Project
from wallet.models import AllocationStatus, WalletAllocation

SECTION_TO_ROW_SECTION = {
    Section.PROGETTI: ImportRowSection.PROGETTI,
    Section.WALLET: ImportRowSection.WALLET,
    Section.ORGANICO: ImportRowSection.ORGANICO,
}

# I nomi dell'estratto sono consulenti Imola: il ruolo e l'organizzazione sono una costante
# del formato, non qualcosa da dedurre riga per riga (§4.1).
SUPPLIER_ORG_CODE = "IMOLA"


def semester_of(period: dt.date) -> str:
    """Etichetta del semestre nel formato usato da `Canone.semester`, es. `2026-S2`."""
    return f"{period.year}-S{1 if period.month <= 6 else 2}"


@dataclass
class Candidate:
    """Una destinazione proponibile all'utente quando la risoluzione è ambigua."""

    id: str
    label: str
    detail: str = ""


@dataclass
class Resolution:
    """Esito della risoluzione di una riga."""

    row: SourceRow
    project: Project | None = None
    wallet_allocation: WalletAllocation | None = None
    canone_subactivity: CanoneSubactivity | None = None
    author: User | None = None
    problems: list[Problem] = field(default_factory=list)
    candidates: dict[str, list[Candidate]] = field(default_factory=dict)
    created_collaborator: User | None = None

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.level is Level.ERROR]

    @property
    def needs_mapping(self) -> bool:
        return bool(self.candidates)

    @property
    def is_ready(self) -> bool:
        if self.errors or self.candidates:
            return False
        if self.author is None:
            return False
        return self.target is not None

    @property
    def target(self):
        return self.project or self.wallet_allocation or self.canone_subactivity


class Resolver:
    """Risolve le righe di un workbook, riusando le associazioni già confermate.

    Istanza per batch: tiene in memoria gli indici delle anagrafiche, così 45 righe non
    producono 45 interrogazioni per destinazione.
    """

    def __init__(self, *, create_missing_collaborators: bool = True) -> None:
        self.create_missing_collaborators = create_missing_collaborators
        self._projects: dict[str, Project] = {}
        self._allocations: dict[int, dict[str, list[WalletAllocation]]] = {}
        self._subactivities: dict[str, dict[str, list[CanoneSubactivity]]] = {}
        self._users: dict[str, list[User]] = {}
        self._mappings: dict[tuple[str, str, int | None, str], ImportMapping] = {}
        self._loaded = False
        self.created_users: list[User] = []

    # ------------------------------------------------------------------ indici

    def load(self) -> None:
        if self._loaded:
            return
        self._projects = {normalize_key(p.code): p for p in Project.objects.all()}

        for allocation in WalletAllocation.objects.select_related(
            "activity", "wallet_year"
        ).exclude(status=AllocationStatus.CHIUSA):
            year = allocation.wallet_year.year
            by_alias = self._allocations.setdefault(year, {})
            for alias in self._allocation_aliases(allocation, year):
                by_alias.setdefault(alias, []).append(allocation)

        for subactivity in CanoneSubactivity.objects.select_related("canone"):
            semester = subactivity.canone.semester
            by_title = self._subactivities.setdefault(semester, {})
            by_title.setdefault(normalize_key(subactivity.title), []).append(subactivity)

        for user in User.objects.filter(is_active=True):
            full_name = user.get_full_name().strip()
            if full_name:
                self._users.setdefault(comparison_key(full_name), []).append(user)

        for mapping in ImportMapping.objects.select_related(
            "project", "wallet_allocation", "canone_subactivity", "user"
        ):
            key = (
                mapping.kind,
                mapping.external_key,
                mapping.context_year,
                mapping.context_semester,
            )
            self._mappings[key] = mapping
        self._loaded = True

    @staticmethod
    def _allocation_aliases(allocation: WalletAllocation, year: int) -> set[str]:
        """Come il sottoprogetto wallet può essere scritto nell'Excel.

        Nell'estratto reale il valore è `Wallet 2026 Migrazione OSB14 POC`, cioè l'anno
        wallet seguito dal titolo dell'attività. Non è un'euristica sui nomi: è la forma
        canonica del campo, dichiarata, e vale per tutte le righe del foglio.
        """
        title = allocation.activity.title
        code = allocation.activity.code
        aliases = {normalize_key(title), normalize_key(code)}
        aliases.add(normalize_key(f"Wallet {year} {title}"))
        aliases.add(normalize_key(f"Wallet {year} {code}"))
        if allocation.external_ref:
            aliases.add(normalize_key(allocation.external_ref))
        return {a for a in aliases if a}

    # ------------------------------------------------------------- associazioni

    def _mapping_for(
        self,
        kind: MappingKind,
        key: str,
        *,
        year: int | None = None,
        semester: str = "",
    ) -> ImportMapping | None:
        return self._mappings.get((kind.value, key, year, semester))

    # ------------------------------------------------------------------ righe

    def resolve(self, row: SourceRow) -> Resolution:
        self.load()
        resolution = Resolution(row=row)
        if row.section is Section.PROGETTI:
            self._resolve_project(row, resolution)
        elif row.section is Section.WALLET:
            self._resolve_wallet(row, resolution)
        else:
            self._resolve_canone(row, resolution)
        self._resolve_author(row, resolution)
        return resolution

    def resolve_all(self, rows: list[SourceRow]) -> list[Resolution]:
        return [self.resolve(row) for row in rows]

    # -------------------------------------------------------------- progetti

    def _resolve_project(self, row: SourceRow, resolution: Resolution) -> None:
        key = normalize_key(row.project)
        mapping = self._mapping_for(MappingKind.PROGETTO, key)
        if mapping is not None and mapping.project is not None:
            resolution.project = mapping.project
            return
        project = self._projects.get(key)
        if project is None:
            resolution.problems.append(
                self._problem(
                    row,
                    "project",
                    f"Progetto '{row.project}' non trovato fra i codici censiti: "
                    "associarlo in Riconciliazione.",
                )
            )
            resolution.candidates["project"] = self._project_candidates()
            return
        resolution.project = project

    def _project_candidates(self) -> list[Candidate]:
        return [
            Candidate(id=str(p.pk), label=p.code, detail=p.title)
            for p in sorted(self._projects.values(), key=lambda p: p.code)
        ]

    # ---------------------------------------------------------------- wallet

    def _resolve_wallet(self, row: SourceRow, resolution: Resolution) -> None:
        year = row.period.year
        key = normalize_key(row.subproject)
        mapping = self._mapping_for(MappingKind.WALLET_ALLOCATION, key, year=year)
        if mapping is not None and mapping.wallet_allocation is not None:
            resolution.wallet_allocation = mapping.wallet_allocation
            return

        matches = self._allocations.get(year, {}).get(key, [])
        if len(matches) == 1:
            resolution.wallet_allocation = matches[0]
            return
        if not matches:
            message = (
                f"Sottoprogetto wallet '{row.subproject}' non trovato fra le allocazioni "
                f"aperte del wallet {year}: associarlo in Riconciliazione."
            )
        else:
            titoli = ", ".join(sorted(str(m) for m in matches))
            message = (
                f"Sottoprogetto wallet '{row.subproject}' corrisponde a più allocazioni "
                f"del wallet {year} ({titoli}): scegliere quella corretta."
            )
        resolution.problems.append(self._problem(row, "subproject", message))
        resolution.candidates["wallet_allocation"] = self._allocation_candidates(year, matches)

    def _allocation_candidates(self, year: int, matches: list[WalletAllocation]) -> list[Candidate]:
        pool = matches or [
            allocation
            for bucket in self._allocations.get(year, {}).values()
            for allocation in bucket
        ]
        unique = {allocation.pk: allocation for allocation in pool}
        return [
            Candidate(
                id=str(allocation.pk),
                label=allocation.activity.title,
                detail=(
                    f"Wallet {allocation.wallet_year.year} · "
                    f"{allocation.allocated_days} gg allocate"
                ),
            )
            for allocation in sorted(unique.values(), key=lambda a: a.activity.title)
        ]

    # ------------------------------------------------------ organico allargato

    def _resolve_canone(self, row: SourceRow, resolution: Resolution) -> None:
        semester = self._semester_for(row.period)
        key = normalize_key(row.subproject)
        mapping = self._mapping_for(MappingKind.CANONE_SUBACTIVITY, key, semester=semester)
        if mapping is not None and mapping.canone_subactivity is not None:
            resolution.canone_subactivity = mapping.canone_subactivity
            return

        matches = self._subactivities.get(semester, {}).get(key, [])
        if len(matches) == 1:
            resolution.canone_subactivity = matches[0]
            return
        if not matches:
            message = (
                f"Attività '{row.subproject}' non trovata nel canone {semester}: "
                "associarla in Riconciliazione."
            )
        else:
            message = (
                f"Attività '{row.subproject}' presente più volte nel canone {semester}: "
                "scegliere quella corretta."
            )
        resolution.problems.append(self._problem(row, "subproject", message))
        resolution.candidates["canone_subactivity"] = self._subactivity_candidates(
            semester, matches
        )

    def _semester_for(self, period: dt.date) -> str:
        """Semestre del canone che copre la data, per intervallo se dichiarato.

        `Canone.start_date` e `end_date` sono opzionali: quando mancano si ricade
        sull'etichetta calcolata dal mese, che è la convenzione del campo `semester`.
        """
        covering = Canone.objects.filter(start_date__lte=period, end_date__gte=period).values_list(
            "semester", flat=True
        )
        for semester in covering:
            if semester in self._subactivities:
                return semester
        return semester_of(period)

    def _subactivity_candidates(
        self, semester: str, matches: list[CanoneSubactivity]
    ) -> list[Candidate]:
        pool = matches or [
            subactivity
            for bucket in self._subactivities.get(semester, {}).values()
            for subactivity in bucket
        ]
        unique = {subactivity.pk: subactivity for subactivity in pool}
        return [
            Candidate(
                id=str(subactivity.pk),
                label=subactivity.title,
                detail=f"{subactivity.canone.semester} · {subactivity.reserved_days} gg riservate",
            )
            for subactivity in sorted(unique.values(), key=lambda s: s.title)
        ]

    # --------------------------------------------------------- collaboratori

    def _resolve_author(self, row: SourceRow, resolution: Resolution) -> None:
        raw = row.collaborator.strip()
        if not raw:
            resolution.problems.append(
                self._problem(row, "collaborator", "Collaboratore mancante.")
            )
            return

        key = comparison_key(raw)
        mapping = self._mapping_for(MappingKind.COLLABORATORE, normalize_key(raw))
        if mapping is not None and mapping.user is not None:
            resolution.author = mapping.user
            return

        matches = self._users.get(key, [])
        if len(matches) == 1:
            resolution.author = matches[0]
            return
        if len(matches) > 1:
            usernames = ", ".join(sorted(u.username for u in matches))
            resolution.problems.append(
                self._problem(
                    row,
                    "collaborator",
                    f"Collaboratore '{raw}' corrisponde a più utenti ({usernames}): "
                    "scegliere quello corretto.",
                )
            )
            resolution.candidates["author"] = [
                Candidate(
                    id=str(u.pk),
                    label=u.get_full_name() or u.username,
                    detail=u.username,
                )
                for u in sorted(matches, key=lambda u: u.username)
            ]
            return

        if not self.create_missing_collaborators:
            resolution.problems.append(
                self._problem(
                    row,
                    "collaborator",
                    f"Collaboratore '{raw}' non censito.",
                )
            )
            resolution.candidates["author"] = []
            return

        user = self._create_collaborator(raw)
        resolution.author = user
        resolution.created_collaborator = user
        resolution.problems.append(
            self._problem(
                row,
                "collaborator",
                f"Collaboratore '{raw}' censito come '{user.get_full_name()}' con ruolo "
                "fornitore: completare l'anagrafica.",
                level=Level.WARNING,
            )
        )

    def _create_collaborator(self, raw: str) -> User:
        """Censisce il consulente Imola mancante: attivo come autore, inerte come accesso.

        `is_active=True` è necessario perché `assignable_authors()` filtra sugli attivi e
        un utente disattivato non potrebbe ricevere consuntivi. L'accesso resta impossibile
        perché la password è inutilizzabile e l'unico backend configurato è a password.
        """
        full_name = titlecase_name(_invert_surname_first(raw))
        first, _, last = full_name.partition(" ")
        user = User(
            username=_available_username(full_name),
            first_name=first[:150],
            last_name=last[:150],
            is_active=True,
        )
        user.set_unusable_password()
        user.save()
        group, _ = Group.objects.get_or_create(name=roles.SUPPLIER)
        user.groups.add(group)

        organization, _ = Organization.objects.get_or_create(
            code=SUPPLIER_ORG_CODE,
            defaults={"name": "Imola Informatica", "kind": OrganizationKind.SUPPLIER},
        )
        if not Person.objects.by_name(full_name, organization).exists():
            Person.objects.create(
                full_name=full_name,
                organization=organization,
                needs_review=True,
                review_note=(
                    "Censita dall'importazione dell'estratto operativo: completare "
                    "email e referenze."
                ),
            )

        self._users.setdefault(comparison_key(full_name), []).append(user)
        self.created_users.append(user)
        return user

    # ----------------------------------------------------------------- utilità

    @staticmethod
    def _problem(
        row: SourceRow,
        field_name: str,
        message: str,
        *,
        level: Level = Level.ERROR,
    ) -> Problem:
        return Problem(
            level,
            message,
            sheet=row.sheet,
            cell=row.cell_of(field_name),
            excel_row=row.excel_row,
        )


def _invert_surname_first(raw: str) -> str:
    """`Nicoletti Pietro` → `Pietro Nicoletti`, come vuole la convenzione dell'anagrafica.

    Solo per due token: con tre o più l'ordine non è deducibile senza rischiare di
    stravolgere nomi composti, quindi si conserva l'originale e lo si lascia da rifinire.
    """
    tokens = raw.split()
    if len(tokens) == 2:
        return f"{tokens[1]} {tokens[0]}"
    return raw


def _available_username(full_name: str) -> str:
    base = normalize_key(full_name).replace(" ", ".")[:140] or "collaboratore"
    tokens = [t for t in full_name.lower().split() if t]
    if len(tokens) >= 2:
        base = f"{tokens[0]}.{tokens[-1]}"[:140]
    candidate = base
    suffix = 2
    while User.objects.filter(username=candidate).exists():
        candidate = f"{base}{suffix}"[:150]
        suffix += 1
    return candidate


@dataclass(frozen=True)
class Overlap:
    """Un movimento già a sistema che coincide con una riga in ingresso."""

    entry_id: str
    period: dt.date
    days: str
    author: str
    same_author: bool

    def describe(self, incoming_author: str) -> str:
        base = f"già presente: {self.period:%d/%m/%Y}, {self.days} gg, {self.author}"
        if self.same_author:
            return f"Riga {base}."
        return (
            f"Riga {base}, mentre l'Excel la intesta a {incoming_author}: "
            "una delle due fonti ha l'autore sbagliato."
        )


def find_overlaps(resolutions: list[Resolution]) -> dict[tuple[str, int], list[Overlap]]:
    """Righe in ingresso che coincidono con movimenti già registrati (§9.4).

    Il confronto è su destinazione, data, giornate e descrizione normalizzata. Non scarta
    nulla: due giornate identiche sulla stessa attività possono essere legittime, e la
    deduplicazione silenziosa è vietata dal §9.3. Serve a mostrare la sovrapposizione
    prima di applicare, perché è l'ultimo momento in cui tornare indietro è gratis.
    """
    from timesheets.models import TimesheetEntry

    with_target = [r for r in resolutions if r.target is not None]
    if not with_target:
        return {}

    periods = {r.row.period for r in with_target}
    targets: dict[str, set] = {"project": set(), "wallet_allocation": set(), "canone": set()}
    for resolution in with_target:
        if resolution.project is not None:
            targets["project"].add(resolution.project.pk)
        elif resolution.wallet_allocation is not None:
            targets["wallet_allocation"].add(resolution.wallet_allocation.pk)
        elif resolution.canone_subactivity is not None:
            targets["canone"].add(resolution.canone_subactivity.pk)

    target_query = Q(pk__in=[])
    if targets["project"]:
        target_query |= Q(project__in=targets["project"])
    if targets["wallet_allocation"]:
        target_query |= Q(wallet_allocation__in=targets["wallet_allocation"])
    if targets["canone"]:
        target_query |= Q(canone_subactivity__in=targets["canone"])

    index: dict[tuple, list[TimesheetEntry]] = {}
    existing = (
        TimesheetEntry.objects.filter(target_query, period__in=periods)
        .exclude(reversals__isnull=False)
        .select_related("created_by")
    )
    for entry in existing:
        target_id = entry.project_id or entry.wallet_allocation_id or entry.canone_subactivity_id
        index.setdefault(
            (target_id, entry.period, entry.days, normalize_key(entry.note)), []
        ).append(entry)

    found: dict[tuple[str, int], list[Overlap]] = {}
    for resolution in with_target:
        row = resolution.row
        key = (resolution.target.pk, row.period, row.days, normalize_key(row.note))
        matches = index.get(key, [])
        if not matches:
            continue
        incoming = resolution.author
        found[(row.sheet, row.excel_row)] = [
            Overlap(
                entry_id=str(entry.pk),
                period=entry.period,
                days=str(entry.days),
                author=_display_name(entry.created_by),
                same_author=bool(incoming and entry.created_by_id == incoming.pk),
            )
            for entry in matches
        ]
    return found


def _display_name(user: User | None) -> str:
    if user is None:
        return "autore non registrato"
    return user.get_full_name() or user.username
