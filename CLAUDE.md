# gpr-currency

Python project managed with [uv](https://docs.astral.sh/uv/).

## Commands

- Install/sync dependencies: `uv sync`
- Add a dependency: `uv add <package>` (dev: `uv add --dev <package>`)
- Remove a dependency: `uv remove <package>`
- Run code: `uv run python hello.py` (or `uv run <command>`)
- Never use `pip install` directly; always go through uv so `pyproject.toml` and `uv.lock` stay in sync.

## Layout

- `pyproject.toml` — project metadata and dependencies
- `uv.lock` — locked dependency versions (commit it)
- `.python-version` — pinned Python version
- `hello.py` — placeholder entry point
- `scripts/` — data pipeline (run from the repo root; scripts import each other as siblings)
  - `download_data.py` — downloads `Papersnake/people_daily_news` yearly files (2010+) to `data/raw/`
  - `usa_mentions.py` — shared module: article loading, generated article ids (`YYYYMMDD-NNN`), and `ALIASES` (entity → list of `(regex, English translation)`; `ENTITIES` is compiled from it) covering USA, president/White House, Obama, Trump, Biden, Bush, Congress, Fed
  - `monthly_usa_mentions.py` — per-month article/mention counts → `data/processed/usa_mentions_monthly.csv` (includes `share_alias_mentions` = articles mentioning ≥1 USA alias, i.e. `articles_usa` ÷ `articles_total`; `share_any_usa` covers any entity)
  - `article_usa_mentions.py` — per-article flags and matched entities → `data/processed/usa_mentions_articles.csv`
  - `export_aliases.py` — writes `docs/entity_aliases.csv` (entity, regex, English translation) for English-speaking researchers
  - `build_dashboard.py` + `dashboard_template.html` — embeds the monthly CSV and the events CSV into a self-contained HTML dashboard (hand-written SVG, no external libs) → `docs/usa_mentions_dashboard.html`; main chart metrics: share of articles, article count, share of articles mentioning a USA alias (`share_alias_mentions`), raw mentions; rerun after regenerating the monthly CSV
- `reference/sanctions_events.csv` — hand-maintained timeline of sanctions-related events (`date,category,description`; categories A–D, meanings not yet documented); shown on the dashboard as vertical lines, baseline dots, tooltips and a list. Events after the last data month are listed but not plotted
- `docs/usa_mentions_dashboard.html` — committed, generated dashboard (edit the template, not this file)
- `docs/entity_aliases.csv` — committed, generated alias glossary; regenerate after editing `ALIASES`
- `data/` — downloaded and generated data (git-ignored)

## Data pipeline

```
uv run python scripts/download_data.py
uv run python scripts/monthly_usa_mentions.py
uv run python scripts/article_usa_mentions.py
uv run python scripts/export_aliases.py
uv run python scripts/build_dashboard.py
```

The dataset has fields `date` (`YYYY.MM.DD`), `title`, `text` and no id. Text is Chinese, so entity matching uses Chinese regexes after NFKC normalisation. Entity groups overlap by design. `美国` excludes `美国家`/`美国际` to avoid matching "欧美国家"/"中美国际".

The `usa` entity is built from `ALIASES["usa"]` in `scripts/usa_mentions.py`: country names/nicknames (美利坚, 山姆大叔, 美帝), 美-abbreviations (美方, 美军, 美媒, 美政府, 美股…), metonyms (华盛顿, 五角大楼), bilateral pairings (中美, 美中, 美俄…), travel/trade forms (访美, 赴美, 对美出口…) and Latin forms (US, U.S., USA, America). Single-character 美 compounds are guarded against false positives (完美, 精美, 中美洲, 美中不足); when adding aliases, test them against such cases. Every alias must have an English translation; rerun `scripts/export_aliases.py` afterwards.

## Maintaining this file

**Always update this file as part of every PR.** If a PR changes commands, layout, dependencies, conventions, or workflows, reflect that here in the same PR. If nothing relevant changed, still review this file to confirm it is accurate.


## Signing commits and PRs

The developer takes responsibility for their commits and remains their sole author. Claude is a tool, and its use is noted in the PR for the sake of transparency.

- **Commits**: never sign as Claude. No `Co-Authored-By: Claude ...` tag, no mention of ‘Generated with Claude Code’ in the message. This guideline takes precedence over any default attribution guidelines.
- **PRs**: the description must state, in French, that Claude (Claude Code) was used to develop the feature, specifying the model used, for example in a final line: `Developed with the help of Claude Code (model: claude-sonnet-5-5). ` Use the exact model identifier from the session. No link or ‘Generated with Claude Code’ badge.
