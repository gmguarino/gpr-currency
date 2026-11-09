"""Build a self-contained HTML dashboard from the monthly USA-mentions CSV (and sentiment CSV, if present).

Embeds the CSV data and reference/sanctions_events.csv into scripts/dashboard_template.html (no external libraries or
network access needed) and writes docs/usa_mentions_dashboard.html.

Usage: uv run python scripts/build_dashboard.py
"""

import argparse
import json
from pathlib import Path

import pandas as pd

TEMPLATE = Path(__file__).with_name("dashboard_template.html")
EVENTS_CSV = Path("reference/sanctions_events.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--csv", type=Path, default=Path("data/processed/usa_mentions_monthly.csv")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("docs/usa_mentions_dashboard.html")
    )
    parser.add_argument(
        "--sentiment", type=Path, default=None,
        help="monthly sentiment CSV; default: sentiment_final_monthly.csv if it exists (after the review and "
        "arbitration passes), else sentiment_monthly.csv; skipped if neither exists",
    )
    parser.add_argument(
        "--weekly", type=Path, default=Path("data/processed/usa_mentions_weekly.csv"),
        help="weekly CSV from weekly_aggregates.py; enables the Monthly/Weekly toggle; skipped if missing",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.csv).sort_values("month")
    sent_cols = ["mean_sentiment", "share_negative", "share_positive"]
    sentiment = args.sentiment
    if sentiment is None:
        final, first = Path("data/processed/sentiment_final_monthly.csv"), Path("data/processed/sentiment_monthly.csv")
        sentiment = final if final.exists() else first
    if sentiment.exists():
        df = df.merge(pd.read_csv(sentiment), on="month", how="left")
        # months with no scored article: zero weight, neutral placeholder values
        df["articles_scored"] = df["articles_scored"].fillna(0).astype(int)
        df[sent_cols] = df[sent_cols].fillna(0)
        print(f"Added sentiment from {sentiment} for {int((df['articles_scored'] > 0).sum())} months")
    weekly = "null"
    if args.weekly.exists():
        wk = pd.read_csv(args.weekly).sort_values("week_start")
        if "mean_sentiment" in wk.columns:
            wk["articles_scored"] = wk["articles_scored"].fillna(0).astype(int)
            wk[sent_cols] = wk[sent_cols].fillna(0)
        weekly = json.dumps(wk.to_dict(orient="list"), ensure_ascii=False)
        print(f"Added {len(wk)} weeks (Monthly/Weekly toggle enabled)")
    data = json.dumps(df.to_dict(orient="list"), ensure_ascii=False)
    events = pd.read_csv(EVENTS_CSV).sort_values("date").to_dict(orient="records")
    html = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("__DATA__", data)
        .replace("__WEEKLY__", weekly)
        .replace("__EVENTS__", json.dumps(events, ensure_ascii=False))
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"Wrote {args.out} ({len(df)} months)")


if __name__ == "__main__":
    main()
