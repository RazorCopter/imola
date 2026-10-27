"""Mappatura idempotente del seed JSON sui modelli applicativi.

Questo modulo cresce per incrementi coesi. Importa fondamenta, progetti, canoni, wallet,
snapshot PPM e anomalie seed, incluse le rispettive entità dipendenti e i consuntivi
iniziali. Il payload è già stato validato da :mod:`importers.schema` e contiene ``Decimal``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from anomalies.models import (
    SEED_RULE_CODE,
    Anomaly,
    AnomalyStatus,
    build_fingerprint,
)
from canone.models import Canone, CanoneSubactivity, extract_redmine_ref
from core.models import AppSettings, verification_point
from directory.models import Organization, OrganizationKind, Person
from directory.normalization import comparison_key, normalize_person_name
from domain.money import ZERO
from importers.report import EntityReport, ImportReport
from imports.models import ImportBatch
from ppm.models import PpmSnapshot, PpmSnapshotRow, normalize_project_code
from projects.models import BillingMilestone, Project
from timesheets.models import TimesheetEntry, TimesheetSource, month_start
from wallet.models import (
    ActivityKind,
    AllocationStatus,
    WalletActivity,
    WalletAllocation,
    WalletFundingTranche,
    WalletSourceLot,
    WalletYear,
)

HISTORICAL_WALLET_YEAR = 2025
HISTORICAL_DUPLICATES = {
    "IM25151-3313-BMED-ARCH-ICT-ASSET-LIFECYCLE-OBSOLESCENZA": "W26-012",
    "IM25236-3313-BMED-ARCH-RAFFORZAMENTO-DATA-QUALITY-TECNICA": "W26-005",
}

# Mappa dichiarativa D-05: id_import seed -> (rule_code, entita_attesa).
# AN-004, AN-005, AN-006, AN-008: 1-to-1 coperte da controlli automatici di Fase 4.
# AN-003, AN-007: 1-to-many con elenco esplicito di entità da coprire interamente.
# AN-001, AN-002, AN-009, AN-010, AN-011: difetti del file Excel superati all'import (risolte).
SEED_EXCEL_DEFECT_RESOLUTION_NOTE = "superata dalla migrazione (difetto del file Excel di origine)"
SEED_EXCEL_DEFECT_ANOMALIES: frozenset[str] = frozenset(
    {"AN-001", "AN-002", "AN-009", "AN-010", "AN-011"}
)

SEED_SUPERSESSION_MAP: dict[str, tuple[str, str | tuple[str, ...] | None] | None] = {
    "AN-001": None,
    "AN-002": None,
    "AN-003": (
        "CHK_UNVERIFIED_DATA",
        (
            "IM25188",
            "IM25151",
            "IM25255",
            "IM25270",
            "IM25206",
            "IM25075",
            "IM25026",
            "IM24517",
            "IM25236",
        ),
    ),
    "AN-004": ("CHK_OVERRUN_PROJECT", "IM26292"),
    "AN-005": ("CHK_DOUBLE_COUNT", ("RM-300228", "RM-300229")),
    "AN-006": ("CHK_MISSING_IN_PPM", "IM25379"),
    "AN-007": (
        "CHK_RECON_DELTA",
        (
            "IM24133",
            "IM25244",
            "IM25306",
            "IM26022",
            "IM25198",
            "IM25197",
            "IM25216",
        ),
    ),
    "AN-008": ("CHK_CANONE_UNDERUSE", "IM26179"),
    "AN-009": None,
    "AN-010": None,
    "AN-011": None,
}


def _record_created(entity: EntityReport, key: str) -> None:
    entity.created += 1
    entity.created_keys.append(key)


def _json_value(value: Any) -> Any:
    """Converte ricorsivamente i Decimal per JSONField senza passare da float."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _report_value(value: Any) -> Any:
    """Rende serializzabili nel report anche i riferimenti a modelli Django."""
    if hasattr(value, "_meta") and hasattr(value, "pk"):
        return str(value.pk)
    return _json_value(value)


def _apply_changes(
    instance: Any,
    values: dict[str, Any],
    *,
    entity: EntityReport,
    key: str,
) -> None:
    changes = {
        field: {
            "prima": _report_value(getattr(instance, field)),
            "dopo": _report_value(value),
        }
        for field, value in values.items()
        if getattr(instance, field) != value
    }
    if not changes:
        entity.unchanged += 1
        return

    for field, value in values.items():
        setattr(instance, field, value)
    instance.full_clean()
    instance.save(update_fields=[*values, "updated_at", "updated_by", "version"])
    entity.updated += 1
    entity.updated_rows.append({"chiave": key, "modifiche": changes})


