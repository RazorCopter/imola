"""Caricamento e validazione del seed JSON.

Due letture dello stesso testo, deliberatamente:

- una con `parse_float=float`, che serve a `jsonschema`: il validatore riconosce come
  "number" solo int e float, un Decimal non lo considera numerico e la validazione
  fallirebbe su ogni giornata;
- una con `parse_float=Decimal`, che è quella da cui si importano i valori, perché le
  giornate sono dati contabili e non devono mai passare da un float.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SUPPORTED_SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS = ("1.0.0", "2.0.0", "3.0.0")


class SeedValidationError(ValueError):
    """Il file non rispetta lo schema: l'import si ferma prima di toccare il database."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems = problems or []


def load_schema(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_seed(text: str) -> dict[str, Any]:
    """Payload con i numeri come Decimal, da usare per l'import."""
    from decimal import Decimal

    return json.loads(text, parse_float=Decimal)


def detect_schema_version(text: str) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SeedValidationError(f"JSON non valido: {exc}") from exc
    version = parsed.get("meta", {}).get("schema_version") if isinstance(parsed, dict) else None
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        expected = ", ".join(SUPPORTED_SCHEMA_VERSIONS)
        raise SeedValidationError(
            "Il file non rispetta una versione di schema supportata: "
            f"{version!r} (supportate: {expected})."
        )
    return version


def validate_seed(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Valida il testo contro lo schema e restituisce il payload con i Decimal.

    Solleva SeedValidationError elencando tutti i problemi trovati, non solo il primo:
    chi corregge il file vuole vedere l'elenco completo.
    """
    try:
        for_validation = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SeedValidationError(f"JSON non valido: {exc}") from exc

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    problems = [
        f"{'/'.join(str(part) for part in error.absolute_path) or '(radice)'}: {error.message}"
        for error in sorted(validator.iter_errors(for_validation), key=lambda e: list(e.path))
    ]
    if problems:
        raise SeedValidationError(
            f"Il file non rispetta seed_schema_v1.json ({len(problems)} problemi).", problems
        )

    payload = parse_seed(text)
    version = payload.get("meta", {}).get("schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise SeedValidationError(
            f"Versione di schema non supportata: {version!r} "
            f"(attesa {SUPPORTED_SCHEMA_VERSION!r})."
        )
    return payload


def validate_seed_file(path: str | Path, schema_path: str | Path) -> dict[str, Any]:
    return validate_seed(
        Path(path).read_text(encoding="utf-8"),
        load_schema(schema_path),
    )


def validate_seed_auto(text: str, schema_paths: dict[str, str | Path]) -> dict[str, Any]:
    version = detect_schema_version(text)
    schema = load_schema(schema_paths[version])
    try:
        for_validation = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SeedValidationError(f"JSON non valido: {exc}") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    problems = [
        f"{'/'.join(str(part) for part in error.absolute_path) or '(radice)'}: {error.message}"
        for error in sorted(
            validator.iter_errors(for_validation), key=lambda error: list(error.path)
        )
    ]
    if problems:
        raise SeedValidationError(
            f"Il file non rispetta lo schema seed {version} ({len(problems)} problemi).",
            problems,
        )
    if version in {"2.0.0", "3.0.0"}:
        v1_validator = Draft202012Validator(
            load_schema(schema_paths["1.0.0"]), format_checker=FormatChecker()
        )
        projection = for_validation.get("application", {}).get("seed_v1", {})
        projection_problems = [
            "application/seed_v1/"
            f"{'/'.join(str(part) for part in error.absolute_path) or '(radice)'}: "
            f"{error.message}"
            for error in sorted(
                v1_validator.iter_errors(projection), key=lambda error: list(error.path)
            )
        ]
        if projection_problems:
            raise SeedValidationError(
                f"La proiezione applicativa del seed {version} non è valida "
                f"({len(projection_problems)} problemi).",
                projection_problems,
            )
    return parse_seed(text)
