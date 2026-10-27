"""Proiezione deterministica dei dataset Excel nel contratto applicativo seed v1."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any


def _dataset(seed: dict[str, Any], dataset_id: str) -> list[dict[str, Any]]:
    return next(item["rows"] for item in seed["datasets"] if item["id"] == dataset_id)


def _cell_value(seed: dict[str, Any], sheet_name: str, ref: str) -> Any:
    sheet = next(item for item in seed["workbook"]["sheets"] if item["name"] == sheet_name)
    cell = next((item for item in sheet["cells"] if item["ref"] == ref), None)
    return None if cell is None else cell.get("value")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).replace("\xa0", " ").strip()
    return result or None


def _person(value: Any) -> str | None:
    result = _text(value)
    if not result or result.upper() in {"N/D", "ND", "0", "-"}:
        return None
    aliases = {
        "gianvito": "Gianvito Bleve",
        "ravagli andrea": "Andrea Ravagli",
        "salvatore di salvo": "Salvatore di Salvo",
    }
    if result.casefold() in aliases:
        return aliases[result.casefold()]
    return result


def _date(value: Any) -> str | None:
    result = _text(value)
    if not result or result == "-":
        return None
    candidate = result[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def _number(value: Any, default: float | None = 0) -> int | float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return default
    rounded = round(value, 4)
    return 0 if rounded == 0 else rounded


def _code_key(value: Any) -> str:
    result = (_text(value) or "").upper()
    return result.replace("-BMED-", "-")


def _activity_code(title: str, project_code: str | None) -> tuple[str, str]:
    if project_code:
        return project_code, "PROGETTO"
    redmine = re.search(r"(?:issues/|#)(\d{4,})", title, flags=re.IGNORECASE)
    if redmine:
        return f"RM-{redmine.group(1)}", "REDMINE"
    slug = re.sub(r"[^A-Z0-9]+", "-", title.upper()).strip("-")[:90] or "ATTIVITA"
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8].upper()
    return f"ATT-{slug}-{digest}"[:120], "ATTIVITA"


def _project_status(excel_status: str | None) -> tuple[str, str]:
    status = (excel_status or "").casefold()
    if status == "offerta inviata":
        return "INVIATA", "NON_AVVIATO"
    if status == "offerta accettata":
        return "ACCETTATA", "NON_AVVIATO"
    if status in {"in corso", "wallet"}:
        return "ACCETTATA", "ATTIVO"
    if status == "terminato":
        return "ACCETTATA", "CHIUSO"
    return "ACCETTATA", "DA_VERIFICARE"


def _contract_type(value: Any) -> str:
    return {
        "canone": "CANONE",
        "aql": "AQL",
        "corpo": "CORPO",
        "ppm": "PPM",
    }.get((_text(value) or "").casefold(), "ATTIVITA")


def _verification(text: str) -> str:
    return f"Proiezione Excel: {text}"


def build_application_projection(seed: dict[str, Any]) -> dict[str, Any]:
    project_rows = _dataset(seed, "Progetti::Tabella3967")
    wallet_rows = _dataset(seed, "Wallet proposta::Table578")
    capacity_rows = _dataset(seed, "Capacity Mensile::intervallo_principale")
    projects_by_key = {
        _code_key(row["values"]["codice"]): _text(row["values"]["codice"])
        for row in project_rows
        if _text(row["values"].get("codice"))
    }
    reference_month = seed["meta"]["workbook_reference_date"][:7]
    capacity_periods = {
        **{str(month): f"2024-{month:02d}-01" for month in range(1, 13)},
        **{f"{month}_2": f"2026-{month:02d}-01" for month in range(1, 13)},
    }
    capacity_weights: dict[str, dict[str, dict[str, Any]]] = {}
    for source in capacity_rows:
        values = source["values"]
        project_code = projects_by_key.get(_code_key(values.get("codice_attività")))
        if not project_code:
            continue
        for column, period in capacity_periods.items():
            value = _number(values.get(column), None)
            if value is None or value <= 0 or period[:7] > reference_month:
                continue
            period_data = capacity_weights.setdefault(project_code, {}).setdefault(
                period,
                {"capacity_days": 0, "source_rows": []},
            )
            period_data["capacity_days"] = _number(period_data["capacity_days"] + value)
            period_data["source_rows"].append(source["source_row"])

    supplier_by_project: dict[str, str] = {}
    for row in wallet_rows:
        values = row["values"]
        supplier = _person(values.get("referente_imola"))
        source = projects_by_key.get(_code_key(values.get("codice_imola")))
        if source and supplier:
            supplier_by_project.setdefault(source, supplier)
    for row in capacity_rows:
        values = row["values"]
        supplier = _person(values.get("colonna_4"))
        source = projects_by_key.get(_code_key(values.get("codice_attività")))
        if source and supplier:
            supplier_by_project.setdefault(source, supplier)

    projects: list[dict[str, Any]] = []
    monthly_timesheets: list[dict[str, Any]] = []
    client_people: set[str] = set()
    supplier_people: set[str] = set(supplier_by_project.values())
    for source in project_rows:
        row = source["values"]
        code = _text(row.get("codice"))
        if not code:
            continue
        client_owner = _person(row.get("responsabile"))
        supplier_owner = supplier_by_project.get(code) or _person(row.get("referente_imola"))
        if client_owner:
            client_people.add(client_owner)
        if supplier_owner:
            supplier_people.add(supplier_owner)
        start_date = _date(row.get("data_inizio"))
        end_date = _date(row.get("data_fine2"))
        verification_points: list[str] = []
        if start_date and end_date and end_date < start_date:
            verification_points.append(_verification("data fine precedente alla data inizio"))
            end_date = None
        budget = _number(row.get("gg"))
        consumed = _number(row.get("gg_consumate"))
        released_to_wallet = _number(row.get("delta_terminato2"))
        if row.get("gg") is None:
            verification_points.append(_verification("budget giornate assente, impostato a zero"))
        offer_status, timesheet_status = _project_status(_text(row.get("stato")))
        actual_closure = end_date if timesheet_status == "CHIUSO" else None
        if timesheet_status == "CHIUSO" and actual_closure is None:
            verification_points.append(_verification("progetto terminato senza data di chiusura"))
        if timesheet_status == "DA_VERIFICARE":
            verification_points.append(_verification("stato Excel Chiuso da confermare"))
        milestones = []
        for key in ("milestone_1", "milestone_2", "milestone_3", "milestone_4"):
            milestone_date = _date(row.get(key))
            if milestone_date:
                milestones.append({"data_prevista": milestone_date, "stato": "DA_VERIFICARE"})
        notes = " | ".join(
            value for value in (_text(row.get("note")), _text(row.get("note_stato"))) if value
        )
        projects.append(
            {
                "codice": code,
                "titolo": code,
                "tipo_contratto": _contract_type(row.get("tipo")),
                "codice_aro": _text(row.get("aro")),
                "codice_rda": _text(row.get("rda")),
                "deliverable": None,
                "referente_bmed": client_owner,
                "referente_imola": supplier_owner,
                "gg_budget": budget,
                "gg_consumati_su_progetto": consumed,
                "gg_rilasciati_wallet": released_to_wallet,
                "data_inizio": start_date,
                "data_fine_prevista": end_date,
                "milestone_fatturazione": milestones,
                "stato_offerta": offer_status,
                "stato_consuntivazione": timesheet_status,
                "data_chiusura_consuntivazione": actual_closure,
                "anno_riferimento_residuo": (
                    int(seed["meta"]["workbook_reference_date"][:4])
                    if released_to_wallet > 0
                    else int(actual_closure[:4])
                    if actual_closure
                    else None
                ),
                "stato_fatturazione": "DA_VERIFICARE",
                "stato_excel_originale": _text(row.get("stato")),
                "note": notes or None,
                "affidabilita": "DA_VERIFICARE" if verification_points else "CERTO",
                "punti_da_verificare": verification_points,
            }
        )
        weights = capacity_weights.get(code, {})
        total_weight = sum(item["capacity_days"] for item in weights.values())
        if consumed and consumed > 0 and total_weight > 0:
            allocated = 0
            weighted_periods = sorted(weights.items())
            for index, (period, period_data) in enumerate(weighted_periods):
                days = (
                    _number(consumed - allocated)
                    if index == len(weighted_periods) - 1
                    else _number(consumed * period_data["capacity_days"] / total_weight)
                )
                allocated = _number(allocated + days)
                monthly_timesheets.append(
                    {
                        "codice_progetto": code,
                        "periodo": period,
                        "giornate": days,
                        "peso_capacity_excel": period_data["capacity_days"],
                        "righe_excel": sorted(set(period_data["source_rows"])),
                        "metodo": "RIPARTIZIONE_PROPORZIONALE_SU_CAPACITY_MENSILE",
                    }
                )

    activities: dict[str, dict[str, Any]] = {}
    source_lots: list[dict[str, Any]] = []
    source_lot_by_project: dict[str, str] = {}
    project_rows_by_code = {
        _text(row["values"].get("codice")): row["values"]
        for row in project_rows
        if _text(row["values"].get("codice"))
    }
    for project in projects:
        raw = project_rows_by_code[project["codice"]]
        capacity = _number(raw.get("delta_terminato2"))
        if (_text(raw.get("stato")) or "").casefold() != "wallet" or not capacity or capacity <= 0:
            continue
        effective_date = _date(raw.get("data_fine2"))
        source_year = int(effective_date[:4]) if effective_date else int(project["codice"][2:4]) + 2000
        lot_ref = f"LOT-{project['codice']}"
        source_lot_by_project[project["codice"]] = lot_ref
        source_lots.append(
            {
                "id_import": lot_ref,
                "anno_wallet": int(seed["meta"]["workbook_reference_date"][:4]),
                "progetto_origine": project["codice"],
                "anno_provenienza": source_year,
                "data_conferimento": effective_date,
                "gg_capienza": capacity,
                "stato_excel_progetto": _text(raw.get("stato")),
                "note": _text(raw.get("note_stato")),
            }
        )

    usage_groups: dict[str, dict[str, Any]] = {}
    for source in wallet_rows:
        row = source["values"]
        client_owner = _person(row.get("referente_bmed"))
        supplier_owner = _person(row.get("referente_imola"))
        if client_owner:
            client_people.add(client_owner)
        if supplier_owner:
            supplier_people.add(supplier_owner)

    for source in wallet_rows:
        row = source["values"]
        excel_status = (_text(row.get("stato")) or "").casefold()
        if excel_status != "wallet":
            continue
        source_raw = _text(row.get("codice_imola"))
        destination_raw = _text(row.get("codice_bmed")) or source_raw
        if not source_raw or not destination_raw:
            continue
        source_project = projects_by_key.get(_code_key(source_raw))
        activity_project = projects_by_key.get(_code_key(destination_raw))
        activity_code, activity_kind = _activity_code(destination_raw, activity_project)
        client_owner = _person(row.get("referente_bmed"))
        supplier_owner = _person(row.get("referente_imola"))
        if client_owner:
            client_people.add(client_owner)
        if supplier_owner:
            supplier_people.add(supplier_owner)
        activities.setdefault(
            activity_code,
            {
                "codice": activity_code,
                "titolo": destination_raw,
                "tipo": activity_kind,
                "referente_bmed": client_owner,
                "referente_imola": supplier_owner,
                "note": _text(row.get("note")),
            },
        )
        allocated = _number(row.get("gg_previste"))
        consumed = _number(row.get("gg_consumate"))
        remaining = row.get("gg_rimanenti")
        verification_points = []
        if source_project is None:
            verification_points.append(_verification("progetto origine non riconciliato"))
        if isinstance(remaining, (int, float)) and remaining < 0:
            verification_points.append(_verification("allocazione wallet in sforamento"))
        note = _text(row.get("note"))
        usage = usage_groups.setdefault(
            activity_code,
            {
                "id_import": f"USE-{hashlib.sha1(activity_code.encode('utf-8')).hexdigest()[:12].upper()}",
                "anno_wallet": int(seed["meta"]["workbook_reference_date"][:4]),
                "attivita": activity_code,
                "referente_imola": supplier_owner,
                "gg_richiesti": 0,
                "gg_impegnati": 0,
                "gg_consumati_iniziali": 0,
                "stato": "APERTA",
                "motivo_chiusura": None,
                "note": note,
                "finanziamenti": [],
                "affidabilita": "CERTO",
                "punti_da_verificare": [],
            },
        )
        closed_with_residual = False
        committed = consumed if closed_with_residual else allocated
        usage["gg_richiesti"] = _number(usage["gg_richiesti"] + allocated)
        usage["gg_impegnati"] = _number(usage["gg_impegnati"] + committed)
        usage["gg_consumati_iniziali"] = _number(usage["gg_consumati_iniziali"] + consumed)
        lot_ref = source_lot_by_project.get(source_project or "")
        if lot_ref is None:
            verification_points.append(_verification("lotto sorgente non disponibile"))
        else:
            usage["finanziamenti"].append(
                {
                    "id_import": f"FUND-WV3-{source['source_row']:03d}",
                    "lotto_sorgente": lot_ref,
                    "ordine": len(usage["finanziamenti"]) + 1,
                    "gg_riservati_iniziali": allocated,
                    "gg_impegnati": committed,
                    "gg_consumati": consumed,
                    "riga_excel": source["source_row"],
                }
            )
        usage["punti_da_verificare"].extend(verification_points)
        if verification_points:
            usage["affidabilita"] = "DA_VERIFICARE"
        if closed_with_residual:
            usage["stato"] = "CHIUSA"
            usage["motivo_chiusura"] = "CON_RESIDUO"

    usages = list(usage_groups.values())
    lot_fifo_key = {
        lot["id_import"]: (
            lot["anno_provenienza"],
            lot["data_conferimento"] or "9999-12-31",
            lot["progetto_origine"],
        )
        for lot in source_lots
    }
    for usage in usages:
        usage["finanziamenti"].sort(
            key=lambda funding: (
                lot_fifo_key.get(funding["lotto_sorgente"], (9999, "9999-12-31", "")),
                funding["riga_excel"],
            )
        )
        remaining_consumed = usage["gg_consumati_iniziali"]
        for sequence, funding in enumerate(usage["finanziamenti"], start=1):
            funding["ordine"] = sequence
            consumed_from_tranche = min(remaining_consumed, funding["gg_impegnati"])
            funding["gg_consumati"] = _number(consumed_from_tranche)
            remaining_consumed = _number(max(0, remaining_consumed - consumed_from_tranche))
        if usage["gg_richiesti"] > 0 and usage["gg_consumati_iniziali"] >= usage["gg_richiesti"]:
            usage["stato"] = "CHIUSA"
            usage["motivo_chiusura"] = "ESAURITA"

    canone_codes = [project["codice"] for project in projects if project["tipo_contratto"] == "CANONE"]
    canoni = []
    for semester, dataset_id in (
        ("2026-S1", "OA-attività S1::intervallo_principale"),
        ("2026-S2", "OA-attività S2::intervallo_principale"),
    ):
        project_code = next(
            (code for code in canone_codes if semester in code),
            None,
        )
        if project_code is None:
            continue
        rows = _dataset(seed, dataset_id)
        subactivities = []
        for source in rows:
            row = source["values"]
            title = _text(row.get("codice"))
            if not title:
                continue
            subactivities.append(
                {
                    "ufficio": _text(row.get("ufficio")),
                    "titolo": title,
                    "gg_consuntivati": _number(row.get("gg_tot")),
                    "stima_trimestre": _number(row.get("stima_trim_18_09"), None),
                    "forecast_residuo_31_12": _number(row.get("forecast_31_12"), None),
                    "note": _text(row.get("note")),
                }
            )
        project = next(item for item in projects if item["codice"] == project_code)
        canoni.append(
            {
                "codice_progetto": project_code,
                "semestre": semester,
                "monte_gg": project["gg_budget"],
                "data_estrazione": seed["meta"]["workbook_reference_date"],
                "formula_target": {
                    "base_gg": 2,
                    "gg_per_settimana": 6.69,
                    "settimane_trascorse": 26 if semester.endswith("S1") else 15,
                    "cap_al_monte": True,
                },
                "sottoattivita": subactivities,
            }
        )

    people = [
        *(
            {"nome": name, "organizzazione": "BMED", "email": None}
            for name in sorted(client_people)
        ),
        *(
            {"nome": name, "organizzazione": "IMOLA", "email": None}
            for name in sorted(supplier_people)
        ),
    ]
    seed_v1 = {
        "$schema": "./seed_schema_v1.json",
        "meta": {
            "schema_version": "1.0.0",
            "generato_il": seed["meta"]["generated_at"][:10],
            "fonte_principale": seed["meta"]["source"]["filename"],
            "fonti_secondarie": [],
            "data_riferimento_dati": seed["meta"]["workbook_reference_date"],
            "note": "Proiezione applicativa deterministica incorporata nel seed workbook v2.",
        },
        "configurazione": {
            "fornitore": {"codice": "IMOLA", "ragione_sociale": "Imola Informatica"},
            "cliente": {"codice": "BMED", "ragione_sociale": "Banca Mediolanum"},
            "unita_misura": "giornata_uomo",
            "ore_per_giornata": 8,
            "granularita_ppm_gg": 0.0625,
            "tolleranza_riconciliazione_gg": 0.01,
            "regola_scadenza_residui": {
                "si_applica_a": "PROGETTI_CON_CONSUNTIVAZIONE_CHIUSA",
                "anno_base": "ANNO_DATA_CHIUSURA_CONSUNTIVAZIONE",
                "anni_validita_dopo_chiusura": 1,
                "fatturazione_influisce": False,
                "descrizione": "Residui utilizzabili nell'anno di chiusura e nel successivo.",
            },
        },
        "persone": people,
        "progetti": projects,
        "canoni": canoni,
        "wallet": {"anno": 2026, "attivita": list(activities.values()), "allocazioni": []},
        "snapshot_ppm": [],
        "anomalie_aperte": [],
    }
    return {
        "projection_version": "4.0.0",
        "source_policy": {
            "projects": "Progetti::Tabella3967",
            "wallet": (
                "Wallet proposta::Table578; righe operative con Stato Wallet o Terminato; "
                "righe Chiuso conservate solo nel dataset integrale"
            ),
            "canone_s1": "OA-attività S1::intervallo_principale",
            "canone_s2": "OA-attività S2::intervallo_principale",
            "capacity": (
                "Capacity Mensile::intervallo_principale; valori mensili fino alla data di "
                "riferimento usati come pesi per ripartire il consuntivo progetto senza "
                "alterarne il totale"
            ),
        },
        "coverage": {
            "projects": len(projects),
            "people": len(people),
            "canoni": len(canoni),
            "wallet_activities": len(activities),
            "wallet_allocations": len(usages),
            "monthly_timesheets": len(monthly_timesheets),
        },
        "seed_v1": seed_v1,
        "monthly_timesheets": monthly_timesheets,
        "wallet_v3": {
            "anno": int(seed["meta"]["workbook_reference_date"][:4]),
            "regola_erosione": "FIFO_ANNO_PROVENIENZA_DATA_CODICE",
            "saldo_non_allocato_excel": _number(
                _cell_value(seed, "Wallet proposta", "D4"), None
            ),
            "rettifica_riconciliazione": _number(
                (_cell_value(seed, "Wallet proposta", "D4") or 0)
                - (
                    sum(lot["gg_capienza"] for lot in source_lots)
                    - sum(usage["gg_impegnati"] for usage in usages)
                )
            ),
            "lotti_sorgente": source_lots,
            "utilizzi": usages,
        },
    }
