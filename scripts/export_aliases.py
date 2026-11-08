"""Export the entity alias dictionary with English translations to docs/entity_aliases.csv.

Columns: entity, pattern (regex used for matching), english. Meant for English-speaking
researchers who need to read what each Chinese alias means.

Usage: uv run python scripts/export_aliases.py
"""

import argparse
import csv
from pathlib import Path

from usa_mentions import ALIASES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("docs/entity_aliases.csv"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["entity", "pattern", "english"])
        for entity, aliases in ALIASES.items():
            for pattern, english in aliases:
                writer.writerow([entity, pattern, english])
    print(f"Wrote {sum(map(len, ALIASES.values()))} aliases to {args.out}")


if __name__ == "__main__":
    main()
