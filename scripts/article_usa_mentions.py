"""Write a per-article CSV: id, date, whether it mentions the USA, and which entities.

Columns: article_id, date, title, mentions_usa (True/False), entities (``;``-separated
entity names, empty if none), total_mentions.

Usage: uv run python scripts/article_usa_mentions.py
"""

import argparse
import csv
from pathlib import Path

from usa_mentions import count_mentions, iter_articles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--out", type=Path, default=Path("data/processed/usa_mentions_articles.csv")
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = hits = 0
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["article_id", "date", "title", "mentions_usa", "entities", "total_mentions"]
        )
        for art in iter_articles(args.raw_dir):
            counts = count_mentions(art["title"], art["text"])
            n += 1
            hits += bool(counts)
            writer.writerow(
                [
                    art["id"],
                    art["date"],
                    art["title"],
                    bool(counts),
                    ";".join(counts),
                    sum(counts.values()),
                ]
            )
    print(f"Wrote {n} articles ({hits} mention the USA) to {args.out}")


if __name__ == "__main__":
    main()
