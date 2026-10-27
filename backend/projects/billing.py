from __future__ import annotations

from calendar import monthrange
from datetime import date

from projects.models import (
    BillingMilestone,
    BillingScheduleSlot,
    BillingStatus,
    MilestoneStatus,
    Project,
)


def month_end(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def sync_project_billing_schedule(project: Project, *, user=None) -> None:
    """Sincronizza le due tranche automatiche con date e stato del progetto."""
    if not project.start_date or not project.planned_end_date:
        project.milestones.filter(schedule_slot__in=BillingScheduleSlot.values).delete()
        return

    dates = {
        BillingScheduleSlot.START: month_end(project.start_date),
        BillingScheduleSlot.END: month_end(project.planned_end_date),
    }
    statuses = {
        BillingStatus.DA_FATTURARE: {
            BillingScheduleSlot.START: MilestoneStatus.PIANIFICATA,
            BillingScheduleSlot.END: MilestoneStatus.PIANIFICATA,
        },
        BillingStatus.PARZIALE: {
            BillingScheduleSlot.START: MilestoneStatus.FATTURATA,
            BillingScheduleSlot.END: MilestoneStatus.PIANIFICATA,
        },
        BillingStatus.TOTALE: {
            BillingScheduleSlot.START: MilestoneStatus.FATTURATA,
            BillingScheduleSlot.END: MilestoneStatus.FATTURATA,
        },
        BillingStatus.NON_FATTURABILE: {
            BillingScheduleSlot.START: MilestoneStatus.ANNULLATA,
            BillingScheduleSlot.END: MilestoneStatus.ANNULLATA,
        },
        BillingStatus.DA_VERIFICARE: {
            BillingScheduleSlot.START: MilestoneStatus.DA_VERIFICARE,
            BillingScheduleSlot.END: MilestoneStatus.DA_VERIFICARE,
        },
    }[project.billing_status]

    for slot, planned_date in dates.items():
        milestone, _created = BillingMilestone.objects.get_or_create(
            project=project,
            schedule_slot=slot,
            defaults={"planned_date": planned_date},
        )
        milestone.planned_date = planned_date
        milestone.status = statuses[slot]
        milestone.actual_date = (
            planned_date if milestone.status == MilestoneStatus.FATTURATA else None
        )
        milestone.updated_by = user
        if milestone.created_by_id is None:
            milestone.created_by = user
        milestone.save()
