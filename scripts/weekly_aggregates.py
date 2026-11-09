"""Aggregate mentions and sentiment by week from existing per-article CSVs (nothing is recomputed).

Reads data/processed/usa_mentions_articles.csv (every article, with its matched entities) and the
per-article sentiment scores, and writes data/processed/usa_mentions_weekly.csv: one row per week
(weeks start on Monday; `week_start` is that Monday). Takes seconds, no model or raw data needed.

Sentiment source (--sentiment): `auto` uses sentiment_final.csv (after the review and arbitration
passes) if it exists, otherwise sentiment_scores.csv (first pass). `none` skips sentiment.

Columns: week_start, articles_total, articles_any_usa, share_any_usa, articles_<entity>
(per entity, article counts), share_alias_mentions (USA-alias articles / total), total_mentions
(all entities; raw per-entity mentions exist only in the monthly file), and, with sentiment,
articles_scored, mean_sentiment, share_negative (<=2), share_positive (>=4).

Usage: uv run python scripts/weekly_aggregates.py [--sentiment auto|first|final|none]
"""

import argparse
from pathlib import Path

import pandas as pd

from usa_mentions import ENTITIES

PROC = Path("data/processed")


def week_start(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates)
    return (d - pd.to_timedelta(d.dt.day_of_week, unit="D")).dt.strftime("%Y-%m-%d")


def sentiment_weekly(a: argparse.Namespace) -> pd.DataFrame | None:
    final, first = PROC / "sentiment_final.csv", PROC / "sentiment_scores.csv"
    if a.sentiment == "none":
        return None
    use_final = a.sentiment == "final" or (a.sentiment == "auto" and final.exists())
    path, col = (final, "final_score") if use_final else (first, "sentiment_score")
    if not path.exists():
        print(f"No sentiment file at {path}: skipping sentiment")
        return None
    s = pd.read_csv(path, usecols=["date", col]).dropna(subset=[col])
    s["week_start"] = week_start(s["date"])
    print(f"Sentiment from {path} ({len(s)} articles)")
    return s.groupby("week_start")[col].agg(
        articles_scored="size",
        mean_sentiment="mean",
        share_negative=lambda x: (x <= 2).mean(),
        share_positive=lambda x: (x >= 4).mean(),
    ).round(4)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--articles", type=Path, default=PROC / "usa_mentions_articles.csv")
    p.add_argument("--sentiment", choices=["auto", "first", "final", "none"], default="auto")
    p.add_argument("--out", type=Path, default=PROC / "usa_mentions_weekly.csv")
    a = p.parse_args()

    df = pd.read_csv(a.articles, usecols=["date", "mentions_usa", "entities", "total_mentions"])
    df["week_start"] = week_start(df["date"])
    ents = df["entities"].fillna("").str.split(";")
    for e in ENTITIES:
        df[f"articles_{e}"] = ents.map(lambda x, e=e: e in x)
    g = df.groupby("week_start")
    out = pd.DataFrame({
        "articles_total": g.size(),
        "articles_any_usa": g["mentions_usa"].sum(),
    })
    out["share_any_usa"] = (out["articles_any_usa"] / out["articles_total"]).round(4)
    out["share_alias_mentions"] = (g["articles_usa"].sum() / out["articles_total"]).round(4)
    for e in ENTITIES:
        out[f"articles_{e}"] = g[f"articles_{e}"].sum()
    out["total_mentions"] = g["total_mentions"].sum()
    sent = sentiment_weekly(a)
    if sent is not None:
        out = out.join(sent)
    out.index.name = "week_start"
    out.to_csv(a.out)
    print(f"Wrote {a.out} ({len(out)} weeks, {out.index.min()} to {out.index.max()})")
    if sent is not None:
        print(f"Scored articles per week: median {int(out['articles_scored'].median())}, "
              f"min {int(out['articles_scored'].min())} (weekly sentiment is noisier than monthly)")


if __name__ == "__main__":
    main()
