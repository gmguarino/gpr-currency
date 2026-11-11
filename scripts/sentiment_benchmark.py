"""Benchmark local Ollama models on scoring the view of the USA (1-5, see sentiment_common.SCALE) and relevance.

Each article is cut to an excerpt running from before its first entity mention to after its
last (see usa_mentions.mention_window). Draws a reproducible random sample of articles that mention the USA, asks each model for a
1-5 score (1 = hostile, 5 = very favourable) plus a short reason, and
reports latency, token throughput, a projection for the full corpus, and how much the
models agree with each other. Raw results go to data/processed/sentiment_benchmark.jsonl.

Requires the article CSV (scripts/article_usa_mentions.py) and the raw data
(scripts/download_data.py), and a running Ollama server with the models pulled.

Usage: uv run python scripts/sentiment_benchmark.py [-n 30] [--models qwen3.5:9b qwen3.5:4b]
"""

import argparse
import json
import random
import statistics
import time
import urllib.request
from pathlib import Path

import pandas as pd

from sentiment_common import SCHEMA, build_messages
from usa_mentions import iter_articles, mention_window

OLLAMA = "http://localhost:11434/api/chat"
DEFAULT_MODELS = ["qwen3.5:9b", "qwen3.5:9b-mlx", "qwen3.5:4b"]

def load_sample(raw_dir: Path, articles_csv: Path, n: int, seed: int, cache: Path) -> list[dict]:
    if cache.exists():
        rows = [json.loads(line) for line in cache.read_text(encoding="utf-8").splitlines()]
        if len(rows) >= n:
            return rows[:n]
    df = pd.read_csv(articles_csv, keep_default_na=False)
    ids = df.loc[df["mentions_usa"].astype(str) == "True", "article_id"].tolist()
    chosen = set(random.Random(seed).sample(ids, n))
    found = {a["id"]: a for a in iter_articles(raw_dir) if a["id"] in chosen}
    rows = [found[i] for i in sorted(chosen)]
    random.Random(seed).shuffle(rows)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return rows


def ask(model: str, article: dict, max_chars: int, num_ctx: int, context: int) -> dict:
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_ctx": num_ctx},
        "messages": build_messages(article["title"], mention_window(article["text"], context, max_chars)),
    }
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.load(r)
    wall = time.perf_counter() - t0
    try:
        parsed = json.loads(resp["message"]["content"])
        score, reason = int(parsed["score"]), str(parsed["reason"])
    except (ValueError, KeyError, TypeError):
        score, reason = None, resp["message"]["content"][:200]
    return {
        "model": model, "id": article["id"], "score": score, "reason": reason, "wall_s": wall,
        "prompt_tokens": resp.get("prompt_eval_count", 0), "gen_tokens": resp.get("eval_count", 0),
        "prompt_s": resp.get("prompt_eval_duration", 0) / 1e9, "gen_s": resp.get("eval_duration", 0) / 1e9,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", type=int, default=30, help="number of sample articles")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--max-chars", type=int, default=2000, help="cap on the excerpt length")
    parser.add_argument("--context", type=int, default=1,
                        help="extra sentences kept before the first and after the last mention")
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--articles-csv", type=Path, default=Path("data/processed/usa_mentions_articles.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/processed/sentiment_benchmark.jsonl"))
    args = parser.parse_args()

    sample = load_sample(args.raw_dir, args.articles_csv, args.n, args.seed,
                         args.out.with_name("sentiment_sample.jsonl"))
    total_articles = int((pd.read_csv(args.articles_csv, usecols=["mentions_usa"]).mentions_usa).sum())
    excerpts = [mention_window(a["text"], args.context, args.max_chars) for a in sample]
    print(f"{len(sample)} articles, mean {statistics.mean(len(a['text']) for a in sample):.0f} chars; "
          f"excerpt around the mentions (+{args.context} sentence context, cap {args.max_chars}): "
          f"mean {statistics.mean(map(len, excerpts)):.0f} chars; "
          f"corpus has {total_articles} USA-mentioning articles\n")

    results: list[dict] = []
    for model in args.models:
        print(f"== {model}")
        try:
            ask(model, sample[0], args.max_chars, args.num_ctx, args.context)  # warm-up: load weights
        except Exception as e:  # noqa: BLE001
            print(f"   skipped: {e}\n")
            continue
        rows = [ask(model, a, args.max_chars, args.num_ctx, args.context) for a in sample]
        results += rows
        wall = statistics.mean(r["wall_s"] for r in rows)
        p_tps = sum(r["prompt_tokens"] for r in rows) / max(sum(r["prompt_s"] for r in rows), 1e-9)
        g_tps = sum(r["gen_tokens"] for r in rows) / max(sum(r["gen_s"] for r in rows), 1e-9)
        bad = sum(r["score"] is None for r in rows)
        print(f"   {wall:.2f} s/article | prompt {p_tps:.0f} tok/s | generate {g_tps:.0f} tok/s | "
              f"avg {statistics.mean(r['prompt_tokens'] for r in rows):.0f} in / "
              f"{statistics.mean(r['gen_tokens'] for r in rows):.0f} out tokens | unparsable {bad}")
        print(f"   projected full corpus: {wall * total_articles / 3600:.1f} h\n")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in results), encoding="utf-8")

    df = pd.DataFrame(results)
    if df.empty:
        return
    wide = df.pivot(index="id", columns="model", values="score")
    print("Score distribution per model:")
    print(wide.apply(lambda c: c.value_counts().sort_index()).fillna(0).astype(int).to_string(), "\n")
    if wide.shape[1] > 1:
        print("Mean absolute difference between models (1-5 scale):")
        cols = list(wide.columns)
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                pair = wide[[a, b]].dropna()
                print(f"   {a} vs {b}: {(pair[a] - pair[b]).abs().mean():.2f} "
                      f"(exact match {(pair[a] == pair[b]).mean():.0%})")
    print(f"\nRaw results: {args.out}")


if __name__ == "__main__":
    main()
