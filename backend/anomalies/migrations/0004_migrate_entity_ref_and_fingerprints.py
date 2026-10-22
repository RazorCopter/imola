from __future__ import annotations

import hashlib
from django.db import migrations


def migrate_fingerprints(apps, schema_editor):
    Anomaly = apps.get_model("anomalies", "Anomaly")

    def build_fp(rule_code: str, ref: str) -> str:
        payload = f"{rule_code}|{ref}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    seen_fps: set[str] = set()
    for anomaly in Anomaly.objects.all().order_by("-updated_at", "-id"):
        ref = anomaly.entity_ref
        if not ref:
            if anomaly.project_id:
                Project = apps.get_model("projects", "Project")
                proj = Project.objects.filter(pk=anomaly.project_id).first()
                ref = proj.code if proj else ""
            elif anomaly.context and isinstance(anomaly.context, dict):
                ref = str(
                    anomaly.context.get("source_project")
                    or anomaly.context.get("project_code")
                    or anomaly.context.get("entity")
                    or anomaly.context.get("activity")
                    or anomaly.external_ref
                    or ""
                )
            else:
                ref = str(anomaly.external_ref or "")
        anomaly.entity_ref = ref
        if ref and anomaly.rule_code != "SEED_MANUALE":
            new_fp = build_fp(anomaly.rule_code, ref)
            if new_fp in seen_fps:
                anomaly.delete()
                continue
            anomaly.fingerprint = new_fp
            seen_fps.add(new_fp)
        anomaly.save()


class Migration(migrations.Migration):
    dependencies = [
        ("anomalies", "0003_anomaly_entity_ref_historicalanomaly_entity_ref"),
    ]

    operations = [
        migrations.RunPython(migrate_fingerprints, migrations.RunPython.noop),
    ]
