"""Normalizzazione dei nomi di persona provenienti da Excel e PPM.

Regole conservative: si invertono solo i nomi in forma "Cognome Nome" riconoscibili
(due token), si compattano gli spazi e si uniforma il maiuscolo. I nomi parziali (un solo
token) non vengono mai risolti automaticamente: tornano come candidati per la coda di
revisione, dove un utente conferma.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SPACES = re.compile(r"\s+")


def strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )


def comparison_key(value: str) -> str:
    """Chiave di confronto: senza accenti, minuscola, spazi compattati, token ordinati.

    I token sono ordinati così che "Ravagli Andrea" e "Andrea Ravagli" collidano.
    """
    cleaned = _SPACES.sub(" ", strip_accents(value or "")).strip().lower()
    return " ".join(sorted(cleaned.split(" ")))


def titlecase_name(value: str) -> str:
    def fix(token: str) -> str:
        if not token:
            return token
        if "-" in token:
            return "-".join(fix(part) for part in token.split("-"))
        if token.lower() in {"de", "di", "da", "del", "della", "van", "von", "la", "lo"}:
            return token.lower()
        return token[:1].upper() + token[1:].lower()

    return " ".join(fix(token) for token in _SPACES.sub(" ", value or "").strip().split(" "))


@dataclass(frozen=True)
class NameCandidate:
    """Risultato della normalizzazione di un nome grezzo."""

    raw: str
    normalized: str
    needs_review: bool
    reason: str = ""

    @property
    def key(self) -> str:
        return comparison_key(self.normalized)


def normalize_person_name(raw: str) -> NameCandidate:
    value = _SPACES.sub(" ", (raw or "").strip())
    if not value:
        return NameCandidate(raw, "", True, "Nome vuoto.")
    tokens = value.split(" ")
    normalized = titlecase_name(value)
    if len(tokens) == 1:
        return NameCandidate(
            raw,
            normalized,
            True,
            "Nome parziale: serve conferma per associarlo a una persona esistente.",
        )
    return NameCandidate(raw, normalized, False)
