"""Build a self-contained HTML dashboard from the monthly USA-mentions CSV.

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
    args = parser.parse_args()

    df = pd.read_csv(args.csv).sort_values("month")
    data = json.dumps(df.to_dict(orient="list"), ensure_ascii=False)
    events = pd.read_csv(EVENTS_CSV).sort_values("date").to_dict(orient="records")
    html = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("__DATA__", data)
        .replace("__EVENTS__", json.dumps(events, ensure_ascii=False))
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"Wrote {args.out} ({len(df)} months)")


if __name__ == "__main__":
    main()