@transaction.atomic
def import_foundation(
    payload: dict[str, Any],
    *,
    batch: ImportBatch,
    report: ImportReport,
) -> None:
    """Importa tutte le entità del seed in modo atomico e idempotente.

    Le chiavi naturali sono quelle fissate nel checkpoint di Fase 2. Solo i record creati
    ricevono il batch corrente, così un rollback futuro non può rivendicare record
    preesistenti.
    """

    configuration = payload["configurazione"]
    _import_configuration(configuration, report.entity("configurazione"))
    organizations = _import_organizations(configuration, batch, report.entity("organizzazioni"))
    _import_people(payload["persone"], organizations, batch, report.entity("persone"))
    _import_projects(payload, organizations, batch, report)
    _import_canoni(payload, batch, report)
    _import_wallet(payload, organizations, batch, report)
    if payload.get("snapshot_ppm"):
        _import_ppm_snapshots(payload["snapshot_ppm"], batch, report)
    if payload.get("anomalie_aperte"):
        _import_seed_anomalies(payload["anomalie_aperte"], batch, report)


def _import_configuration(configuration: dict[str, Any], entity: EntityReport) -> None:
    settings = AppSettings.objects.filter(singleton=True).first()
    values = {
        "hours_per_day": configuration["ore_per_giornata"],
        "ppm_granularity_days": configuration.get("granularita_ppm_gg", 0),
        "reconciliation_tolerance_days": configuration["tolleranza_riconciliazione_gg"],
        "residual_years_after_closure": configuration["regola_scadenza_residui"][
            "anni_validita_dopo_chiusura"
        ],
    }
    if "costo_giornata_uomo" in configuration:
        values["daily_person_cost"] = configuration["costo_giornata_uomo"]
    if settings is None:
        settings = AppSettings(**values)
        settings.full_clean()
        settings.save()
        _record_created(entity, "singleton")
        return
    _apply_changes(settings, values, entity=entity, key="singleton")


def _import_organizations(
    configuration: dict[str, Any],
    batch: ImportBatch,
    entity: EntityReport,
) -> dict[str, Organization]:
    definitions = (
        (configuration["cliente"], OrganizationKind.CLIENT),
        (configuration["fornitore"], OrganizationKind.SUPPLIER),
    )
    organizations: dict[str, Organization] = {}
    for source, kind in definitions:
        code = source["codice"]
        values = {"name": source["ragione_sociale"], "kind": kind}
        organization = Organization.objects.filter(code=code).first()
        if organization is None:
            organization = Organization.objects.create(code=code, import_batch=batch, **values)
            _record_created(entity, code)
        else:
            _apply_changes(organization, values, entity=entity, key=code)
        organizations[code] = organization
    return organizations


def _import_people(
    rows: list[dict[str, Any]],
    organizations: dict[str, Organization],
    batch: ImportBatch,
    entity: EntityReport,
) -> None:
    for row in rows:
        organization = organizations[row["organizzazione"]]
        candidate = normalize_person_name(row["nome"])
        key = comparison_key(candidate.normalized)
        report_key = f"{organization.code}:{key}"
        values = {
            "full_name": candidate.normalized,
            "email": row.get("email"),
            "is_active": True,
            "needs_review": candidate.needs_review,
            "review_note": candidate.reason,
        }
        person = Person.objects.filter(name_key=key, organization=organization).first()
        if person is None:
            Person.objects.create(
                name_key=key,
                organization=organization,
                import_batch=batch,
                **values,
            )
            _record_created(entity, report_key)
        else:
            _apply_changes(person, values, entity=entity, key=report_key)


def _as_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _find_person(raw_name: str | None, organization: Organization) -> Person | None:
    if not raw_name:
        return None
    return Person.objects.filter(
        organization=organization,
        name_key=comparison_key(raw_name),
    ).first()


def _project_values(row: dict[str, Any], organizations: dict[str, Organization]) -> dict[str, Any]:
    return {
        "title": row["titolo"],
        "contract_type": row["tipo_contratto"],
        "aro_code": row.get("codice_aro") or "",
        "rda_code": row.get("codice_rda") or "",
        "deliverable": row.get("deliverable") or "",
        "client_owner": _find_person(row.get("referente_bmed"), organizations["BMED"]),
        "supplier_owner": _find_person(row.get("referente_imola"), organizations["IMOLA"]),
        "budget_days": row["gg_budget"],
        "start_date": _as_date(row.get("data_inizio")),
        "planned_end_date": _as_date(row.get("data_fine_prevista")),
        "actual_closure_date": _as_date(row.get("data_chiusura_consuntivazione")),
        "offer_status": row["stato_offerta"],
        "timesheet_status": row["stato_consuntivazione"],
        "billing_status": row["stato_fatturazione"],
        "released_to_wallet_days": row.get("gg_rilasciati_wallet", ZERO),
        "declared_residual_year": row.get("anno_riferimento_residuo"),
        "notes": row.get("note") or "",
        "legacy_excel_status": row.get("stato_excel_originale") or "",
        "reliability": row["affidabilita"],
        "verification_points": [
            verification_point(text) for text in row.get("punti_da_verificare", [])
        ],
    }


