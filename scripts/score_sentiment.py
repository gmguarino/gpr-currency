"""Score the sentiment towards the USA (1-5) of every USA-mentioning article, in batches.

Sends each article's excerpt (from before the first to after the last entity mention, see
usa_mentions.mention_window) to an OpenAI-compatible chat server such as the vLLM server
started by deploy/serve_vllm.sh. Many requests are kept in flight at once, so vLLM batches
them. 1 = completely negative, 5 = completely positive.

Stages (each is skipped if its output already exists):
  1. build the inputs   data/raw/*.jsonl.gz  ->  data/processed/sentiment_inputs.jsonl
  2. score them         -> data/processed/sentiment_scores.jsonl   (resumable: re-run to continue)
  3. summarise          -> data/processed/sentiment_scores.csv and sentiment_monthly.csv

Examples:
  uv run python scripts/score_sentiment.py --limit 20            # smoke test on 20 articles
  uv run python scripts/score_sentiment.py                       # everything, vLLM on localhost:8000
  uv run python scripts/score_sentiment.py --no-reason           # score only: fewer output tokens
  uv run python scripts/score_sentiment.py --summary-only        # just rebuild the CSVs
  # against a local Ollama server instead of vLLM:
  # (Ollama ignores chat_template_kwargs, so switch thinking off with reasoning_effort)
  uv run python scripts/score_sentiment.py --base-url http://localhost:11434/v1 --model qwen3.5:4b \\
      --extra-body '{"reasoning_effort": "none"}' --concurrency 2 --limit 10
"""

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from sentiment_common import SCHEMA, SCHEMA_SCORE_ONLY, build_messages
from usa_mentions import count_mentions, iter_articles, mention_window


def build_inputs(raw_dir: Path, out: Path, context: int, max_chars: int) -> None:
    """One line per USA-mentioning article: id, date, title, excerpt."""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    tmp = out.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for art in iter_articles(raw_dir):
            if not count_mentions(art["title"], art["text"]):
                continue
            row = {
                "id": art["id"], "date": art["date"], "title": art["title"],
                "excerpt": mention_window(art["text"], context, max_chars),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    tmp.replace(out)
    print(f"Wrote {n} articles to {out}")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_one(art: dict, a: argparse.Namespace) -> dict:
    schema = SCHEMA if a.reason else SCHEMA_SCORE_ONLY
    body = {
        "model": a.model,
        "messages": build_messages(art["title"], art["excerpt"], a.reason),
        "temperature": 0,
        "max_tokens": a.max_tokens,
        "response_format": {"type": "json_schema", "json_schema": {"name": "sentiment", "strict": True, "schema": schema}},
        "chat_template_kwargs": {"enable_thinking": False},
        **a.extra_body,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {a.api_key}"}
    req_url = a.base_url.rstrip("/") + "/chat/completions"
    last_err = ""
    for attempt in range(a.retries):
        try:
            req = urllib.request.Request(req_url, json.dumps(body).encode(), headers)
            with urllib.request.urlopen(req, timeout=a.timeout) as r:
                resp = json.load(r)
            content = resp["choices"][0]["message"]["content"] or ""
            parsed = json.loads(content)
            score = int(parsed["score"])
            if not 1 <= score <= 5:
                raise ValueError(f"score out of range: {score}")
            return {"id": art["id"], "date": art["date"], "score": score,
                    "reason": str(parsed.get("reason", "")), "model": a.model,
                    "tokens_in": resp.get("usage", {}).get("prompt_tokens"),
                    "tokens_out": resp.get("usage", {}).get("completion_tokens")}
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read()[:200]!r}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, KeyError, TypeError) as e:
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(2 ** attempt)
    return {"id": art["id"], "date": art["date"], "score": None, "reason": "", "model": a.model, "error": last_err}


