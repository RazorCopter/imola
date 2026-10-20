"""Blocca il commit dei dati reali del fornitore.

Il seed (data/seed/*.json) contiene progetti, budget e nomi di persone: resta su disco e
fuori da git. Nel repository stanno solo lo schema JSON e le fixture demo anonimizzate.
"""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN_DIRS = ("data/seed",)
ALLOWED_NAMES = {".gitkeep", "seed_schema_v1.json"}


def main(paths: list[str]) -> int:
    offenders = []
    for raw in paths:
        path = Path(raw.replace("\\", "/"))
        posix = path.as_posix()
        if any(posix.startswith(folder) for folder in FORBIDDEN_DIRS):
            if path.name not in ALLOWED_NAMES:
                offenders.append(posix)

    if offenders:
        print("Questi file contengono dati reali e non vanno versionati:")
        for offender in offenders:
            print(f"  - {offender}")
        print("Sono esclusi da .gitignore: rimuovili dall'indice con `git rm --cached`.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
