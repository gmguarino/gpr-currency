# gpr-currency

How often, and in what tone, does China's *People's Daily* (人民日报) talk about the United States? This repo downloads the newspaper's archive from 2010 onwards, counts mentions of the USA and related entities (presidents, Congress, the Fed, …) per month and per article, and presents the result in a self-contained HTML dashboard. A sentiment-scoring benchmark with local Qwen models is in progress.

## Contents

- [Requirements](#requirements)
- [Setup](#setup)
- [Quick start](#quick-start)
- [The scripts](#the-scripts)
- [Outputs](#outputs)
- [The dashboard](#the-dashboard)
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

Embeds the monthly CSV and `reference/sanctions_events.csv` into `scripts/dashboard_template.html` and writes the standalone `docs/usa_mentions_dashboard.html` (no server, libraries or network needed). Re-run it whenever the monthly CSV, the events file or the template changes. **Edit the template, not the generated HTML.**

```bash
uv run python scripts/build_dashboard.py
uv run python scripts/build_dashboard.py --csv data/processed/usa_mentions_monthly.csv --out docs/usa_mentions_dashboard.html
```

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
| `data/processed/usa_mentions_articles.csv` | One row per article: `article_id`, `date`, `title`, `mentions_usa` (True/False), `entities` (`;`-separated), `total_mentions` |
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

The moving-average window is the `W` constant near the top of the script in `scripts/dashboard_template.html`.

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

`scripts/sentiment_benchmark.py` compares local Qwen models (via Ollama) on scoring the sentiment of an article towards the United States, from 1 (completely negative) to 5 (completely positive). It reports seconds per article, prompt and generation speed, a projected time for the whole corpus, and how much the models agree. It is a speed and agreement benchmark; it does not yet compute scores for the whole corpus.

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

Scoring all ~32.5k USA-mentioning articles with a 9B model takes about 12 hours on a laptop and roughly 0.5-3 hours on a cloud GPU (L4, L40S or H100; the L40S is the best value). `deploy/` contains what you need to bring up a GPU box by hand and serve a model with [vLLM](https://docs.vllm.ai/):

- `deploy/cloud-init.yaml`: cloud-init (user data) that installs git, tmux and uv, clones this repo, runs `uv sync`, and pre-pulls the vLLM Docker image and the model weights in the background.
- `deploy/serve_vllm.sh`: starts, stops and tests a vLLM OpenAI-compatible server in Docker.

**1. Push your branch.** The cloud-init clones the repo from GitHub, so the branch it names (`BRANCH` in the CONFIG block, default `sentiment-analysis`) must be pushed, and the repo must be reachable (public, or see the note about private repos in the file).

**2. Create the instance.** In the Scaleway console create a GPU instance (L4-1-24G, L40S-1-48G or H100-1-80G) with a **GPU OS** image (Ubuntu with NVIDIA drivers, Docker and the NVIDIA container toolkit preinstalled). Under *Advanced options → Cloud-init*, paste the contents of `deploy/cloud-init.yaml` after editing its CONFIG block (`APP_USER`, `REPO_URL`, `BRANCH`, `MODEL`, `VLLM_IMAGE`). The repo is cloned into `/home/<APP_USER>/gpr-currency`, owned by that user (default `ubuntu`, created if the image has no such user), who is also added to the `docker` group and gets the model cache in their home. Allow ~40 GB of disk for the image and weights.

**3. Wait for setup, then connect.**

```bash
ssh ubuntu@<instance-ip>             # cloud-init creates the ubuntu user if the image has none
tail -f /var/log/gpr-setup.log        # wait for "SETUP DONE" (a few minutes: it downloads ~18 GB of weights)
exit && ssh ubuntu@<instance-ip>      # log in again so the docker group membership applies
cd ~/gpr-currency
```

**4. Start the model server.**

```bash
deploy/serve_vllm.sh                              # Qwen/Qwen3.5-9B on an L40S or H100
QUANTIZATION=fp8 deploy/serve_vllm.sh             # on a 24 GB L4 (weights fit in half the memory)
MODEL=Qwen/Qwen3.5-4B deploy/serve_vllm.sh        # a smaller model
deploy/serve_vllm.sh test                         # send one sample sentiment request
deploy/serve_vllm.sh status | logs | stop | restart
```

The server exposes an OpenAI-compatible API at `http://127.0.0.1:8000/v1` (model name `qwen`). It listens on localhost only. Run the scoring client on the instance, or reach the server from your laptop through a tunnel: `ssh -L 8000:localhost:8000 ubuntu@<instance-ip>`. To expose it publicly set `BIND=0.0.0.0` **and** `VLLM_API_KEY`. All options (context length, memory fraction, batch size, extra vLLM arguments, image tag, ...) are environment variables listed at the top of `deploy/serve_vllm.sh`.

Qwen3.5 has a thinking mode; clients should send `"chat_template_kwargs": {"enable_thinking": false}` with each request (the `test` command does). The Qwen3.5 models are multimodal; if vLLM runs short of memory on the 24 GB L4, try `EXTRA_ARGS="--limit-mm-per-prompt {}"` or a smaller `MAX_MODEL_LEN` (check the vLLM docs for the flags your image version supports).

**5. Shut the instance down when finished.** GPU instances are billed per minute while they exist; delete the instance (or check Scaleway's docs on whether a stopped GPU instance is still billed) so it does not keep running.

The instance only hosts the model: once it is up, run the batch client on it (see [Scoring sentiment with a model server](#scoring-sentiment-with-a-model-server)).

## Scoring sentiment with a model server

`scripts/score_sentiment.py` scores every USA-mentioning article (about 32.5k) from 1 (completely negative) to 5 (completely positive) with an OpenAI-compatible server such as the vLLM server from [Cloud GPU deployment](#cloud-gpu-deployment-scaleway). It uses the same prompt as the benchmark (`scripts/sentiment_common.py`) and sends each article's excerpt (from before the first to after the last mention), keeping many requests in flight so vLLM batches them.

```bash
uv run python scripts/score_sentiment.py --limit 20       # smoke test on 20 articles
uv run python scripts/score_sentiment.py                  # all articles, server at http://127.0.0.1:8000/v1
uv run python scripts/score_sentiment.py --no-reason      # score only: fewer output tokens, faster
uv run python scripts/score_sentiment.py --summary-only   # just rebuild the CSVs from the scores so far
```

It runs three stages, each skipped if its output exists: (1) build `data/processed/sentiment_inputs.jsonl` from the raw data (needs `download_data.py`; ~1.5 min); (2) score into `data/processed/sentiment_scores.jsonl`, appending as it goes; (3) write `data/processed/sentiment_scores.csv` (`article_id`, `date`, `sentiment_score`, `reason`) and `data/processed/sentiment_monthly.csv` (`month`, `articles_scored`, `mean_sentiment`, `share_negative` = scores 1-2, `share_positive` = scores 4-5). **It is resumable:** if it stops, run it again and it continues with the unscored articles; failed articles are retried on the next run.

Options: `--base-url` (default `http://127.0.0.1:8000/v1`), `--model` (default `qwen`, the vLLM `SERVED_MODEL_NAME`), `--api-key` (or `VLLM_API_KEY`), `--concurrency` (64), `--limit`, `--no-reason`, `--max-tokens`, `--timeout`, `--retries`, `--extra-body` (JSON merged into each request), `--context`, `--max-chars`, `--rebuild-inputs`, `--summary-only`, plus path options (`--raw-dir`, `--inputs`, `--out`, `--csv-out`, `--monthly-out`).

To try it locally with Ollama before renting a GPU (Ollama ignores vLLM's thinking switch, so pass `reasoning_effort`):

```bash
uv run python scripts/score_sentiment.py --base-url http://localhost:11434/v1 --model qwen3.5:4b \
    --extra-body '{"reasoning_effort": "none"}' --concurrency 2 --limit 10
```

On the GPU instance, run `uv run python scripts/download_data.py` first (the raw data is not in git), start the server with `deploy/serve_vllm.sh`, then run the client. With the default `--concurrency 64` and the server's `MAX_NUM_SEQS=128`, the GPU stays busy.

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