def _import_projects(
    payload: dict[str, Any],
    organizations: dict[str, Organization],
    batch: ImportBatch,
    report: ImportReport,
) -> None:
    rows = payload.get("progetti", [])
    if not rows:
        return

    projects_entity = report.entity("progetti")
    milestones_entity = report.entity("milestone")
    timesheets_entity = report.entity("consuntivi_progetto")
    reference_date = _as_date(payload.get("meta", {}).get("data_riferimento_dati"))

    for row in rows:
        code = row["codice"]
        values = _project_values(row, organizations)
        project = Project.objects.filter(code=code).first()
        if project is None:
            project = Project.objects.create(code=code, import_batch=batch, **values)
            _record_created(projects_entity, code)
        else:
            _apply_changes(project, values, entity=projects_entity, key=code)

        _import_milestones(
            project,
            row.get("milestone_fatturazione", []),
            batch,
            milestones_entity,
        )
        _import_project_timesheet(
            project,
            row["gg_consumati_su_progetto"],
            reference_date,
            batch,
            timesheets_entity,
            report,
        )


def _import_milestones(
    project: Project,
    rows: list[dict[str, Any]],
    batch: ImportBatch,
    entity: EntityReport,
) -> None:
    seen_dates: set[date | None] = set()
    for row in rows:
        planned_date = _as_date(row["data_prevista"])
        date_key = planned_date.isoformat() if planned_date else "senza-data"
        key = f"{project.code}:{date_key}"
        if planned_date in seen_dates:
            entity.skipped.append(
                {"chiave": key, "motivo": "Data milestone duplicata nello stesso progetto"}
            )
            continue
        seen_dates.add(planned_date)

        milestone = BillingMilestone.objects.filter(
            project=project, planned_date=planned_date
        ).first()
        values = {"status": row["stato"]}
        if milestone is None:
            BillingMilestone.objects.create(
                project=project,
                planned_date=planned_date,
                import_batch=batch,
                **values,
            )
            _record_created(entity, key)
        else:
            _apply_changes(milestone, values, entity=entity, key=key)


def _import_project_timesheet(
    project: Project,
    days: Decimal,
    reference_date: date | None,
    batch: ImportBatch,
    entity: EntityReport,
    report: ImportReport,
) -> None:
    key = project.code
    if not days:
        entity.skipped.append({"chiave": key, "motivo": "Consuntivo a zero: nessuna riga"})
        return
    if reference_date is None:
        entity.errors.append({"chiave": key, "motivo": "Data di riferimento seed assente"})
        return

    period = month_start(reference_date)
    existing = TimesheetEntry.objects.filter(
        project=project,
        period=period,
        source=TimesheetSource.SEED_INIZIALE,
    ).first()
    if existing is None:
        TimesheetEntry.objects.create(
            project=project,
            period=period,
            days=days,
            source=TimesheetSource.SEED_INIZIALE,
            note="Consuntivo diretto iniziale dal seed",
            import_batch=batch,
        )
        _record_created(entity, key)
        return

    entity.unchanged += 1
    if existing.days != days:
        report.warnings.append(
            f"{key}: consuntivo seed {existing.days} gg già presente; differenza a {days} gg "
            "non applicata, usare un import PPM"
        )


def _canone_values(row: dict[str, Any]) -> dict[str, Any]:
    formula = row.get("formula_target") or {}
    start_date, end_date = Canone.semester_bounds(row["semestre"])
    return {
        "total_days": row["monte_gg"],
        "target_base_days": formula.get("base_gg", Decimal("2")),
        "target_days_per_week": formula.get("gg_per_settimana", Decimal("0")),
        "weeks_elapsed_at_import": formula.get("settimane_trascorse"),
        "cap_at_total": formula.get("cap_al_monte", True),
        "start_date": _as_date(start_date),
        "end_date": _as_date(end_date),
        "extracted_at": _as_date(row.get("data_estrazione")),
    }


def _import_canoni(
    payload: dict[str, Any],
    batch: ImportBatch,
    report: ImportReport,
) -> None:
    rows = payload.get("canoni", [])
    if not rows:
        return

    canoni_entity = report.entity("canoni")
    subactivities_entity = report.entity("sottoattivita_canone")
    timesheets_entity = report.entity("consuntivi_canone")
    reference_date = _as_date(payload.get("meta", {}).get("data_riferimento_dati"))
    seen_canoni: set[tuple[str, str]] = set()

    for row in rows:
        project_code = row["codice_progetto"]
        semester = row["semestre"]
        key_tuple = (project_code, semester)
        key = f"{project_code}:{semester}"
        if key_tuple in seen_canoni:
            canoni_entity.skipped.append({"chiave": key, "motivo": "Canone duplicato nel payload"})
            continue
        seen_canoni.add(key_tuple)

        project = Project.objects.filter(code=project_code).first()
        if project is None:
            canoni_entity.skipped.append(
                {"chiave": key, "motivo": "Progetto di riferimento non trovato"}
            )
            continue

        values = _canone_values(row)
        canone = Canone.objects.filter(project=project, semester=semester).first()
        if canone is None:
            canone = Canone.objects.create(
                project=project,
                semester=semester,
                import_batch=batch,
                **values,
            )
            _record_created(canoni_entity, key)
        else:
            _apply_changes(canone, values, entity=canoni_entity, key=key)

        _import_canone_subactivities(
            canone,
            row.get("sottoattivita", []),
            values["extracted_at"] or reference_date,
            batch,
            subactivities_entity,
            timesheets_entity,
            report,
        )


