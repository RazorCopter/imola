from __future__ import annotations

from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from domain.money import ZERO
from timesheets.models import TimesheetEntry
from wallet.models import AllocationClosureReason, AllocationStatus, WalletAllocation
from wallet.services import sync_allocation_funding


@receiver(post_save, sender=TimesheetEntry)
def distribute_wallet_consumption(
    sender, instance: TimesheetEntry, created: bool, **kwargs
) -> None:
    if instance.wallet_allocation_id is None:
        return
    allocation = WalletAllocation.objects.get(pk=instance.wallet_allocation_id)
    if allocation.funding_tranches.exists():
        sync_allocation_funding(allocation)

    total = allocation.timesheet_entries.aggregate(total=Sum("days"))["total"] or ZERO
    if total >= allocation.allocated_days and allocation.allocated_days > ZERO:
        if allocation.status != AllocationStatus.CHIUSA:
            allocation.status = AllocationStatus.CHIUSA
            allocation.closure_reason = AllocationClosureReason.ESAURITA
            allocation.closed_at = timezone.now()
            allocation.save(
                update_fields=["status", "closure_reason", "closed_at", "updated_at", "version"]
            )


@receiver(post_delete, sender=TimesheetEntry)
def redistribute_wallet_consumption_after_delete(
    sender, instance: TimesheetEntry, **kwargs
) -> None:
    if instance.wallet_allocation_id is None:
        return
    allocation = WalletAllocation.objects.filter(pk=instance.wallet_allocation_id).first()
    if allocation is not None and allocation.funding_tranches.exists():
        sync_allocation_funding(allocation)
