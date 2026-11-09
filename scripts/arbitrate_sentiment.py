"""Third pass: settle the articles where the reviewer disagreed with the first score.

For each article the reviewer (review_sentiment.py) disagreed on, an arbiter model sees the excerpt,
both scores and both reasonings, and gives the final score, whether it sided with the first
annotator, the reviewer or neither, and why. Articles the reviewer agreed on keep their score.

Outputs:
  data/processed/sentiment_arbitrations.jsonl   one line per arbitration (resumable)
  data/processed/sentiment_final.csv            every article: first_score, reviewer_score, final_score, source
  data/processed/sentiment_final_monthly.csv    same columns as sentiment_monthly.csv, from the final scores
sentiment_final.csv `source` is: first_agreed (reviewer agreed), arbitrated, or first_unreviewed
(no usable review yet, first score kept).

The arbiter is the server you point it at; for independence use a model different from the first
scorer and, ideally, from the reviewer (--base-url / --model, see deploy/serve_vllm.sh).

Examples:
  uv run python scripts/arbitrate_sentiment.py --limit 20
  uv run python scripts/arbitrate_sentiment.py
  uv run python scripts/arbitrate_sentiment.py --summary-only
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from sentiment_common import SCHEMA_ARBITER, build_arbiter_messages
from score_sentiment import chat_json, ensure_trailing_newline, read_jsonl


def arbitrate_one(art: dict, first: dict, rev: dict, a: argparse.Namespace) -> dict:
    out = {"id": art["id"], "date": art["date"], "first_score": first["score"],
           "reviewer_score": rev["revised_score"], "arbiter": a.model}
    parsed, resp, err = chat_json(
        a, build_arbiter_messages(art["title"], art["excerpt"], first["score"], first.get("reason", ""),
                                  rev["revised_score"], rev.get("explanation", "")),
        SCHEMA_ARBITER, a.max_tokens, name="arbitration")
    if parsed is None:
        return {**out, "final_score": None, "error": err}
    try:
        final = int(parsed["final_score"])
        if not 1 <= final <= 5:
            raise ValueError(f"final_score out of range: {final}")
    except (KeyError, TypeError, ValueError) as e:
        return {**out, "final_score": None, "error": f"{type(e).__name__}: {e}"}
    # Derive the decision from the numbers so it cannot contradict the score
    decision = "first" if final == first["score"] else "second" if final == rev["revised_score"] else "neither"
    return {**out, "final_score": final, "decision": decision, "explanation": str(parsed.get("explanation", ""))}


def summarise(a: argparse.Namespace) -> None:
    firsts = {r["id"]: r for r in read_jsonl(a.scores) if r.get("score") is not None}
    if not firsts:
        print("No scores yet.")
        return
    reviews = {r["id"]: r for r in read_jsonl(a.reviews) if r.get("agree") is not None}
    arbs = {r["id"]: r for r in read_jsonl(a.out) if r.get("final_score") is not None}

    rows = []
    for i, f in sorted(firsts.items()):
        rev, arb = reviews.get(i), arbs.get(i)
        if rev is None:
            src, final, rscore = "first_unreviewed", f["score"], None
        elif rev["agree"]:
            src, final, rscore = "first_agreed", f["score"], rev["revised_score"]
        elif arb is not None:
            src, final, rscore = "arbitrated", arb["final_score"], rev["revised_score"]
        else:
            src, final, rscore = "first_unreviewed", f["score"], rev["revised_score"]  # disagreement not yet arbitrated
        rows.append({"article_id": i, "date": f["date"], "first_score": f["score"], "reviewer_score": rscore,
                     "final_score": final, "source": src,
                     "decision": arb["decision"] if src == "arbitrated" else "",
                     "arbiter_explanation": arb["explanation"] if src == "arbitrated" else ""})
    df = pd.DataFrame(rows)
    df["reviewer_score"] = df["reviewer_score"].astype("Int64")  # integers, blank when unreviewed
    df.to_csv(a.csv_out, index=False)
    df["month"] = df["date"].str[:7]
    df.groupby("month").agg(
        articles_scored=("final_score", "size"),
        mean_sentiment=("final_score", "mean"),
        share_negative=("final_score", lambda s: (s <= 2).mean()),
        share_positive=("final_score", lambda s: (s >= 4).mean()),
    ).round(4).to_csv(a.monthly_out)

    print(f"Wrote {a.csv_out} and {a.monthly_out} ({len(df)} articles)")
    print(df["source"].value_counts().to_string())
    pending = ((df["source"] == "first_unreviewed") & df["reviewer_score"].notna()).sum()
    if pending:
        print(f"  ({pending} disagreements not arbitrated yet: re-run to continue)")
    arb_df = df[df["source"] == "arbitrated"]
    if len(arb_df):
        print("Arbiter sided with: " + ", ".join(f"{k} {v}" for k, v in arb_df["decision"].value_counts().items()))
        print(f"Mean score over all articles: first {df['first_score'].mean():.2f} -> final {df['final_score'].mean():.2f}; "
              f"{(df['final_score'] != df['first_score']).mean():.1%} of articles changed score")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    p.add_argument("--model", default="qwen", help="arbiter model name the server expects")
    p.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "EMPTY")
    p.add_argument("--concurrency", type=int, default=64)
    p.add_argument("--limit", type=int, help="arbitrate only the first N pending articles (smoke test)")
    p.add_argument("--max-tokens", type=int, default=150)
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--extra-body", type=json.loads, default={}, help="JSON merged into each request body")
    p.add_argument("--inputs", type=Path, default=Path("data/processed/sentiment_inputs.jsonl"))
    p.add_argument("--scores", type=Path, default=Path("data/processed/sentiment_scores.jsonl"))
    p.add_argument("--reviews", type=Path, default=Path("data/processed/sentiment_reviews.jsonl"))
    p.add_argument("--out", type=Path, default=Path("data/processed/sentiment_arbitrations.jsonl"))
    p.add_argument("--csv-out", type=Path, default=Path("data/processed/sentiment_final.csv"))
    p.add_argument("--monthly-out", type=Path, default=Path("data/processed/sentiment_final_monthly.csv"))
    p.add_argument("--summary-only", action="store_true")
    a = p.parse_args()

    if a.summary_only:
        summarise(a)
        return
    if not a.reviews.exists():
        raise SystemExit(f"{a.reviews} not found: run scripts/review_sentiment.py first")

    articles = {x["id"]: x for x in read_jsonl(a.inputs)}
    firsts = {r["id"]: r for r in read_jsonl(a.scores) if r.get("score") is not None}
    disputed = {r["id"]: r for r in read_jsonl(a.reviews) if r.get("agree") is False}
    done = {r["id"] for r in read_jsonl(a.out) if r.get("final_score") is not None}
    todo = [(articles[i], firsts[i], r) for i, r in sorted(disputed.items())
            if i in articles and i in firsts and i not in done]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(disputed)} disagreements, {len(done)} already arbitrated, {len(todo)} to do "
          f"(arbiter {a.model} at {a.base_url}, {a.concurrency} concurrent)")

    if todo:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        ensure_trailing_newline(a.out)
        t0, n_ok, n_fail, interrupted = time.perf_counter(), 0, 0, False
        pool = ThreadPoolExecutor(a.concurrency)
        futures = [pool.submit(arbitrate_one, art, f, r, a) for art, f, r in todo]
        try:
            with a.out.open("a", encoding="utf-8") as f:
                for i, fut in enumerate(as_completed(futures), 1):
                    res = fut.result()
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                    f.flush()
                    n_ok += res["final_score"] is not None
                    n_fail += res["final_score"] is None
                    if res["final_score"] is None and n_fail <= 3:
                        print(f"  failed {res['id']}: {res.get('error')}")
                    if i % 200 == 0 or i == len(todo):
                        rate = i / (time.perf_counter() - t0)
                        print(f"  {i}/{len(todo)}  {rate:.1f} articles/s  ETA {(len(todo) - i) / rate / 60:.1f} min  ({n_fail} failed)")
        except KeyboardInterrupt:
            interrupted = True
            print("\nInterrupted: dropping queued requests ...")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        if interrupted:
            summarise(a)
            print("Re-run the same command to continue where it stopped.")
            raise SystemExit(130)
        if n_fail and n_ok == 0:
            raise SystemExit("Every request failed: is the server running? (deploy/serve_vllm.sh status)")

    summarise(a)


if __name__ == "__main__":
    main()