def summarise(scores_path: Path, csv_out: Path, monthly_out: Path) -> None:
    rows = read_jsonl(scores_path)
    if not rows:
        print("No scores yet.")
        return
    df = pd.DataFrame(rows).drop_duplicates("id", keep="last")  # latest attempt per article wins
    done = df[df["score"].notna()].copy()
    done["score"] = done["score"].astype(int)
    done = done.sort_values("id")
    done[["id", "date", "score", "reason"]].rename(
        columns={"id": "article_id", "score": "sentiment_score"}).to_csv(csv_out, index=False)
    done["month"] = done["date"].str[:7]
    monthly = done.groupby("month").agg(
        articles_scored=("score", "size"),
        mean_sentiment=("score", "mean"),
        share_negative=("score", lambda s: (s <= 2).mean()),
        share_positive=("score", lambda s: (s >= 4).mean()),
    ).round(4)
    monthly.to_csv(monthly_out)
    failed = len(df) - len(done)
    print(f"Summary: {len(done)} scored, {failed} failed (re-run to retry). "
          f"Mean score {done['score'].mean():.2f}. Wrote {csv_out} and {monthly_out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    p.add_argument("--model", default="qwen", help="model name the server expects (vLLM: SERVED_MODEL_NAME)")
    p.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "EMPTY")
    p.add_argument("--concurrency", type=int, default=64, help="requests in flight (vLLM batches them)")
    p.add_argument("--limit", type=int, help="score only the first N unscored articles (smoke test)")
    p.add_argument("--no-reason", dest="reason", action="store_false", help="ask for the score only")
    p.add_argument("--max-tokens", type=int, default=None, help="default 120, or 20 with --no-reason")
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--extra-body", type=json.loads, default={}, help="JSON merged into each request body")
    p.add_argument("--context", type=int, default=1, help="sentences kept around the mentions")
    p.add_argument("--max-chars", type=int, default=2000, help="cap on the excerpt length")
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--inputs", type=Path, default=Path("data/processed/sentiment_inputs.jsonl"))
    p.add_argument("--out", type=Path, default=Path("data/processed/sentiment_scores.jsonl"))
    p.add_argument("--csv-out", type=Path, default=Path("data/processed/sentiment_scores.csv"))
    p.add_argument("--monthly-out", type=Path, default=Path("data/processed/sentiment_monthly.csv"))
    p.add_argument("--rebuild-inputs", action="store_true")
    p.add_argument("--summary-only", action="store_true")
    a = p.parse_args()
    if a.max_tokens is None:
        a.max_tokens = 120 if a.reason else 20

    if a.summary_only:
        summarise(a.out, a.csv_out, a.monthly_out)
        return

    if a.rebuild_inputs or not a.inputs.exists():
        build_inputs(a.raw_dir, a.inputs, a.context, a.max_chars)
    articles = read_jsonl(a.inputs)
    done = {r["id"] for r in read_jsonl(a.out) if r.get("score") is not None}
    todo = [x for x in articles if x["id"] not in done]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(articles)} articles, {len(done)} already scored, {len(todo)} to do "
          f"(model {a.model} at {a.base_url}, {a.concurrency} concurrent)")

    if todo:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        t0, n_ok, n_fail, lock = time.perf_counter(), 0, 0, threading.Lock()
        with a.out.open("a", encoding="utf-8") as f, ThreadPoolExecutor(a.concurrency) as pool:
            futures = [pool.submit(score_one, art, a) for art in todo]
            for i, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                with lock:
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                    if i % 50 == 0:
                        f.flush()
                n_ok += res["score"] is not None
                n_fail += res["score"] is None
                if n_fail and res["score"] is None and n_fail <= 3:
                    print(f"  failed {res['id']}: {res.get('error')}")
                if i % 200 == 0 or i == len(todo):
                    rate = i / (time.perf_counter() - t0)
                    print(f"  {i}/{len(todo)}  {rate:.1f} articles/s  ETA {(len(todo) - i) / rate / 60:.1f} min  ({n_fail} failed)")
            f.flush()
        if n_fail and n_ok == 0:
            raise SystemExit("Every request failed: is the server running? (deploy/serve_vllm.sh status)")

    summarise(a.out, a.csv_out, a.monthly_out)


if __name__ == "__main__":
    main()
