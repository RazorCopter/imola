"""Esecuzione idempotente dei controlli e supersessione D-05."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from anomalies.models import SEED_RULE_CODE, Anomaly, AnomalyStatus, build_fingerprint
from domain.checks import RULES, Finding
from importers.seed_json import SEED_SUPERSESSION_MAP


@dataclass
class RunReport:
    detected: int = 0
    created: int = 0
    updated: int = 0
    resolved: int = 0
    superseded: int = 0
    by_rule: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "rilevate": self.detected,
            "create": self.created,
            "aggiornate": self.updated,
            "risolte": self.resolved,
            "seed_sostituite": self.superseded,
            "per_regola": self.by_rule,
        }


def _values(finding: Finding, now) -> dict:
    return {
        "rule_code": finding.rule_code,
        "severity": finding.severity,
        "scope": finding.scope,
        "description": finding.description,
        "suggested_action": finding.suggested_action,
        "context": finding.context,
        "project_id": finding.project_id,
        "allocation_id": finding.allocation_id,
        "canone_id": finding.canone_id,
        "subactivity_id": finding.subactivity_id,
        "snapshot_row_id": finding.snapshot_row_id,
        "milestone_id": finding.milestone_id,
        "last_seen_at": now,
    }


def _supersede_seed(report: RunReport) -> None:
    for external_ref, mapping in SEED_SUPERSESSION_MAP.items():
        if mapping is None:
            continue
        rule_code, expected = mapping
        expected_refs = set(expected if isinstance(expected, tuple) else (expected,))
        replacements = list(
            Anomaly.objects.filter(rule_code=rule_code).exclude(status=AnomalyStatus.RISOLTA)
        )
        covered: set[str] = set()
        for replacement in replacements:
            covered.update(replacement.extract_covered_entities())
        if not expected_refs.issubset(covered):
            continue
        seed = Anomaly.objects.filter(rule_code=SEED_RULE_CODE, external_ref=external_ref).first()
        if seed is None or seed.superseded_by_id is not None:
            continue
        replacement = next(
            (row for row in replacements if row.extract_covered_entities() & expected_refs),
            replacements[0] if replacements else None,
        )
        if replacement is not None:
            seed.mark_superseded(replacement)
            seed.resolution_note = f"sostituita da {rule_code}"
            seed.save(
                update_fields=[
                    "status",
                    "resolution_note",
                    "resolved_at",
                    "superseded_by",
                    "updated_at",
                ]
            )
            report.superseded += 1


@transaction.atomic
def run_checks(rule_codes: list[str] | None = None) -> RunReport:
    selected = rule_codes or list(RULES)
    unknown = sorted(set(selected) - set(RULES))
    if unknown:
        raise ValueError(f"Regole sconosciute: {', '.join(unknown)}")
    report = RunReport()
    now = timezone.now()
    seen: set[str] = set()
    for rule_code in selected:
        findings = list(RULES[rule_code]())
        report.by_rule[rule_code] = len(findings)
        report.detected += len(findings)
        for finding in findings:
            fingerprint = build_fingerprint(finding.rule_code, finding.entity_ref)
            seen.add(fingerprint)
            anomaly, created = Anomaly.objects.get_or_create(
                fingerprint=fingerprint,
                defaults={**_values(finding, now), "status": AnomalyStatus.APERTA},
            )
            if created:
                report.created += 1
                continue
            if anomaly.status == AnomalyStatus.ACCETTATA and (
                anomaly.accepted_until is None or anomaly.accepted_until >= now.date()
            ):
                continue
            changed = False
            for key, value in _values(finding, now).items():
                if key != "last_seen_at" and getattr(anomaly, key) != value:
                    changed = True
                setattr(anomaly, key, value)
            if anomaly.status == AnomalyStatus.RISOLTA:
                anomaly.status = AnomalyStatus.APERTA
                anomaly.resolved_at = None
                anomaly.resolution_note = ""
                changed = True
            anomaly.save()
            if changed:
                report.updated += 1

    stale = Anomaly.objects.filter(rule_code__in=selected).exclude(fingerprint__in=seen)
    for anomaly in stale:
        if anomaly.status in (AnomalyStatus.APERTA, AnomalyStatus.IN_VERIFICA):
            anomaly.resolve("Risolta automaticamente: condizione non più rilevata.")
            anomaly.save()
            report.resolved += 1
    _supersede_seed(report)
    return report
