"""Second pass: have a model audit each sentiment score and its reason (agree / disagree and why).

For every article scored by score_sentiment.py, a reviewer model sees the same excerpt plus the
first annotator's score and reason, and answers: does it agree, what score would it give, and why
(if it disagrees, what the first annotator got wrong). Resumable, like score_sentiment.py.

Outputs:
  data/processed/sentiment_reviews.jsonl   one line per review (resumable)
  data/processed/sentiment_reviews.csv     article_id, date, score, agree, revised_score, explanation, reason

The reviewer can be the same server (default) or a different one. A model reviewing its own output
tends to agree too readily, so for a more independent check serve a different or larger model with
deploy/serve_vllm.sh (MODEL=..., SERVED_MODEL_NAME=...) and pass --base-url / --model.

Examples:
  uv run python scripts/review_sentiment.py --limit 20            # smoke test
  uv run python scripts/review_sentiment.py                       # review everything
  uv run python scripts/review_sentiment.py --only-extreme        # only scores 1, 2, 4, 5 (skip the neutral 3s)
  uv run python scripts/review_sentiment.py --summary-only        # rebuild the CSV and the printed summary
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from sentiment_common import PROMPT_VERSION, SCHEMA_REVIEW, build_review_messages, same_verdict
from score_sentiment import chat_json, check_prompt_version, ensure_trailing_newline, read_jsonl


def review_one(art: dict, first: dict, a: argparse.Namespace) -> dict:
    first_rel = first.get("relevant", True)
    out = {"id": art["id"], "date": art["date"], "relevant": first_rel, "score": first["score"],
           "reason": first.get("reason", ""), "reviewer": a.model, "prompt": PROMPT_VERSION}
    parsed, resp, err = chat_json(
        a, build_review_messages(art["title"], art["excerpt"], first["score"], first.get("reason", ""), first_rel),
        SCHEMA_REVIEW, a.max_tokens, name="review")
    if parsed is None:
        return {**out, "agree": None, "error": err}
    try:
        revised = int(parsed["revised_score"])
        if not 1 <= revised <= 5:
            raise ValueError(f"revised_score out of range: {revised}")
        revised_rel = parsed["revised_relevant"]
        if not isinstance(revised_rel, bool):
            raise ValueError(f"revised_relevant is not a boolean: {revised_rel!r}")
    except (KeyError, TypeError, ValueError) as e:
        return {**out, "agree": None, "error": f"{type(e).__name__}: {e}"}
    # Decide from the verdicts themselves, so "agree" cannot contradict them (two "irrelevant" verdicts agree
    # whatever the scores; otherwise relevance and score must both match)
    agree = same_verdict(first_rel, first["score"], revised_rel, revised)
    return {**out, "agree": agree, "revised_relevant": revised_rel, "revised_score": revised,
            "explanation": str(parsed.get("explanation", ""))}


def summarise(path: Path, csv_out: Path) -> None:
    rows = read_jsonl(path)
    if not rows:
        print("No reviews yet.")
        return
    df = pd.DataFrame(rows).drop_duplicates("id", keep="last")
    done = df[df["agree"].notna()].copy()
    if done.empty:
        print("No successful reviews yet.")
        return
    done["agree"] = done["agree"].astype(bool)
    done["revised_score"] = done["revised_score"].astype(int)
    done["relevant"] = done["relevant"].fillna(True).astype(bool)
    done["revised_relevant"] = done["revised_relevant"].astype(bool)
    done = done.sort_values("id")
    done[["id", "date", "relevant", "score", "agree", "revised_relevant", "revised_score", "explanation", "reason"]].rename(
        columns={"id": "article_id"}).to_csv(csv_out, index=False)

    dis = done[~done["agree"]]
    print(f"Reviewed {len(done)} articles ({len(df) - len(done)} failed): "
          f"{done['agree'].mean():.1%} agree, {len(dis)} disagree. Wrote {csv_out}")
    flips = done[done["relevant"] != done["revised_relevant"]]
    print(f"Relevance: first pass says irrelevant for {int((~done['relevant']).sum())}, reviewer for "
          f"{int((~done['revised_relevant']).sum())}; they differ on {len(flips)}")
    print("Agreement by original score:")
    print(done.groupby("score")["agree"].agg(n="size", agree="mean").round(3).to_string())
    if len(dis):
        dis = dis[dis["relevant"] & dis["revised_relevant"]]  # score shifts only make sense when both say relevant
        d = (dis["revised_score"] - dis["score"])
        print(f"Disagreements: reviewer is more positive in {(d > 0).sum()}, more negative in {(d < 0).sum()}; "
              f"mean shift {d.mean():+.2f}; mean score {done['score'].mean():.2f} -> {done['revised_score'].mean():.2f}")
        print("Original -> revised (rows: original score, columns: revised score):")
        print(pd.crosstab(done["score"], done["revised_score"]).to_string())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    p.add_argument("--model", default="qwen", help="reviewer model name the server expects")
    p.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "EMPTY")
    p.add_argument("--concurrency", type=int, default=64)
    p.add_argument("--limit", type=int, help="review only the first N unreviewed articles (smoke test)")
    p.add_argument("--only-extreme", action="store_true", help="skip articles the first pass scored 3 (neutral)")
    p.add_argument("--max-tokens", type=int, default=150)
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--extra-body", type=json.loads, default={}, help="JSON merged into each request body")
    p.add_argument("--inputs", type=Path, default=Path("data/processed/sentiment_inputs.jsonl"))
    p.add_argument("--scores", type=Path, default=Path("data/processed/sentiment_scores.jsonl"))
    p.add_argument("--out", type=Path, default=Path("data/processed/sentiment_reviews.jsonl"))
    p.add_argument("--csv-out", type=Path, default=Path("data/processed/sentiment_reviews.csv"))
    p.add_argument("--summary-only", action="store_true")
    a = p.parse_args()

    if a.summary_only:
        summarise(a.out, a.csv_out)
        return

    if not a.scores.exists():
        raise SystemExit(f"{a.scores} not found: run scripts/score_sentiment.py first")
    articles = {x["id"]: x for x in read_jsonl(a.inputs)}
    scores = read_jsonl(a.scores)
    existing = read_jsonl(a.out)
    check_prompt_version(scores, a.scores)  # the scores being reviewed must come from the current prompt
    check_prompt_version(existing, a.out)
    firsts = {}
    for r in scores:
        if r.get("score") is not None:
            firsts[r["id"]] = r  # latest successful score per article
    done = {r["id"] for r in existing if r.get("agree") is not None}
    todo = [(articles[i], f) for i, f in sorted(firsts.items())
            if i in articles and i not in done and not (a.only_extreme and f["score"] == 3)]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(firsts)} scored articles, {len(done)} already reviewed, {len(todo)} to do "
          f"(reviewer {a.model} at {a.base_url}, {a.concurrency} concurrent)")

    if todo:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        ensure_trailing_newline(a.out)
        t0, n_ok, n_fail, interrupted = time.perf_counter(), 0, 0, False
        pool = ThreadPoolExecutor(a.concurrency)
        futures = [pool.submit(review_one, art, first, a) for art, first in todo]
        try:
            with a.out.open("a", encoding="utf-8") as f:
                for i, fut in enumerate(as_completed(futures), 1):
                    res = fut.result()
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                    f.flush()
                    n_ok += res["agree"] is not None
                    n_fail += res["agree"] is None
                    if res["agree"] is None and n_fail <= 3:
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
            summarise(a.out, a.csv_out)
            print("Re-run the same command to continue where it stopped.")
            raise SystemExit(130)
        if n_fail and n_ok == 0:
            raise SystemExit("Every request failed: is the server running? (deploy/serve_vllm.sh status)")

    summarise(a.out, a.csv_out)


if __name__ == "__main__":
    main()