def _import_canone_subactivities(
    canone: Canone,
    rows: list[dict[str, Any]],
    reference_date: date | None,
    batch: ImportBatch,
    entity: EntityReport,
    timesheets_entity: EntityReport,
    report: ImportReport,
) -> None:
    seen_titles: set[str] = set()
    for row in rows:
        title = row["titolo"]
        key = f"{canone.project.code}:{canone.semester}:{title}"
        if title in seen_titles:
            entity.skipped.append(
                {"chiave": key, "motivo": "Titolo sotto-attività duplicato nel canone"}
            )
            continue
        seen_titles.add(title)

        values = {
            "office": row.get("ufficio") or "",
            "redmine_ref": extract_redmine_ref(title),
            "quarter_estimate_days": row.get("stima_trimestre"),
            "forecast_remaining_days": row.get("forecast_residuo_31_12"),
            "notes": row.get("note") or "",
            "needs_review": False,
        }
        subactivity = CanoneSubactivity.objects.filter(canone=canone, title=title).first()
        if subactivity is None:
            subactivity = CanoneSubactivity.objects.create(
                canone=canone,
                title=title,
                import_batch=batch,
                **values,
            )
            _record_created(entity, key)
        else:
            _apply_changes(subactivity, values, entity=entity, key=key)

        _import_canone_timesheet(
            subactivity,
            row["gg_consuntivati"],
            reference_date,
            batch,
            timesheets_entity,
            report,
        )


def _import_canone_timesheet(
    subactivity: CanoneSubactivity,
    days: Decimal,
    reference_date: date | None,
    batch: ImportBatch,
    entity: EntityReport,
    report: ImportReport,
) -> None:
    key_prefix = (
        f"{subactivity.canone.project.code}:{subactivity.canone.semester}:{subactivity.title}"
    )
    if days == 0:
        entity.skipped.append({"chiave": key_prefix, "motivo": "Consuntivo a zero omesso"})
        return
    if reference_date is None:
        entity.errors.append(
            {"chiave": key_prefix, "motivo": "Data di riferimento del consuntivo assente"}
        )
        return

    period = month_start(reference_date)
    key = f"{key_prefix}:{period.isoformat()}"
    existing = TimesheetEntry.objects.filter(
        canone_subactivity=subactivity,
        period=period,
        source=TimesheetSource.SEED_INIZIALE,
    ).first()
    if existing is not None:
        entity.unchanged += 1
        if existing.days != days:
            report.warnings.append(
                f"{key}: consuntivo seed esistente {existing.days} gg, nuovo valore {days} gg; "
                "differenza non applicata, usare un import PPM"
            )
        return

    TimesheetEntry.objects.create(
        canone_subactivity=subactivity,
        period=period,
        days=days,
        source=TimesheetSource.SEED_INIZIALE,
        note="Consuntivo iniziale sotto-attività canone dal seed JSON",
        import_batch=batch,
    )
    _record_created(entity, key)


def _wallet_year(year: int, batch: ImportBatch, entity: EntityReport) -> WalletYear:
    wallet_year = WalletYear.objects.filter(year=year).first()
    key = str(year)
    if wallet_year is None:
        wallet_year = WalletYear.objects.create(year=year, notes="", import_batch=batch)
        _record_created(entity, key)
    else:
        entity.unchanged += 1
    return wallet_year


def _wallet_person(
    raw_name: str | None,
    organization: Organization,
    *,
    entity: EntityReport,
    key: str,
    role: str,
) -> tuple[Person | None, bool]:
    if not raw_name:
        return None, True
    normalized = normalize_person_name(raw_name).normalized
    matches = list(
        Person.objects.filter(
            name_key=comparison_key(normalized), organization=organization
        ).order_by("pk")[:2]
    )
    if len(matches) == 1:
        return matches[0], True
    reason = (
        f"Referente {role} non trovato: {raw_name}"
        if not matches
        else f"Referente {role} ambiguo: {raw_name}"
    )
    entity.skipped.append({"chiave": key, "motivo": reason})
    return None, False


def _wallet_activity_values(
    row: dict[str, Any],
    organizations: dict[str, Organization],
    entity: EntityReport,
) -> dict[str, Any] | None:
    code = row["codice"]
    project = None
    if row["tipo"] == ActivityKind.PROGETTO:
        project = Project.objects.filter(code=code).first()
        if project is None:
            entity.skipped.append(
                {"chiave": code, "motivo": f"Progetto collegato non trovato: {code}"}
            )
            return None
    client_owner, client_ok = _wallet_person(
        row.get("referente_bmed"),
        organizations["BMED"],
        entity=entity,
        key=code,
        role="BMED",
    )
    supplier_owner, supplier_ok = _wallet_person(
        row.get("referente_imola"),
        organizations["IMOLA"],
        entity=entity,
        key=code,
        role="Imola",
    )
    if not client_ok or not supplier_ok:
        return None
    return {
        "title": row["titolo"],
        "kind": row["tipo"],
        "project": project,
        "redmine_ref": code.removeprefix("RM-") if row["tipo"] == ActivityKind.REDMINE else "",
        "client_owner": client_owner,
        "supplier_owner": supplier_owner,
        "notes": row.get("note") or "",
        "is_technical": False,
    }


