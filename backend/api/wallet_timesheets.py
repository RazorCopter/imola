"""Consuntivi riga per riga su un'allocazione wallet.

La rettifica sintetica (`adjust_consumed_days`) storna tutto e riscrive una riga sola: va
bene come correzione amministrativa, non per il lavoro di tutti i giorni. Qui ogni giornata
erosa e una riga con data, giornate e descrizione, append-only come gli altri consuntivi:
una correzione e uno storno, non una modifica.

Il consumo scala le tranche FIFO nell'ordine di prelievo (`sync_allocation_funding`), quindi
il residuo dell'allocazione e quello dei lotti di origine restano allineati.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.timesheet_authors import resolve_author
from core.permissions import CanCreateTimesheets, CanEditTimesheets
from domain.money import ZERO


class WalletTimesheetResponseSerializer(serializers.Serializer):
    """Risposta documentata: il dettaglio aggiornato dell'allocazione."""


def entry_payload(entry) -> dict:
    return {
        "id": str(entry.id),
        "data": entry.period.isoformat() if entry.period else None,
        "giornate": str(entry.days),
        "descrizione": entry.note,
        "utente": (
            (entry.created_by.get_full_name() or entry.created_by.username)
            if entry.created_by
            else "Importazione"
        ),
        "utente_id": entry.created_by_id,
        "origine": entry.source,
    }


def active_entries(allocation):
    from timesheets.models import TimesheetSource

    return (
        allocation.timesheet_entries.filter(reversals__isnull=True)
        .exclude(source=TimesheetSource.STORNO)
        .select_related("created_by")
        .order_by("-period", "-created_at")
    )


def allocation_payload(allocation) -> dict:
    consumed = allocation.timesheet_entries.aggregate(total=Sum("days"))["total"] or ZERO
    return {
        "id": str(allocation.id),
        "version": allocation.version,
        "allocated_days": str(allocation.allocated_days),
        "consumed_days": str(consumed),
        "available_days": str(allocation.allocated_days - consumed),
        "status": allocation.status,
        "consuntivi": [entry_payload(entry) for entry in active_entries(allocation)],
    }


def parse_entry(request, *, entry=None):
    """Legge data, giornate e descrizione, con i valori attuali come default in rettifica."""
    raw_days = request.data.get("giornate", entry.days if entry else "")
    try:
        days = Decimal(str(raw_days))
    except InvalidOperation as exc:
        raise DjangoValidationError({"giornate": "Inserire un numero valido."}) from exc
    raw_date = request.data.get("data", entry.period.isoformat() if entry else "")
    try:
        period = date.fromisoformat(str(raw_date))
    except ValueError as exc:
        raise DjangoValidationError({"data": "Inserire una data valida."}) from exc
    description = str(request.data.get("descrizione", entry.note if entry else "")).strip()
    if days <= 0:
        raise DjangoValidationError({"giornate": "Le giornate devono essere maggiori di zero."})
    if not description:
        raise DjangoValidationError({"descrizione": "La descrizione è obbligatoria."})
    if len(description) > 300:
        raise DjangoValidationError({"descrizione": "Massimo 300 caratteri."})
    return days, period, description


