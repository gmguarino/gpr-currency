"""Count USA-related mentions in People's Daily per month.

Output (one row per month): total articles, articles mentioning the USA (any entity),
their share (``share_any_usa``), ``share_alias_mentions`` (articles mentioning at least
one USA alias, i.e. the ``usa`` entity, divided by total articles), and for every
entity both the number of articles mentioning it (``articles_<entity>``) and its raw
occurrence count (``mentions_<entity>``).

Usage: uv run python scripts/monthly_usa_mentions.py
"""

import argparse
from collections import defaultdict
from pathlib import Path

import pandas as pd

from usa_mentions import ENTITIES, count_mentions, iter_articles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--out", type=Path, default=Path("data/processed/usa_mentions_monthly.csv")
    )
    args = parser.parse_args()

    rows: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for art in iter_articles(args.raw_dir):
        row = rows[art["date"][:7]]
        row["articles_total"] += 1
        counts = count_mentions(art["title"], art["text"])
        if counts:
            row["articles_any_usa"] += 1
        for name, n in counts.items():
            row[f"articles_{name}"] += 1
            row[f"mentions_{name}"] += n

    columns = (
        ["articles_total", "articles_any_usa"]
        + [f"articles_{n}" for n in ENTITIES]
        + [f"mentions_{n}" for n in ENTITIES]
    )
    df = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=columns).fillna(0)
    df = df.astype(int).sort_index()
    df.insert(2, "share_any_usa", (df["articles_any_usa"] / df["articles_total"]).round(4))
    df.insert(
        3, "share_alias_mentions", (df["articles_usa"] / df["articles_total"]).round(4)
    )
    df.index.name = "month"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out)
    print(f"Wrote {len(df)} months to {args.out}")


if __name__ == "__main__":
    main()