def _import_wallet_activities(
    rows: list[dict[str, Any]],
    organizations: dict[str, Organization],
    batch: ImportBatch,
    entity: EntityReport,
) -> None:
    seen: set[str] = set()
    for row in rows:
        code = row["codice"]
        if code in seen:
            entity.skipped.append({"chiave": code, "motivo": "Attività duplicata nel payload"})
            continue
        seen.add(code)
        values = _wallet_activity_values(row, organizations, entity)
        if values is None:
            continue
        activity = WalletActivity.objects.filter(code=code).first()
        if activity is None:
            WalletActivity.objects.create(code=code, import_batch=batch, **values)
            _record_created(entity, code)
        else:
            _apply_changes(activity, values, entity=entity, key=code)


def _wallet_allocation_values(
    row: dict[str, Any], wallet_year: WalletYear, activity: WalletActivity
) -> dict[str, Any] | None:
    allocated_days = row["gg_allocati"]
    consumed_days = row["gg_consumati_iniziali"]
    if allocated_days < 0 or consumed_days < 0:
        return None
    source_code = row.get("progetto_origine")
    source_project = Project.objects.filter(code=source_code).first() if source_code else None
    if source_code and source_project is None:
        return None
    return {
        "wallet_year": wallet_year,
        "source_project": source_project,
        "activity": activity,
        "allocated_days": allocated_days,
        "status": row["stato"],
        "notes": row.get("note") or "",
        "requires_source_attribution": source_project is None,
        "reliability": row["affidabilita"],
        "verification_points": [
            verification_point(text) for text in row.get("punti_da_verificare", [])
        ],
        "is_technical": False,
    }


def _import_wallet_timesheet(
    allocation: WalletAllocation,
    days: Decimal,
    reference_date: date | None,
    batch: ImportBatch,
    entity: EntityReport,
    report: ImportReport,
) -> None:
    if days == 0:
        return
    if reference_date is None:
        entity.errors.append(
            {"chiave": allocation.external_ref, "motivo": "Data di riferimento assente"}
        )
        return
    period = month_start(reference_date)
    key = f"{allocation.external_ref}:{period.isoformat()}"
    existing = TimesheetEntry.objects.filter(
        wallet_allocation=allocation,
        period=period,
        source=TimesheetSource.SEED_INIZIALE,
    ).first()
    if existing is not None:
        entity.unchanged += 1
        if existing.days != days:
            report.warnings.append(
                f"{key}: consuntivo seed esistente {existing.days} gg, nuovo valore {days} gg; "
                "differenza non applicata, usare un import PPM"
            )
        return
    TimesheetEntry.objects.create(
        wallet_allocation=allocation,
        period=period,
        days=days,
        source=TimesheetSource.SEED_INIZIALE,
        note="Consuntivo wallet iniziale importato dal seed JSON",
        import_batch=batch,
    )
    _record_created(entity, key)


def _import_wallet_allocations(
    rows: list[dict[str, Any]],
    reference_date: date | None,
    batch: ImportBatch,
    report: ImportReport,
) -> None:
    if not rows:
        return
    years_entity = report.entity("anni_wallet")
    entity = report.entity("allocazioni_wallet")
    timesheets_entity = report.entity("consuntivi_wallet")
    years: dict[int, WalletYear] = {}
    seen: set[str] = set()
    for row in rows:
        external_ref = row["id_import"]
        if external_ref in seen:
            entity.skipped.append(
                {"chiave": external_ref, "motivo": "Allocazione duplicata nel payload"}
            )
            continue
        seen.add(external_ref)
        activity = WalletActivity.objects.filter(code=row["attivita"]).first()
        if activity is None:
            entity.skipped.append(
                {
                    "chiave": external_ref,
                    "motivo": f"Attività non trovata o scartata: {row['attivita']}",
                }
            )
            continue
        year = row["anno_wallet"]
        if year not in years:
            years[year] = _wallet_year(year, batch, years_entity)
        wallet_year = years[year]
        values = _wallet_allocation_values(row, wallet_year, activity)
        if values is None:
            source_code = row.get("progetto_origine")
            reason = (
                f"Progetto di origine non trovato: {source_code}"
                if source_code and not Project.objects.filter(code=source_code).exists()
                else "Giornate allocate e consumate devono essere non negative"
            )
            entity.skipped.append({"chiave": external_ref, "motivo": reason})
            continue
        allocation = WalletAllocation.objects.filter(external_ref=external_ref).first()
        if allocation is None:
            allocation = WalletAllocation.objects.create(
                external_ref=external_ref, import_batch=batch, **values
            )
            _record_created(entity, external_ref)
        else:
            _apply_changes(allocation, values, entity=entity, key=external_ref)
        _import_wallet_timesheet(
            allocation,
            row["gg_consumati_iniziali"],
            reference_date,
            batch,
            timesheets_entity,
            report,
        )