class WalletAllocationTimesheetListView(APIView):
    """Registra un consuntivo sull'allocazione: erode le giornate riservate."""

    permission_classes = [CanCreateTimesheets]
    serializer_class = WalletTimesheetResponseSerializer

    @staticmethod
    def get_allocation(pk):
        from wallet.models import WalletAllocation

        return get_object_or_404(
            WalletAllocation.objects.select_for_update().select_related("activity"), pk=pk
        )

    @extend_schema(request=dict, responses={201: WalletTimesheetResponseSerializer})
    @transaction.atomic
    def post(self, request, pk):
        from timesheets.models import TimesheetEntry, TimesheetSource
        from wallet.models import AllocationStatus
        from wallet.services import sync_allocation_funding

        allocation = self.get_allocation(pk)
        if allocation.status == AllocationStatus.CHIUSA:
            return Response(
                {"detail": "L'allocazione è chiusa: riaprirla per registrare altri consuntivi."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            days, period, description = parse_entry(request)
            author = resolve_author(request)
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)

        consumed = allocation.timesheet_entries.aggregate(total=Sum("days"))["total"] or ZERO
        if consumed + days > allocation.allocated_days:
            return Response(
                {
                    "giornate": [
                        "Il consuntivo supera le giornate riservate all'allocazione "
                        f"(residuo {allocation.allocated_days - consumed} gg)."
                    ]
                },
                status=400,
            )

        entry = TimesheetEntry(
            wallet_allocation=allocation,
            period=period,
            days=days,
            source=TimesheetSource.MANUALE,
            note=description,
            created_by=author,
            updated_by=request.user,
        )
        try:
            entry.full_clean()
            entry.save()
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)
        sync_allocation_funding(allocation)
        allocation.refresh_from_db()
        return Response(allocation_payload(allocation), status=status.HTTP_201_CREATED)


class WalletAllocationTimesheetDetailView(APIView):
    """Rettifica o annulla un consuntivo dell'allocazione, sempre con uno storno."""

    permission_classes = [CanEditTimesheets]
    serializer_class = WalletTimesheetResponseSerializer

    @staticmethod
    def get_entry(allocation_pk, entry_pk):
        from timesheets.models import TimesheetEntry, TimesheetSource

        return get_object_or_404(
            TimesheetEntry.objects.select_related("wallet_allocation"),
            pk=entry_pk,
            wallet_allocation_id=allocation_pk,
            source=TimesheetSource.MANUALE,
            reversals__isnull=True,
        )

    @extend_schema(request=dict, responses={200: WalletTimesheetResponseSerializer})
    @transaction.atomic
    def patch(self, request, pk, entry_pk):
        from timesheets.models import TimesheetEntry, TimesheetSource
        from wallet.services import sync_allocation_funding

        entry = self.get_entry(pk, entry_pk)
        allocation = entry.wallet_allocation
        try:
            days, period, description = parse_entry(request, entry=entry)
            author = resolve_author(request, default=entry.created_by)
        except DjangoValidationError as exc:
            return Response(getattr(exc, "message_dict", {"detail": exc.messages}), status=400)

        consumed_without_entry = (
            allocation.timesheet_entries.aggregate(total=Sum("days"))["total"] or ZERO
        ) - entry.days
        if consumed_without_entry + days > allocation.allocated_days:
            return Response(
                {"giornate": ["Il consuntivo supera le giornate riservate all'allocazione."]},
                status=400,
            )

        reversal = entry.build_reversal(note=f"Rettifica del consuntivo {entry.id}")
        reversal.created_by = request.user
        reversal.updated_by = request.user
        reversal.full_clean()
        reversal.save()
        replacement = TimesheetEntry(
            wallet_allocation=allocation,
            period=period,
            days=days,
            source=TimesheetSource.MANUALE,
            note=description,
            created_by=author,
            updated_by=request.user,
        )
        replacement.full_clean()
        replacement.save()
        sync_allocation_funding(allocation)
        allocation.refresh_from_db()
        return Response(allocation_payload(allocation))

    @extend_schema(responses={200: WalletTimesheetResponseSerializer})
    @transaction.atomic
    def delete(self, request, pk, entry_pk):
        from wallet.services import sync_allocation_funding

        entry = self.get_entry(pk, entry_pk)
        allocation = entry.wallet_allocation
        reversal = entry.build_reversal(note=f"Eliminazione del consuntivo {entry.id}")
        reversal.created_by = request.user
        reversal.updated_by = request.user
        reversal.full_clean()
        reversal.save()
        sync_allocation_funding(allocation)
        allocation.refresh_from_db()
        return Response(allocation_payload(allocation))
