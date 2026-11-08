"""Download Papersnake/people_daily_news for 2010 onwards into data/raw/.

The dataset is published as one gzipped JSONL file per year (e.g. ``2010.jsonl.gz``),
so "2010 onwards" means downloading every yearly file with year >= START_YEAR.
Files that already exist locally are skipped.

Usage: uv run python scripts/download_data.py [--start-year 2010] [--out-dir data/raw]
"""

import argparse
import re
from pathlib import Path

from huggingface_hub import hf_hub_download, list_repo_files

REPO_ID = "Papersnake/people_daily_news"
YEAR_FILE = re.compile(r"^(\d{4})\.jsonl\.gz$")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=2010)
    parser.add_argument("--out-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    files = sorted(
        f
        for f in list_repo_files(REPO_ID, repo_type="dataset")
        if (m := YEAR_FILE.match(f)) and int(m.group(1)) >= args.start_year
    )
    if not files:
        raise SystemExit(f"No yearly files >= {args.start_year} found in {REPO_ID}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name in files:
        target = args.out_dir / name
        if target.exists():
            print(f"skip   {name} (already downloaded)")
            continue
        print(f"fetch  {name}")
        hf_hub_download(
            REPO_ID, name, repo_type="dataset", local_dir=args.out_dir
        )
    print(f"Done: {len(files)} files in {args.out_dir}")


if __name__ == "__main__":
    main()