def _import_historical_wallet(
    project_rows: list[dict[str, Any]],
    reference_date: date | None,
    batch: ImportBatch,
    report: ImportReport,
) -> None:
    candidates = [row for row in project_rows if "gg_wallet_storico_gia_usati" in row]
    if not candidates:
        return
    activities_entity = report.entity("attivita_wallet_storiche")
    allocations_entity = report.entity("allocazioni_wallet_storiche")
    timesheets_entity = report.entity("consuntivi_wallet_storici")
    years_entity = report.entity("anni_wallet_storici")
    wallet_year: WalletYear | None = None
    for row in candidates:
        project_code = row["codice"]
        days = row["gg_wallet_storico_gia_usati"]
        external_ref = f"STORICO-{project_code}"
        if days == 0:
            allocations_entity.skipped.append(
                {"chiave": external_ref, "motivo": "Giornate storiche a zero"}
            )
            continue
        if days < 0:
            allocations_entity.skipped.append(
                {"chiave": external_ref, "motivo": "Giornate storiche negative"}
            )
            continue
        duplicate_ref = HISTORICAL_DUPLICATES.get(project_code)
        if duplicate_ref:
            allocations_entity.skipped.append(
                {"chiave": external_ref, "motivo": f"Duplicato di {duplicate_ref}"}
            )
            continue
        project = Project.objects.filter(code=project_code).first()
        if project is None:
            allocations_entity.skipped.append(
                {"chiave": external_ref, "motivo": f"Progetto non trovato: {project_code}"}
            )
            continue
        if wallet_year is None:
            wallet_year = _wallet_year(HISTORICAL_WALLET_YEAR, batch, years_entity)
        activity = WalletActivity.objects.filter(code=external_ref).first()
        activity_values = {
            "title": f"Wallet storico già usato — {project.title}",
            "kind": ActivityKind.PROGETTO,
            "project": project,
            "redmine_ref": "",
            "client_owner": project.client_owner,
            "supplier_owner": project.supplier_owner,
            "notes": "Attività tecnica derivata da gg_wallet_storico_gia_usati",
            "is_technical": True,
        }
        if activity is None:
            activity = WalletActivity.objects.create(
                code=external_ref, import_batch=batch, **activity_values
            )
            _record_created(activities_entity, external_ref)
        else:
            _apply_changes(activity, activity_values, entity=activities_entity, key=external_ref)
        allocation = WalletAllocation.objects.filter(external_ref=external_ref).first()
        allocation_values = {
            "wallet_year": wallet_year,
            "source_project": project,
            "activity": activity,
            "allocated_days": days,
            "status": AllocationStatus.CHIUSA,
            "notes": "Allocazione tecnica storica importata dal seed JSON",
            "requires_source_attribution": False,
            "reliability": "DA_VERIFICARE",
            "verification_points": [
                verification_point("Confermare le giornate wallet storiche già usate")
            ],
            "is_technical": True,
        }
        if allocation is None:
            allocation = WalletAllocation.objects.create(
                external_ref=external_ref, import_batch=batch, **allocation_values
            )
            _record_created(allocations_entity, external_ref)
        else:
            _apply_changes(
                allocation, allocation_values, entity=allocations_entity, key=external_ref
            )
        _import_wallet_timesheet(allocation, days, reference_date, batch, timesheets_entity, report)


def _import_wallet(
    payload: dict[str, Any],
    organizations: dict[str, Organization],
    batch: ImportBatch,
    report: ImportReport,
) -> None:
    wallet = payload.get("wallet")
    reference_date = _as_date(payload.get("meta", {}).get("data_riferimento_dati"))
    if wallet:
        activity_rows = wallet.get("attivita", [])
        if activity_rows:
            _import_wallet_activities(
                activity_rows,
                organizations,
                batch,
                report.entity("attivita_wallet"),
            )
        _import_wallet_allocations(wallet.get("allocazioni", []), reference_date, batch, report)
    _import_historical_wallet(payload.get("progetti", []), reference_date, batch, report)


