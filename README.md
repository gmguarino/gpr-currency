# gpr-currency

How often, and in what tone, does China's *People's Daily* (人民日报) talk about the United States? This repo downloads the newspaper's archive from 2010 onwards, counts mentions of the USA and related entities (presidents, Congress, the Fed, …) per month and per article, and presents the result in a self-contained HTML dashboard. A sentiment-scoring benchmark with local Qwen models is in progress.

## Contents

- [Requirements](#requirements)
- [Setup](#setup)
- [Quick start](#quick-start)
- [The scripts](#the-scripts)
- [Outputs](#outputs)
- [The dashboard](#the-dashboard)
- [The scoring scale](#the-scoring-scale)
- [Reviewing the scores with a second pass](#reviewing-the-scores-with-a-second-pass)
- [Arbitrating disagreements (third pass)](#arbitrating-disagreements-third-pass)
- [Customising](#customising)
- [Sentiment benchmark](#sentiment-benchmark)
- [Cloud GPU deployment (Scaleway)](#cloud-gpu-deployment-scaleway)
- [Scoring sentiment with a model server](#scoring-sentiment-with-a-model-server)
- [Repository layout](#repository-layout)
- [Troubleshooting](#troubleshooting)

## Requirements

- [uv](https://docs.astral.sh/uv/) (manages Python and dependencies; Python ≥ 3.11 is pinned in `.python-version`)
- About 1 GB of free disk space (the raw data is ~620 MB)
- Internet access for the first download (Hugging Face)
- For the sentiment benchmark only: [Ollama](https://ollama.com/) running locally

Never use `pip install`; always go through uv so `pyproject.toml` and `uv.lock` stay in sync.

## Setup

```bash
git clone git@github.com:gmguarino/gpr-currency.git
cd gpr-currency
uv sync            # creates .venv and installs dependencies
```

All commands below are run **from the repository root** with `uv run`.

## Quick start

Run these in order. Each step reads the previous step's output.

```bash
uv run python scripts/download_data.py          # 1. download 2010+ articles   (~620 MB, a few minutes)
uv run python scripts/monthly_usa_mentions.py   # 2. monthly counts            (~1.5 min)
uv run python scripts/article_usa_mentions.py   # 3. per-article flags         (~1.5 min)
uv run python scripts/export_aliases.py         # 4. alias glossary (EN/ZH)    (instant)
uv run python scripts/build_dashboard.py        # 5. build the HTML dashboard  (instant)
open docs/usa_mentions_dashboard.html           # 6. view it (macOS; otherwise open the file in a browser)
```

Steps 2 and 3 are independent of each other; both only need step 1. Step 5 needs step 2 and the events file in `reference/`.

## The scripts

All scripts live in `scripts/` and print `--help`.

### `download_data.py`: get the data

Downloads the yearly `Papersnake/people_daily_news` files (`YYYY.jsonl.gz`) from Hugging Face into `data/raw/`. Files already present are skipped, so it is safe to re-run.

```bash
uv run python scripts/download_data.py                       # 2010 onwards (default)
uv run python scripts/download_data.py --start-year 2015     # a later start
uv run python scripts/download_data.py --out-dir data/raw    # target folder (default)
```

Each record has `date` (`YYYY.MM.DD`), `title` and `text`. There is no article id, so the scripts generate one: `YYYYMMDD-NNN`, where NNN is the article's 0-based position within that date. Ids are stable as long as the downloaded files do not change.

### `monthly_usa_mentions.py`: monthly counts

Scans every article and aggregates per month. Writes `data/processed/usa_mentions_monthly.csv`.

```bash
uv run python scripts/monthly_usa_mentions.py
uv run python scripts/monthly_usa_mentions.py --raw-dir data/raw --out data/processed/usa_mentions_monthly.csv
```

### `article_usa_mentions.py`: per-article flags

Writes one row per article (all articles, not just matches) with whether it mentions the USA and which entities it mentions. Writes `data/processed/usa_mentions_articles.csv`.

```bash
uv run python scripts/article_usa_mentions.py
uv run python scripts/article_usa_mentions.py --raw-dir data/raw --out data/processed/usa_mentions_articles.csv
```

### `export_aliases.py`: alias glossary

Exports every alias regex with its English translation to `docs/entity_aliases.csv`, so English-speaking researchers can read what each Chinese keyword means. Re-run it after editing the aliases.

```bash
uv run python scripts/export_aliases.py
```

### `build_dashboard.py`: HTML dashboard

Embeds the monthly CSV and `reference/sanctions_events.csv` into `scripts/dashboard_template.html` and writes the standalone `docs/usa_mentions_dashboard.html` (no server, libraries or network needed). If `data/processed/sentiment_monthly.csv` exists (from `score_sentiment.py`) it is merged in too, adding the **Sentiment (1–5)**, **Share unfavourable** and **Share favourable** views and a mean-sentiment tile (without a sentiment file those views are simply absent). The sentiment file defaults to `sentiment_final_monthly.csv` (final scores after the review and arbitration passes) if it exists, otherwise `sentiment_monthly.csv` (first pass); `--sentiment PATH` overrides this. If `data/processed/usa_mentions_weekly.csv` exists (from `weekly_aggregates.py`; `--weekly PATH` to override) the dashboard also gets a **Monthly / Weekly** toggle; run `weekly_aggregates.py` before `build_dashboard.py` so both use the same sentiment scores. Rolling averages are weighted by the number of articles scored. Re-run it whenever the monthly CSV, the events file or the template changes. **Edit the template, not the generated HTML.**

```bash
uv run python scripts/build_dashboard.py
uv run python scripts/build_dashboard.py --csv data/processed/usa_mentions_monthly.csv --out docs/usa_mentions_dashboard.html
```

### `weekly_aggregates.py`: weekly aggregation

Groups the existing per-article files by week (Monday start, `week_start` column) into `data/processed/usa_mentions_weekly.csv`, **without re-reading the raw data or re-running any model** (a few seconds). It reads `usa_mentions_articles.csv` and the sentiment scores: `--sentiment auto` (default) uses `sentiment_final.csv` if it exists (after the review and arbitration passes), otherwise `sentiment_scores.csv`; `first`, `final` and `none` force a choice.

```bash
uv run python scripts/weekly_aggregates.py
```

Columns: `articles_total`, `articles_any_usa`, `share_any_usa`, `share_alias_mentions`, `articles_<entity>`, `total_mentions` (all entities together; per-entity raw mentions exist only in the monthly file), and `articles_scored`, `mean_sentiment`, `share_negative`, `share_positive`. The first and last weeks are partial (the data starts on a Friday and ends on a Wednesday). Weekly sentiment rests on a median of about 39 scored articles (as few as 3), so it is noisier than monthly; consider a moving average. The dashboard is still monthly.

### `usa_mentions.py`: shared module (not run directly)

Holds the article loader, the `ALIASES` dictionary and `mention_window` (the excerpt around the mentions) that the other scripts import.

### `sentiment_benchmark.py`: sentiment benchmark

See [Sentiment benchmark](#sentiment-benchmark).

## Outputs

Everything under `data/` is generated and git-ignored; regenerate it with the commands above.

| File | Contents |
|---|---|
| `data/raw/YYYY.jsonl.gz` | Downloaded articles, one file per year |
| `data/processed/usa_mentions_monthly.csv` | One row per month (see columns below) |
| `data/processed/usa_mentions_weekly.csv` | One row per week: mention counts and sentiment, see `weekly_aggregates.py` |
| `data/processed/usa_mentions_articles.csv` | One row per article: `article_id`, `date`, `title`, `mentions_usa` (True/False), `entities` (`;`-separated), `total_mentions` |
| `data/processed/sentiment_*.csv/.jsonl` | Sentiment scores, monthly summary, reviews, arbitrations and final scores, see [Scoring](#scoring-sentiment-with-a-model-server) and [Reviewing](#reviewing-the-scores-with-a-second-pass) |
| `docs/entity_aliases.csv` | Glossary: `entity`, `pattern` (regex), `english` (committed) |
| `docs/usa_mentions_dashboard.html` | The dashboard (committed) |

**Monthly CSV columns**

- `articles_total`: all articles that month
- `articles_any_usa`, `share_any_usa`: articles mentioning at least one tracked entity, and that as a share of all articles
- `share_alias_mentions`: articles mentioning at least one USA alias (the `usa` entity) ÷ `articles_total`. Almost identical to `share_any_usa`, because the other entities nearly always co-occur with a USA alias
- `articles_<entity>`: articles mentioning that entity
- `mentions_<entity>`: raw number of occurrences of that entity

Entities: `usa`, `president`, `obama`, `trump`, `biden`, `bush`, `congress`, `fed`. Entity groups overlap by design: "美国总统奥巴马" counts for `usa`, `president` and `obama`.

## The dashboard

Open `docs/usa_mentions_dashboard.html` in any browser. It supports light and dark mode (follows your system setting).

- **Date range** (top): All years, Last 10, 5 or 3 years. Every number and chart follows it.
- **Summary tiles**: share of articles mentioning the USA, article counts, raw mentions, peak month.
- **Main chart**: monthly values in grey with a 3-month moving average in blue. Switch the metric with the buttons: *Share (any entity)*, *Articles*, *Share (USA aliases)*, *Raw mentions*. Darker vertical lines mark presidential transitions. Hover a month for values; the left/right arrow keys also work after focusing the chart.
- **Sanctions-related events**: each event in `reference/sanctions_events.csv` appears as a thin vertical line with a dot on the baseline. Hover that month to read the event text. They are also listed in a table below the chart. Events dated after the last month of data are listed in grey but not plotted.
- **Named people and institutions**: small charts of articles per month for the president/White House, Obama, Trump, Biden, Congress and the Fed (each has its own vertical scale).
- **Table view**: a collapsible table of the selected range.

The moving-average window is set in `setGran` in `scripts/dashboard_template.html` (3 months, 4 weeks). The **Aggregation** toggle switches the whole dashboard between monthly and weekly data; in the weekly view the date ranges, event lines, tooltips and tables all use weeks (starting Monday), and the *Raw mentions* metric is hidden because per-entity raw mentions exist only in the monthly file.

## Customising

**Aliases.** Edit the `ALIASES` dictionary in `scripts/usa_mentions.py`: each entity maps to a list of `(regex, English translation)` pairs. The text is Chinese and is NFKC-normalised before matching, so full-width characters match. Every alias must have an English translation. After editing:

```bash
uv run python scripts/monthly_usa_mentions.py
uv run python scripts/article_usa_mentions.py
uv run python scripts/export_aliases.py
uv run python scripts/build_dashboard.py
```

Be careful with single-character 美 compounds, which can match unrelated words (完美, 精美, 中美洲, 美中不足). Guards for these are in the file; test new aliases against such cases.

**Events.** Edit `reference/sanctions_events.csv` (columns `date` as `YYYY-MM-DD`, `category`, `description`), then re-run `build_dashboard.py`. Categories (A–D) are shown as plain letters.

**Time range.** Use `download_data.py --start-year`, then re-run steps 2–5.

## Sentiment benchmark

`scripts/sentiment_benchmark.py` compares local Qwen models (via Ollama) on scoring the stance of an article towards the United States in the commercial and sanctions context, from 1 (confrontation) to 5 (strong cooperation); see [The scoring scale](#the-scoring-scale). It reports seconds per article, prompt and generation speed, a projected time for the whole corpus, and how much the models agree. It is a speed and agreement benchmark; it does not yet compute scores for the whole corpus.

Prerequisites: steps 1 and 3 of the quick start, plus Ollama running with the models pulled:

```bash
ollama pull qwen3.5:9b
ollama pull qwen3.5:9b-mlx     # MLX build, may be faster on Apple Silicon
ollama pull qwen3.5:4b
```

Run it:

```bash
uv run python scripts/sentiment_benchmark.py                          # 30 articles, the three models above
uv run python scripts/sentiment_benchmark.py -n 100                   # a larger sample
uv run python scripts/sentiment_benchmark.py --models qwen3.5:9b      # a single model
uv run python scripts/sentiment_benchmark.py --max-chars 1500 --context 2 --num-ctx 4096 --seed 7
```

Options: `-n` sample size (default 30), `--models` (default `qwen3.5:9b qwen3.5:9b-mlx qwen3.5:4b`), `--max-chars` cap on the excerpt length (2000), `--context` extra sentences kept around the mentions (1), `--num-ctx` context size (4096), `--seed` (42), `--raw-dir`, `--articles-csv`, `--out`.

Each article is not sent whole: it is cut to an excerpt running from the sentence containing the first entity mention to the sentence containing the last one, plus `--context` sentences on each side (see `mention_window` in `scripts/usa_mentions.py`; if the cut is longer than `--max-chars` the end is trimmed). It draws a reproducible random sample of articles that mention the USA, caches it in `data/processed/sentiment_sample.jsonl`, and writes per-article results to `data/processed/sentiment_benchmark.jsonl`. Models that are not installed are skipped with a message.

## Cloud GPU deployment (Scaleway)

Scoring all ~32.5k USA-mentioning articles with the 9B model takes about 12 hours on a laptop (measured with Ollama) and, by estimate, well under 3 hours on a cloud GPU. This section is the step-by-step guide to doing it on a GPU instance you create by hand. `deploy/` contains:

- `deploy/cloud-init.yaml`: cloud-init (user data) that creates/prepares the `ubuntu` user, installs git, tmux and uv, clones this repo into `/home/ubuntu/gpr-currency` (owned by `ubuntu`), runs `uv sync`, and pre-pulls the vLLM Docker image and the model weights in the background.
- `deploy/serve_vllm.sh`: starts, stops and tests a [vLLM](https://docs.vllm.ai/) OpenAI-compatible server in Docker.

The model runs on the GPU instance; the scoring client (`scripts/score_sentiment.py`, see [Scoring sentiment with a model server](#scoring-sentiment-with-a-model-server)) can run either on your laptop through an SSH tunnel (recommended) or on the instance itself.

### Which GPU

| GPU | Memory | Server settings | Estimated time for all articles* |
|---|---|---|---|
| L4 | 24 GB | `QUANTIZATION=fp8` (the weights do not fit otherwise) | 2-3 h |
| L40S | 48 GB | defaults | 0.7-1.2 h |
| H100 | 80 GB | `MAX_NUM_SEQS=256` | 0.3-0.6 h |
| RTX 6000 Blackwell (RTX6000B-1-96G) | 96 GB | `MAX_NUM_SEQS=256`; needs NVIDIA driver 570+ (CUDA 12.8+) and a recent vLLM image | 0.4-1 h |

\*Estimates from hardware specs for `Qwen/Qwen3.5-9B` with excerpts of ~660 tokens, not measurements; check Scaleway's pricing page for current prices (billed per minute while the instance exists). With 96 GB you could also try a larger model such as Qwen3.5-27B (`MODEL=...`), at roughly 2-3x the time; decide on a hand-labelled sample.

### 1. Push the branch

The cloud-init clones the repo from GitHub, so the branch named in its CONFIG block (`BRANCH`, default `sentiment-analysis`) must be pushed with your latest commits, and the repo must be reachable without credentials (public). For a private repo, clone by hand over SSH after boot instead (see the note at the top of `cloud-init.yaml`).

### 2. Create the instance

In the Scaleway console create the GPU instance with a **GPU OS** image (Ubuntu with NVIDIA drivers, Docker and the NVIDIA container toolkit preinstalled) and about 40 GB of disk (image + weights). Under *Advanced options → Cloud-init*, paste the contents of `deploy/cloud-init.yaml` after editing its CONFIG block (`APP_USER`, `REPO_URL`, `BRANCH`, `MODEL`, `VLLM_IMAGE`). If the image has no `ubuntu` user, cloud-init creates it with root's SSH keys and passwordless sudo.

### 3. Wait for the setup, then log in again

```bash
ssh ubuntu@<instance-ip>
tail -f /var/log/gpr-setup.log        # wait for "SETUP DONE" (a few minutes: it downloads ~18 GB of weights)
exit
ssh ubuntu@<instance-ip>              # log in again so the docker group membership applies
nvidia-smi                            # confirm the GPU is visible (Blackwell: driver 570 or newer)
cd ~/gpr-currency
```

### 4. Start the model server (on the instance)

```bash
deploy/serve_vllm.sh                              # Qwen/Qwen3.5-9B, waits until the server is ready
MAX_NUM_SEQS=256 deploy/serve_vllm.sh             # larger batches on an H100 / RTX 6000 Blackwell
QUANTIZATION=fp8 deploy/serve_vllm.sh             # on a 24 GB L4
MODEL=Qwen/Qwen3.5-4B deploy/serve_vllm.sh        # a smaller, faster model
deploy/serve_vllm.sh test                         # one sample request; should print a JSON score
deploy/serve_vllm.sh status | logs | stop | restart
```

The server runs in Docker (restarted automatically), exposes an OpenAI-compatible API at `http://127.0.0.1:8000/v1` under the model name `qwen`, and listens on **localhost only**. All options (context length, memory fraction, batch size, extra vLLM arguments, image tag, ...) are environment variables documented at the top of `deploy/serve_vllm.sh`. If it fails to start, `deploy/serve_vllm.sh logs` shows why; typical causes are an old NVIDIA driver, a vLLM image that does not support the GPU (try `VLLM_IMAGE=<newer tag>`), or too little memory (smaller `MAX_MODEL_LEN`, or `EXTRA_ARGS="--limit-mm-per-prompt {}"` for the multimodal model; check the vLLM docs for flags your image supports).

### 5. Run the scoring client

**Option A (recommended): client on your laptop, through an SSH tunnel.** The excerpts are built from the data you already have locally, results land directly in your local `data/processed/`, and the instance needs no data download. Keep the tunnel and the Mac awake while it runs.

```bash
# laptop, terminal 1: the tunnel (leave it open)
ssh -N -L 8000:localhost:8000 -o ServerAliveInterval=30 ubuntu@<instance-ip>

# laptop, terminal 2: the client (needs data/raw from download_data.py, or an existing data/processed/sentiment_inputs.jsonl)
cd gpr-currency
curl -s localhost:8000/health && echo OK                                     # tunnel and server reachable
uv run python scripts/score_sentiment.py --limit 20                          # smoke test
head -5 data/processed/sentiment_scores.csv
caffeinate -i uv run python scripts/score_sentiment.py --concurrency 128     # full run (caffeinate keeps the Mac awake)
```

**Option B: client on the instance** (more robust for very long runs; run it in `tmux` so it survives a disconnect).

```bash
# on the instance, in ~/gpr-currency
uv run python scripts/download_data.py                  # the raw data is not in git (~620 MB)
uv run python scripts/score_sentiment.py --limit 20     # smoke test
tmux new -s score
uv run python scripts/score_sentiment.py --concurrency 128
# detach: Ctrl-b then d          reattach: tmux attach -t score

# afterwards, from your laptop:
scp ubuntu@<instance-ip>:gpr-currency/data/processed/sentiment_{scores.csv,monthly.csv,scores.jsonl} data/processed/
```

Either way the run is **resumable**: if it is interrupted (Ctrl-C, a dropped tunnel, a reboot), run the same command again and it continues with the unscored articles. Add `--no-reason` for a faster, score-only run. Monitor the GPU with `watch -n 2 nvidia-smi` and the server with `deploy/serve_vllm.sh logs` on the instance.

### 6. Delete the instance

GPU instances are billed per minute while they exist. When the run has finished and the results are on your laptop, delete the instance in the Scaleway console (do not rely on stopping it: check Scaleway's docs on whether a stopped GPU instance is still billed).

Qwen3.5 has a thinking mode; the client switches it off with `chat_template_kwargs` on every request (the `test` command does too). To expose the server publicly instead of tunnelling, set `BIND=0.0.0.0` **and** `VLLM_API_KEY` (not recommended).

## The scoring scale

The study is about sanctions and economic relations between China and the United States, so the models do not rate generic positive/negative tone. For every article they decide **two things**, using the wording in `scripts/sentiment_common.py` (`FOCUS`, `RELEVANCE`, `SCALE`, `JUDGE`):

**1. Is the article relevant?** It is relevant if the US is a real subject of its economic, commercial, financial, sanctions or geopolitical content, or if it portrays the US or the West as strong, weak, divided, failing or in decline, or if an American official, scholar or outlet comments on the economy, trade or geopolitics. It is **not** relevant if the US is only incidental: a venue or a stop on an itinerary, a name in passing, an American quoted about something unrelated, sport, culture, an accident or a disaster. **Irrelevant articles are excluded** from all sentiment aggregates (they stay in `sentiment_scores.csv` and `sentiment_final.csv` with `relevant = False`, and in the mention counts, which measure attention only).

**2. What view of the US does it convey?** The score judges the view of the United States itself, **not the relationship, not China, and not whether the news is good or bad**. Praise of China, or criticism of third countries, is not a view of the US. In particular, **an American praising China is not praise of the US**: such an article scores 3 unless it also expresses a view of the US itself.

| Score | Meaning |
|---|---|
| 1 | Hostile: the US is portrayed as an aggressor or bully (imposing or threatening sanctions, tariffs, export controls), blamed and condemned |
| 2 | Critical: the US is criticised or portrayed negatively (in the wrong, hypocritical, divided, weak, failing or in decline) without outright condemnation |
| 3 | Neutral: no clear view of the US: factual reporting, balanced signals, or a text about China or others that expresses no view of the US |
| 4 | Favourable: the US is portrayed positively (a constructive or credible partner, succeeding, cooperating) |
| 5 | Very favourable: strong praise of the US or of cooperation with it |

Output columns: `sentiment_scores.csv` has `relevant` and `sentiment_score`; `sentiment_monthly.csv` / `sentiment_final_monthly.csv` count **relevant articles only** (`articles_scored`, `mean_sentiment`, `share_negative` = scores 1-2, `share_positive` = scores 4-5; the dashboard labels the last two *Share unfavourable* and *Share favourable*). The review and arbitration passes judge relevance as well as the score: two "irrelevant" verdicts agree whatever the scores, otherwise relevance and score must both match.

**Small models are stricter on relevance.** In a 30-article test on the first days of 2010, Qwen 4B judged 27 irrelevant and Qwen 9B 19; the 9B matched expectations on the examples checked (a mascot tour excluded, a story about US security failures and partisan disputes relevant and critical). Check a sample of excluded articles after the full run (`relevant == False` in `sentiment_scores.csv`) before trusting the exclusion rate.

**Changing the scale means scoring everything again.** Every result carries a `prompt` version (`PROMPT_VERSION` in `sentiment_common.py`, currently `stance-v3`; results with no version come from the original "completely negative / completely positive" prompt, `attitude-v1`). The scoring, review and arbitration scripts refuse to resume on top of results from another version, because mixing scales would be meaningless. To rescore, move the old files aside first, then run the passes again:

```bash
mkdir -p data/processed/v1
mv data/processed/sentiment_{scores,reviews,arbitrations,final,final_monthly}.* data/processed/sentiment_monthly.csv data/processed/v1/
uv run python scripts/score_sentiment.py        # then review_sentiment.py, arbitrate_sentiment.py, weekly_aggregates.py, build_dashboard.py
```

If you edit the wording or a schema, bump `PROMPT_VERSION`. `sentiment_inputs.jsonl` (the excerpts) does not depend on the prompt and can stay.

## Scoring sentiment with a model server

`scripts/score_sentiment.py` scores every USA-mentioning article (about 32.5k) from 1 (confrontation) to 5 (strong cooperation), see [The scoring scale](#the-scoring-scale), with an OpenAI-compatible server such as the vLLM server from [Cloud GPU deployment](#cloud-gpu-deployment-scaleway). It uses the same prompt as the benchmark (`scripts/sentiment_common.py`) and sends each article's excerpt (from before the first to after the last mention), keeping many requests in flight so vLLM batches them.

```bash
uv run python scripts/score_sentiment.py --limit 20       # smoke test on 20 articles
uv run python scripts/score_sentiment.py                  # all articles, server at http://127.0.0.1:8000/v1
uv run python scripts/score_sentiment.py --no-reason      # score only: fewer output tokens, faster
uv run python scripts/score_sentiment.py --summary-only   # just rebuild the CSVs from the scores so far
```

It runs three stages, each skipped if its output exists: (1) build `data/processed/sentiment_inputs.jsonl` from the raw data (needs `download_data.py`; ~1.5 min); (2) score into `data/processed/sentiment_scores.jsonl`, appending as it goes; (3) write `data/processed/sentiment_scores.csv` (`article_id`, `date`, `relevant`, `sentiment_score`, `reason`) and `data/processed/sentiment_monthly.csv` (`month`, `articles_scored`, `mean_sentiment`, `share_negative` = scores 1-2, `share_positive` = scores 4-5). **It is resumable:** every result is written to disk as soon as it arrives, so if it stops for any reason (Ctrl-C, a dropped tunnel, a crash) you run the same command again and it continues with the unscored articles; failed articles are retried on the next run. Ctrl-C stops within a second, writes the CSVs for what is done so far, and exits with code 130. A line cut off by a hard kill is skipped on the next run.

Options: `--base-url` (default `http://127.0.0.1:8000/v1`), `--model` (default `qwen`, the vLLM `SERVED_MODEL_NAME`), `--api-key` (or `VLLM_API_KEY`), `--concurrency` (64), `--limit`, `--no-reason`, `--max-tokens`, `--timeout`, `--retries`, `--extra-body` (JSON merged into each request), `--context`, `--max-chars`, `--rebuild-inputs`, `--summary-only`, plus path options (`--raw-dir`, `--inputs`, `--out`, `--csv-out`, `--monthly-out`).

To try it locally with Ollama before renting a GPU (Ollama ignores vLLM's thinking switch, so pass `reasoning_effort`):

```bash
uv run python scripts/score_sentiment.py --base-url http://localhost:11434/v1 --model qwen3.5:4b \
    --extra-body '{"reasoning_effort": "none"}' --concurrency 2 --limit 10
```

To run it against a model on a cloud GPU, follow [Cloud GPU deployment (Scaleway)](#cloud-gpu-deployment-scaleway). The default `--concurrency 64` suits the server's default `MAX_NUM_SEQS=128`; use `--concurrency 128` with `MAX_NUM_SEQS=256`.

## Reviewing the scores with a second pass

`scripts/review_sentiment.py` audits the scores. For each scored article, a reviewer model sees the same excerpt plus the first annotator's score and reason, and answers: does it agree, what score would it give, and why (if it disagrees, what the first annotator got wrong). It runs against the same kind of server as the scoring client, takes `sentiment_scores.jsonl` as input, and is resumable in the same way.

```bash
uv run python scripts/review_sentiment.py --limit 20        # smoke test
uv run python scripts/review_sentiment.py                   # review every scored article
uv run python scripts/review_sentiment.py --only-extreme    # skip the neutral 3s (about 40% of articles)
uv run python scripts/review_sentiment.py --summary-only    # rebuild the CSV and print the summary
```

Outputs: `data/processed/sentiment_reviews.jsonl` (appended as it goes) and `data/processed/sentiment_reviews.csv` (`article_id`, `date`, `relevant`, `score`, `agree`, `revised_relevant`, `revised_score`, `explanation`, `reason`). It prints the agreement rate, the agreement by original score, the direction of the disagreements and an original-by-revised score table. The review is a second opinion from a language model, not ground truth: it does not change `sentiment_scores.csv` or the dashboard.

**Use an independent reviewer if you can.** A model reviewing its own output tends to agree too readily or to be sceptical in a systematic way (in a 8-article test with Qwen 4B it disagreed almost every time and pulled scores towards 3). For a more independent check, serve a different or larger model (`MODEL=<hf id> SERVED_MODEL_NAME=reviewer deploy/serve_vllm.sh restart`) and pass `--base-url` and `--model reviewer`. Options match `score_sentiment.py` (`--base-url`, `--model`, `--concurrency`, `--limit`, `--max-tokens` (150), `--extra-body`, ...) plus `--only-extreme`, `--scores` and `--out`/`--csv-out`. The review costs about as much GPU time as the scoring pass, since the prompt is the same excerpt plus a short explanation.

## Arbitrating disagreements (third pass)

`scripts/arbitrate_sentiment.py` settles the articles where the reviewer disagreed. The arbiter model sees the excerpt, both scores and both reasonings (the first annotator's reason and the reviewer's explanation) and returns a `final_score`, plus an explanation of which reasoning holds up. It may side with either or choose a different score. The `decision` column (`first`, `second`, `neither`) is derived from the numbers, so it cannot contradict the score. Articles where the reviewer agreed keep their score.

```bash
uv run python scripts/arbitrate_sentiment.py --limit 20       # smoke test
uv run python scripts/arbitrate_sentiment.py                  # all disagreements
uv run python scripts/arbitrate_sentiment.py --summary-only   # rebuild the CSVs only
```

Outputs: `data/processed/sentiment_arbitrations.jsonl` (resumable), `data/processed/sentiment_final.csv` (every article: `first_relevant`, `first_score`, `reviewer_relevant`, `reviewer_score`, `final_relevant`, `final_score`, `source` = `first_agreed` / `arbitrated` / `first_unreviewed`, `decision`, `arbiter_explanation`) and `data/processed/sentiment_final_monthly.csv`, which has the same columns as `sentiment_monthly.csv` but computed from the final scores. Run it only after `review_sentiment.py` has finished: articles not yet reviewed or arbitrated keep their first score (`first_unreviewed`), and the summary says how many disagreements are still pending. Options match the other clients (`--base-url`, `--model`, `--concurrency`, `--limit`, `--max-tokens`, `--extra-body`, `--reviews`, `--out`, `--csv-out`, `--monthly-out`).

The pipeline is therefore: `score_sentiment.py` -> `review_sentiment.py` -> `arbitrate_sentiment.py`. Using a different model for each pass gives the most independent result; the arbiter is still a language model, not ground truth. The dashboard still reads `sentiment_monthly.csv` (first-pass scores); use `build_dashboard.py --sentiment data/processed/sentiment_final_monthly.csv` to show the final scores.

## Repository layout

```
pyproject.toml, uv.lock, .python-version   uv project and locked dependencies
CLAUDE.md                                  instructions for Claude Code (kept up to date with every PR)
scripts/
  download_data.py                         download the dataset
  usa_mentions.py                          loader + ALIASES (shared module)
  monthly_usa_mentions.py                  monthly CSV
  article_usa_mentions.py                  per-article CSV
  export_aliases.py                        alias glossary with English translations
  build_dashboard.py, dashboard_template.html   dashboard builder and its template
  sentiment_benchmark.py                   local-LLM sentiment benchmark
  sentiment_common.py                      shared sentiment prompt and JSON schema
  score_sentiment.py                       batch sentiment scoring against a vLLM/OpenAI-compatible server
  weekly_aggregates.py                     weekly counts and sentiment from the per-article CSVs
  review_sentiment.py                      second pass: a model agrees/disagrees with each score and says why
  arbitrate_sentiment.py                   third pass: an arbiter settles disagreements and gives the final score
deploy/                                    cloud-init.yaml + serve_vllm.sh for a Scaleway GPU box
reference/sanctions_events.csv             hand-maintained events timeline
docs/                                      committed outputs: dashboard and alias glossary
data/                                      downloaded and generated data (git-ignored)
```

## Troubleshooting

- **`No .jsonl.gz files in data/raw; run scripts/download_data.py first.`** Run the download step.
- **`FileNotFoundError` for a CSV in `data/processed/`** The earlier step has not been run. Follow the quick-start order.
- **The dashboard shows old numbers.** Re-run `build_dashboard.py` after regenerating the monthly CSV.
- **Chinese text looks garbled in Excel.** Open `docs/entity_aliases.csv` via *Data → From Text/CSV* with UTF-8 encoding (it is written with a BOM, so Excel normally detects it). The other CSVs are plain UTF-8.
- **Benchmark: `skipped: ...` for a model.** The model is not pulled, or Ollama is not running. Start the Ollama app and run `ollama pull <model>`.
- **A script cannot import `usa_mentions`.** Run scripts as `uv run python scripts/<name>.py` from the repo root (the scripts import each other as siblings).
