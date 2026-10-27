"""Verifica che il seed lossless corrisponda ancora al workbook sorgente."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from export_full_workbook_seed import (
    DEFAULT_OUTPUT,
    DEFAULT_SCHEMA,
    DEFAULT_SOURCE,
    build_seed,
    validate_seed,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--seed", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()

    actual = json.loads(args.seed.resolve().read_text(encoding="utf-8"))
    validate_seed(actual, args.schema.resolve())
    expected = build_seed(args.source.resolve())
    expected["meta"]["generated_at"] = actual["meta"]["generated_at"]
    if actual != expected:
        raise ValueError("Il seed non corrisponde integralmente al workbook sorgente")
    print(
        json.dumps(
            {
                "verified": True,
                "source": str(args.source.resolve()),
                "seed": str(args.seed.resolve()),
                **actual["audit"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