@transaction.atomic
def import_wallet_v3(
    wallet: dict[str, Any],
    *,
    batch: ImportBatch,
    report: ImportReport,
    reference_date: str | date | None,
) -> None:
    """Importa il modello v3: lotti sorgente, utilizzi e tranche di finanziamento."""
    from directory.models import Person
    from wallet.services import refresh_source_lot_status, sync_allocation_funding

    wallet_year = _wallet_year(int(wallet["anno"]), batch, report.entity("anni_wallet_v3"))
    adjustment = wallet.get("rettifica_riconciliazione", ZERO)
    if wallet_year.reconciliation_adjustment_days != adjustment:
        wallet_year.reconciliation_adjustment_days = adjustment
        wallet_year.save(update_fields=["reconciliation_adjustment_days", "updated_at", "version"])
    lots_entity = report.entity("lotti_sorgente_wallet")
    uses_entity = report.entity("utilizzi_wallet")
    funding_entity = report.entity("finanziamenti_wallet")
    timesheets_entity = report.entity("consuntivi_wallet_v3")
    lot_by_ref: dict[str, WalletSourceLot] = {}

    for row in wallet.get("lotti_sorgente", []):
        ref = row["id_import"]
        project = Project.objects.filter(code=row["progetto_origine"]).first()
        if project is None:
            lots_entity.skipped.append(
                {
                    "chiave": ref,
                    "motivo": f"Progetto origine non trovato: {row['progetto_origine']}",
                }
            )
            continue
        values = {
            "wallet_year": wallet_year,
            "source_project": project,
            "source_year": row["anno_provenienza"],
            "capacity_days": row["gg_capienza"],
            "effective_date": _as_date(row.get("data_conferimento")),
            "notes": row.get("note") or "",
        }
        lot = WalletSourceLot.objects.filter(external_ref=ref).first()
        if lot is None:
            lot = WalletSourceLot.objects.create(external_ref=ref, import_batch=batch, **values)
            _record_created(lots_entity, ref)
        else:
            _apply_changes(lot, values, entity=lots_entity, key=ref)
        lot_by_ref[ref] = lot

    parsed_reference = _as_date(reference_date)
    for row in wallet.get("utilizzi", []):
        ref = row["id_import"]
        activity = WalletActivity.objects.filter(code=row["attivita"]).first()
        if activity is None:
            uses_entity.skipped.append(
                {"chiave": ref, "motivo": f"Attività non trovata: {row['attivita']}"}
            )
            continue
        assignee = None
        if row.get("referente_imola"):
            assignee = Person.objects.filter(full_name__iexact=row["referente_imola"]).first()
        values = {
            "wallet_year": wallet_year,
            "source_project": None,
            "activity": activity,
            "assignee": assignee,
            "initial_allocated_days": row["gg_richiesti"],
            "allocated_days": row["gg_impegnati"],
            "status": row["stato"],
            "closure_reason": row.get("motivo_chiusura") or None,
            "closed_at": timezone.now() if row["stato"] == AllocationStatus.CHIUSA else None,
            "notes": row.get("note") or "",
            "requires_source_attribution": False,
            "reliability": row.get("affidabilita", "CERTO"),
            "verification_points": [
                verification_point(text) for text in row.get("punti_da_verificare", [])
            ],
            "is_technical": False,
        }
        allocation = WalletAllocation.objects.filter(external_ref=ref).first()
        if allocation is None:
            allocation = WalletAllocation.objects.create(
                external_ref=ref, import_batch=batch, **values
            )
            _record_created(uses_entity, ref)
        else:
            _apply_changes(allocation, values, entity=uses_entity, key=ref)

        for funding in row.get("finanziamenti", []):
            funding_ref = funding["id_import"]
            lot = lot_by_ref.get(funding["lotto_sorgente"])
            if lot is None:
                funding_entity.skipped.append(
                    {"chiave": funding_ref, "motivo": "Lotto sorgente non importato"}
                )
                continue
            funding_values = {
                "allocation": allocation,
                "source_lot": lot,
                "sequence": funding["ordine"],
                "initial_reserved_days": funding["gg_riservati_iniziali"],
                "committed_days": funding["gg_impegnati"],
                "consumed_days": ZERO,
            }
            tranche = WalletFundingTranche.objects.filter(external_ref=funding_ref).first()
            if tranche is None:
                WalletFundingTranche.objects.create(
                    external_ref=funding_ref, import_batch=batch, **funding_values
                )
                _record_created(funding_entity, funding_ref)
            else:
                _apply_changes(tranche, funding_values, entity=funding_entity, key=funding_ref)

        _import_wallet_timesheet(
            allocation,
            row["gg_consumati_iniziali"],
            parsed_reference,
            batch,
            timesheets_entity,
            report,
        )
        sync_allocation_funding(allocation)

    for lot in lot_by_ref.values():
        refresh_source_lot_status(lot)


def _as_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        dt = parse_datetime(value)
        if dt is None:
            raise ValueError(f"Data e ora non valida: {value}")
        parsed = dt
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _project_by_ppm_code(code: str) -> tuple[Project | None, str]:
    exact = list(Project.objects.filter(code=code).order_by("pk")[:2])
    if len(exact) == 1:
        return exact[0], ""
    normalized = normalize_project_code(code)
    matches = [
        project
        for project in Project.objects.only("id", "code").order_by("pk")
        if normalize_project_code(project.code) == normalized
    ][:2]
    if len(matches) == 1:
        return matches[0], ""
    if not matches:
        return None, f"Progetto non trovato: {code}"
    return None, f"Codice progetto ambiguo: {code}"


def _import_ppm_snapshot_rows(
    snapshot: PpmSnapshot,
    rows: list[dict[str, Any]],
    batch: ImportBatch,
    entity: EntityReport,
) -> None:
    seen: set[str] = set()
    for raw in rows:
        code = raw["codice_progetto"]
        key = f"{snapshot.pk}:{code}"
        if code in seen:
            entity.skipped.append({"chiave": key, "motivo": "Riga PPM duplicata nel payload"})
            continue
        seen.add(code)
        matches = list(PpmSnapshotRow.objects.filter(snapshot=snapshot, project_code=code)[:2])
        if len(matches) > 1:
            entity.skipped.append(
                {"chiave": key, "motivo": "Chiave naturale PPM ambigua nel database"}
            )
            continue
        project, unmatched_reason = _project_by_ppm_code(code)
        values = {
            "project": project,
            "supplier_owner_name": raw.get("responsabile_imola") or "",
            "ppm_status": raw.get("stato_ppm", ""),
            "planned_days": raw.get("gg_previsti"),
            "residual_days": raw.get("gg_residui"),
            "total_days": raw.get("gg_totali"),
            "raw": _json_value(raw),
            "unmatched_reason": unmatched_reason,
        }
        if not matches:
            PpmSnapshotRow.objects.create(
                snapshot=snapshot,
                project_code=code,
                import_batch=batch,
                **values,
            )
            _record_created(entity, key)
        else:
            _apply_changes(matches[0], values, entity=entity, key=key)


