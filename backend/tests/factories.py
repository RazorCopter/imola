"""Factory per i test. I dati demo non replicano il seed reale (che non è versionato)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import factory
from django.contrib.auth.models import User

from anomalies.models import Anomaly, Scope, Severity, build_fingerprint
from canone.models import Canone, CanoneSubactivity, Office
from directory.models import Organization, OrganizationKind, Person
from imports.models import ImportBatch, ImportKind
from ppm.models import PpmSnapshot, PpmSnapshotRow, SnapshotKind
from projects.models import (
    BillingMilestone,
    BillingStatus,
    ContractType,
    MilestoneStatus,
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


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"utente{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@mediolanum.it")
    is_active = True


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization
        django_get_or_create = ("code",)

    code = "BMED"
    name = "Banca Mediolanum"
    kind = OrganizationKind.CLIENT


class SupplierOrganizationFactory(OrganizationFactory):
    code = "IMOLA"
    name = "Imola Informatica"
    kind = OrganizationKind.SUPPLIER


class PersonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Person
        django_get_or_create = ("full_name", "organization")

    full_name = factory.Sequence(lambda n: f"Persona Numero{n}")
    organization = factory.SubFactory(OrganizationFactory)


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"IM26{n:03d}-3313-BMED-ARCH-PROGETTO-DEMO")
    title = factory.Sequence(lambda n: f"Progetto demo {n}")
    contract_type = ContractType.AQL
    budget_days = Decimal("10.0000")
    start_date = date(2026, 1, 1)
    planned_end_date = date(2026, 6, 30)
    offer_status = OfferStatus.ACCETTATA
    timesheet_status = TimesheetStatus.ATTIVO
    billing_status = BillingStatus.DA_FATTURARE


class ClosedProjectFactory(ProjectFactory):
    timesheet_status = TimesheetStatus.CHIUSO
    actual_closure_date = date(2025, 11, 15)


class MilestoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BillingMilestone

    project = factory.SubFactory(ProjectFactory)
    planned_date = date(2026, 3, 1)
    status = MilestoneStatus.PIANIFICATA


class CanoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Canone

    project = factory.SubFactory(
        ProjectFactory,
        contract_type=ContractType.CANONE,
        budget_days=Decimal("173.0000"),
    )
    semester = "2026-S2"
    total_days = Decimal("173.0000")
    target_base_days = Decimal("2.0000")
    target_days_per_week = Decimal("6.6900")
    start_date = date(2026, 7, 1)
    end_date = date(2026, 12, 31)
    cap_at_total = True


class CanoneSubactivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CanoneSubactivity

    canone = factory.SubFactory(CanoneFactory)
    office = Office.SA
    title = factory.Sequence(lambda n: f"Sotto-attività {n}")


class WalletYearFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WalletYear
        django_get_or_create = ("year",)

    year = 2026


class WalletActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WalletActivity
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"ATT-DEMO-{n}")
    title = factory.Sequence(lambda n: f"Attività demo {n}")
    kind = ActivityKind.ATTIVITA


class WalletAllocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WalletAllocation

    wallet_year = factory.SubFactory(WalletYearFactory)
    source_project = factory.SubFactory(ProjectFactory)
    activity = factory.SubFactory(WalletActivityFactory)
    allocated_days = Decimal("1.0000")
    status = AllocationStatus.APERTA


class TimesheetEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TimesheetEntry

    period = date(2026, 10, 1)
    days = Decimal("1.0000")
    source = TimesheetSource.MANUALE


class PpmSnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PpmSnapshot

    kind = SnapshotKind.PPM_WALLET
    title = "Progetti Gruppo Progetto - Banca Mediolanum - Wallet 2026"
    extracted_at = factory.LazyFunction(
        lambda: __import__("django.utils.timezone", fromlist=["timezone"]).now()
    )
    source_filename = "wallet_2026.xlsx"


class PpmSnapshotRowFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PpmSnapshotRow

    snapshot = factory.SubFactory(PpmSnapshotFactory)
    project_code = factory.Sequence(lambda n: f"IM26{n:03d}-3313-ARCH-PROGETTO-DEMO")
    planned_days = Decimal("10.0000")
    residual_days = Decimal("0.0000")
    total_days = Decimal("10.0000")


class AnomalyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Anomaly

    rule_code = "CHK_DEMO"
    severity = Severity.MEDIA
    scope = Scope.PROGETTO
    description = "Anomalia di prova."
    fingerprint = factory.Sequence(lambda n: build_fingerprint("CHK_DEMO", n))


class ImportBatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ImportBatch

    kind = ImportKind.SEED_JSON
    source_filename = "seed_demo.json"
