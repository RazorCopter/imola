"""Carica un dataset sintetico e deterministico per test e verifiche locali."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from anomalies.models import Anomaly, AnomalyStatus, Scope, Severity, build_fingerprint
from anomalies.runner import run_checks
from canone.models import Canone, CanoneSubactivity, Office
from core import roles
from directory.models import Organization, OrganizationKind, Person
from imports.models import ImportBatch, ImportKind, ImportStatus
from ppm.models import PpmSnapshot, PpmSnapshotRow, SnapshotKind
from projects.models import (
    BillingStatus,
    ContractType,
    OfferStatus,
    Project,
    TimesheetStatus,
)
from timesheets.models import TimesheetEntry, TimesheetSource
from wallet.models import (
    ActivityKind,
    AllocationStatus,
    WalletActivity,
    WalletAllocation,
    WalletYear,
)

DEFAULT_PASSWORD = "Demo-Local-2026!"


class Command(BaseCommand):
    help = "Carica dati sintetici e utenti demo per verifiche funzionali locali ed E2E."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Password comune assegnata agli account demo.",
        )
        parser.add_argument(
            "--run-checks",
            action="store_true",
            help="Esegue il motore controlli al termine del caricamento.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        password: str = options["password"]
        should_run_checks: bool = options["run_checks"]

        self.stdout.write("Configurazione ruoli e utenti demo...")
        roles.ensure_groups()

        admin, _ = User.objects.update_or_create(
            username="demo_admin",
            defaults={
                "email": "admin@demo.local",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        manager, _ = User.objects.update_or_create(
            username="demo_responsabile",
            defaults={"email": "responsabile@demo.local", "is_staff": True},
        )
        referent, _ = User.objects.update_or_create(
            username="demo_referente",
            defaults={"email": "referente@demo.local"},
        )
        supplier, _ = User.objects.update_or_create(
            username="demo_fornitore",
            defaults={"email": "fornitore@demo.local"},
        )

        user_role_map = [
            (admin, roles.ADMIN),
            (manager, roles.MANAGER),
            (referent, roles.REFERENT),
            (supplier, roles.SUPPLIER),
        ]
        for user, role in user_role_map:
            user.set_password(password)
            user.is_active = True
            user.save()
            user.groups.set([Group.objects.get(name=role)])

        self.stdout.write("Configurazione organizzazioni e persone...")
        bmed, _ = Organization.objects.get_or_create(
            code="DEMO-BMED",
            defaults={
                "name": "Organizzazione Demo Cliente",
                "kind": OrganizationKind.CLIENT,
            },
        )
        supplier_org, _ = Organization.objects.get_or_create(
            code="DEMO-SUP",
            defaults={
                "name": "Fornitore Demo",
                "kind": OrganizationKind.SUPPLIER,
            },
        )
        owner, _ = Person.objects.get_or_create(
            full_name="Referente Demo",
            defaults={"email": "referente@demo.local", "organization": bmed},
        )
        supplier_owner, _ = Person.objects.get_or_create(
            full_name="Fornitore Demo",
            defaults={"email": "fornitore@demo.local", "organization": supplier_org},
        )

        self.stdout.write("Configurazione import batch demo...")
        seed_batch, _ = ImportBatch.objects.get_or_create(
            source_filename="demo_seed_synthetic.json",
            defaults={
                "kind": ImportKind.SEED_JSON,
                "status": ImportStatus.APPLIED,
                "applied_by": admin,
                "report": {"demo": True},
            },
        )

        self.stdout.write("Configurazione progetti demo...")
        project_specs = [
            (
                "DEMO-PRJ-001",
                "Portale dimostrativo",
                ContractType.AQL,
                TimesheetStatus.ATTIVO,
                None,
                Decimal("40.0000"),
                Decimal("18.5000"),
            ),
            (
                "DEMO-PRJ-002",
                "Migrazione applicativa demo",
                ContractType.AQL,
                TimesheetStatus.CHIUSO,
                date(2026, 6, 30),
                Decimal("25.0000"),
                Decimal("20.0000"),
            ),
            (
                "DEMO-PRJ-003",
                "Progetto da revisionare",
                ContractType.AQL,
                TimesheetStatus.DA_VERIFICARE,
                None,
                Decimal("18.0000"),
                Decimal("9.2500"),
            ),
            (
                "DEMO-PRJ-004",
                "Progetto chiuso da revisionare",
                ContractType.AQL,
                TimesheetStatus.DA_VERIFICARE,
                None,
                Decimal("12.0000"),
                Decimal("10.0000"),
            ),
            (
                "DEMO-PRJ-005",
                "Progetto chiuso senza data",
                ContractType.AQL,
                TimesheetStatus.CHIUSO,
                None,
                Decimal("15.0000"),
                Decimal("15.0000"),
            ),
            (
                "DEMO-CANONE-001",
                "Servizio canone semestrale demo",
                ContractType.CANONE,
                TimesheetStatus.ATTIVO,
                None,
                Decimal("100.0000"),
                Decimal("0.0000"),
            ),
        ]

        projects: dict[str, Project] = {}
        for code, title, contract_type, status, closure, budget, consumed in project_specs:
            defaults = {
                "title": title,
                "contract_type": contract_type,
                "budget_days": budget,
                "start_date": date(2026, 1, 1),
                "planned_end_date": date(2026, 12, 31),
                "offer_status": OfferStatus.ACCETTATA,
                "timesheet_status": status,
                "billing_status": BillingStatus.DA_FATTURARE,
                "actual_closure_date": closure,
                "client_owner": owner,
                "supplier_owner": supplier_owner,
                "notes": "Dato esclusivamente dimostrativo.",
            }
            if status == TimesheetStatus.CHIUSO and closure is None:
                defaults["import_batch"] = seed_batch

            p, _ = Project.objects.update_or_create(
                code=code,
                defaults=defaults,
            )
            projects[code] = p

            if (
                consumed > Decimal("0")
                and not TimesheetEntry.objects.filter(
                    project=p, source=TimesheetSource.MANUALE
                ).exists()
            ):
                TimesheetEntry.objects.create(
                    project=p,
                    period=date(2026, 10, 1),
                    days=consumed,
                    source=TimesheetSource.MANUALE,
                    note=f"Consuntivo demo {code}",
                )

        self.stdout.write("Configurazione canone e sottoattività...")
        canone_prj = projects["DEMO-CANONE-001"]
        canone, _ = Canone.objects.update_or_create(
            project=canone_prj,
            semester="2026-S2",
            defaults={
                "total_days": Decimal("100.0000"),
                "target_base_days": Decimal("2.0000"),
                "target_days_per_week": Decimal("5.0000"),
                "cap_at_total": True,
                "start_date": date(2026, 7, 1),
                "end_date": date(2026, 12, 31),
            },
        )
        subactivity_ea, _ = CanoneSubactivity.objects.update_or_create(
            canone=canone,
            title="Supporto Architetturale EA",
            defaults={
                "office": Office.EA,
                "quarter_estimate_days": Decimal("20.0000"),
                "notes": "Sotto-attività demo EA",
            },
        )
        _subactivity_sa, _ = CanoneSubactivity.objects.update_or_create(
            canone=canone,
            title="#300228 Sviluppo Componenti SA",
            defaults={
                "office": Office.SA,
                "redmine_ref": "300228",
                "quarter_estimate_days": Decimal("30.0000"),
                "notes": "Sotto-attività demo SA",
            },
        )
        if not TimesheetEntry.objects.filter(
            canone_subactivity=subactivity_ea, source=TimesheetSource.MANUALE
        ).exists():
            TimesheetEntry.objects.create(
                canone_subactivity=subactivity_ea,
                period=date(2026, 10, 1),
                days=Decimal("8.0000"),
                source=TimesheetSource.MANUALE,
                note="Consuntivo canone EA demo",
            )

        self.stdout.write("Configurazione wallet e allocazioni...")
        active_years = {2026, timezone.localdate().year}
        wallet_years = [WalletYear.objects.get_or_create(year=yr)[0] for yr in active_years]
        activity, _ = WalletActivity.objects.get_or_create(
            code="DEMO-ACT-001",
            defaults={
                "title": "Attività wallet demo",
                "kind": ActivityKind.ATTIVITA,
            },
        )
        for w_year in wallet_years:
            alloc_ref_1 = f"DEMO-ALLOC-{w_year.year}-001"
            alloc_1, _ = WalletAllocation.objects.update_or_create(
                external_ref=alloc_ref_1,
                defaults={
                    "wallet_year": w_year,
                    "source_project": projects["DEMO-PRJ-001"],
                    "activity": activity,
                    "allocated_days": Decimal("5.0000"),
                    "status": AllocationStatus.APERTA,
                },
            )
            alloc_ref_2 = f"DEMO-ALLOC-{w_year.year}-002"
            WalletAllocation.objects.update_or_create(
                external_ref=alloc_ref_2,
                defaults={
                    "wallet_year": w_year,
                    "source_project": projects["DEMO-PRJ-001"],
                    "activity": activity,
                    "allocated_days": Decimal("8.0000"),
                    "status": AllocationStatus.APERTA,
                },
            )
            if not TimesheetEntry.objects.filter(
                wallet_allocation=alloc_1, source=TimesheetSource.MANUALE
            ).exists():
                TimesheetEntry.objects.create(
                    wallet_allocation=alloc_1,
                    period=(
                        date(w_year.year, 10, 1) if w_year.year == 2026 else date(w_year.year, 1, 1)
                    ),
                    days=Decimal("2.0000"),
                    source=TimesheetSource.MANUALE,
                    note=f"Consuntivo wallet demo {w_year.year}",
                )

        self.stdout.write("Configurazione snapshot PPM per riconciliazione...")
        snapshot, _ = PpmSnapshot.objects.update_or_create(
            title="Snapshot PPM Demo 2026-10",
            defaults={
                "kind": SnapshotKind.PPM_PROGETTI,
                "source_filename": "demo_ppm_export_2026-10.xlsx",
                "extracted_at": timezone.now(),
                "imported_by": admin,
            },
        )
        PpmSnapshotRow.objects.update_or_create(
            snapshot=snapshot,
            project_code="DEMO-PRJ-001",
            defaults={
                "project": projects["DEMO-PRJ-001"],
                "ppm_status": "ATTIVO",
                "planned_days": Decimal("40.0000"),
                "residual_days": Decimal("21.5000"),
                "total_days": Decimal("18.5000"),
                "supplier_owner_name": "Fornitore Demo",
            },
        )
        PpmSnapshotRow.objects.update_or_create(
            snapshot=snapshot,
            project_code="DEMO-PRJ-003",
            defaults={
                "project": projects["DEMO-PRJ-003"],
                "ppm_status": "ATTIVO",
                "planned_days": Decimal("18.0000"),
                "residual_days": Decimal("3.0000"),
                "total_days": Decimal("15.0000"),
                "supplier_owner_name": "Fornitore Demo",
            },
        )

        self.stdout.write("Configurazione anomalie dimostrative...")
        demo_anomalies = [
            (
                "DEMO_END_PASSED",
                projects["DEMO-PRJ-001"],
                Severity.BASSA,
                "Data fine prevista da aggiornare (demo).",
                "Verificare la data di fine prevista del progetto.",
            ),
            (
                "DEMO_UNVERIFIED",
                projects["DEMO-PRJ-003"],
                Severity.MEDIA,
                "Dati di consuntivazione da verificare (demo).",
                "Completare la revisione del progetto.",
            ),
            (
                "DEMO_CLOSED_NO_DATE",
                projects["DEMO-PRJ-005"],
                Severity.ALTA,
                "Progetto chiuso senza data di chiusura (demo).",
                "Inserire la data effettiva di chiusura.",
            ),
        ]
        for rule_code, prj, severity, desc, suggested in demo_anomalies:
            fingerprint = build_fingerprint(rule_code, prj.code)
            Anomaly.objects.update_or_create(
                fingerprint=fingerprint,
                defaults={
                    "entity_ref": prj.code,
                    "rule_code": rule_code,
                    "severity": severity,
                    "scope": Scope.PROGETTO,
                    "description": desc,
                    "suggested_action": suggested,
                    "status": AnomalyStatus.APERTA,
                    "project": prj,
                    "context": {"project_code": prj.code, "demo": True},
                },
            )

        if should_run_checks:
            self.stdout.write("Esecuzione motore controlli...")
            report = run_checks()
            self.stdout.write(
                f"Controlli completati: {report.detected} rilevate, "
                f"{report.created} create, {report.updated} aggiornate."
            )

        self.stdout.write(self.style.SUCCESS("Dati demo caricati con successo."))
        self.stdout.write(
            "Utenti: demo_admin, demo_responsabile, demo_referente, "
            f"demo_fornitore (pwd: {password})"
        )
        demo_projects = Project.objects.filter(code__startswith="DEMO-").count()
        demo_allocations = WalletAllocation.objects.filter(external_ref__startswith="DEMO-").count()
        open_anomalies = Anomaly.objects.filter(status=AnomalyStatus.APERTA).count()
        self.stdout.write(
            f"Progetti: {demo_projects} | Allocazioni: {demo_allocations} | "
            f"Anomalie aperte: {open_anomalies}"
        )