def _import_ppm_snapshots(
    rows: list[dict[str, Any]], batch: ImportBatch, report: ImportReport
) -> None:
    snapshots_entity = report.entity("snapshot_ppm")
    snapshot_rows_entity = report.entity("righe_snapshot_ppm")
    seen: set[tuple[str, datetime, str]] = set()
    for raw in rows:
        extracted_at = _as_datetime(raw["data_estrazione"])
        natural_key = (raw["tipo"], extracted_at, raw.get("file_origine", ""))
        key = f"{natural_key[0]}:{extracted_at.isoformat()}:{natural_key[2]}"
        if natural_key in seen:
            snapshots_entity.skipped.append(
                {"chiave": key, "motivo": "Snapshot PPM duplicato nel payload"}
            )
            continue
        seen.add(natural_key)
        matches = list(
            PpmSnapshot.objects.filter(
                kind=natural_key[0],
                extracted_at=natural_key[1],
                source_filename=natural_key[2],
            )[:2]
        )
        if len(matches) > 1:
            snapshots_entity.skipped.append(
                {"chiave": key, "motivo": "Chiave naturale snapshot ambigua nel database"}
            )
            continue
        values = {
            "title": raw.get("titolo", ""),
            "row_count": len(raw.get("righe", [])),
            "totals": _json_value(raw.get("totali", {})),
        }
        if not matches:
            snapshot = PpmSnapshot.objects.create(
                kind=natural_key[0],
                extracted_at=natural_key[1],
                source_filename=natural_key[2],
                import_batch=batch,
                **values,
            )
            _record_created(snapshots_entity, key)
        else:
            snapshot = matches[0]
            _apply_changes(snapshot, values, entity=snapshots_entity, key=key)
        _import_ppm_snapshot_rows(snapshot, raw.get("righe", []), batch, snapshot_rows_entity)


def _import_seed_anomalies(
    rows: list[dict[str, Any]], batch: ImportBatch, report: ImportReport
) -> None:
    entity = report.entity("anomalie_seed")
    references_entity = report.entity("riferimenti_anomalie_seed")
    seen: set[str] = set()
    for raw in rows:
        external_ref = raw["id_import"]
        if external_ref in seen:
            entity.skipped.append(
                {"chiave": external_ref, "motivo": "Anomalia duplicata nel payload"}
            )
            continue
        seen.add(external_ref)
        fingerprint = build_fingerprint(SEED_RULE_CODE, external_ref)
        matches = list(Anomaly.objects.filter(fingerprint=fingerprint)[:2])
        if len(matches) > 1:
            entity.skipped.append(
                {"chiave": external_ref, "motivo": "Fingerprint anomalia ambiguo"}
            )
            continue
        project_code = raw.get("codice_progetto")
        project = None
        reference_problem = ""
        if project_code:
            project, reference_problem = _project_by_ppm_code(project_code)
            if reference_problem:
                references_entity.skipped.append(
                    {"chiave": external_ref, "motivo": reference_problem}
                )
        context = {"id_import": external_ref, "raw": _json_value(raw)}
        if reference_problem:
            context["revisione_riferimento"] = reference_problem
        is_excel_defect = external_ref in SEED_EXCEL_DEFECT_ANOMALIES
        status = AnomalyStatus.RISOLTA if is_excel_defect else raw["stato"]

        values = {
            "external_ref": external_ref,
            "rule_code": SEED_RULE_CODE,
            "severity": raw["severita"],
            "scope": raw["ambito"],
            "description": raw["descrizione"],
            "status": status,
            "project": project,
            "context": context,
        }
        if is_excel_defect:
            values["resolution_note"] = SEED_EXCEL_DEFECT_RESOLUTION_NOTE
            values["resolved_at"] = timezone.now()

        if not matches:
            Anomaly.objects.create(
                fingerprint=fingerprint,
                import_batch=batch,
                **values,
            )
            _record_created(entity, external_ref)
        else:
            existing = matches[0]
            if existing.superseded_by_id is not None:
                # D-05: un'anomalia già sostituita da un controllo automatico conserva lo stato
                # RISOLTA; il reimport del seed non la riapre.
                values.pop("status", None)
                values.pop("resolution_note", None)
                values.pop("resolved_at", None)
            elif is_excel_defect:
                values["status"] = AnomalyStatus.RISOLTA
                values["resolution_note"] = SEED_EXCEL_DEFECT_RESOLUTION_NOTE
                if existing.resolved_at:
                    values["resolved_at"] = existing.resolved_at
            _apply_changes(existing, values, entity=entity, key=external_ref)
