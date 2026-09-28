# Local development

## Quick start

```bash
./run-local.sh            # http://127.0.0.1:5001
PORT=8080 ./run-local.sh  # different port
```

`run-local.sh` forces a **local SQLite database**. That default matters — see
"`.env` mirrors production" below.

Port 5000 is taken by macOS AirPlay Receiver, so the script uses 5001.

## Environment files

| File | Purpose | Committed? |
|---|---|---|
| `.env.example` | template, lists every variable | yes |
| `.env` | the working config — mirrors the deployment values | **no, gitignored** |
| `.env.*` | ignored on purpose (`.env.local`, `.env.production`, …) | **no** |

`.gitignore` ignores `.env` *and* `.env.*`, with `!.env.example` re-allowing the
template. Plain `.env` alone is not enough: a file called `.env.production`
contains exactly the same secrets and would otherwise be committed.

> **`.env` mirrors production.** It points `DATABASE_URL` at the live production
> database and holds the real API keys, so that local testing uses the same
> configuration the server does. The consequence is that **any write you trigger
> in the local UI (votes, imports, recalculation, purchases) changes production
> data**. Use `run-local.sh`, which overrides the database with local SQLite, and
> only pass `KI_USE_PROD_ENV=1` when you really mean it.

Variables exported by the shell (or by `run-local.sh`) win over `.env`, because
python-dotenv does not overwrite variables that are already set.

## Interpreter

The project needs Python 3.10+. This machine has 3.9.6 as `python3` and Homebrew
3.13/3.14. `requirements.txt` pins `numpy==2.0.0` and `matplotlib==3.9.0`, which
have no wheels for 3.13+, so the venv is built with 3.12 via `uv`:

```bash
uv venv --python 3.12 venv
uv pip install --python venv/bin/python -r requirements.txt
```

## Scripts

| Script | What it does | Safety |
|---|---|---|
| `run-local.sh` | starts the dev server on local SQLite | safe |
| `scripts/seed_demo_data.py` | seeds demo companies/analyses/stock prices for local chart testing | **refuses non-local databases** unless `--force-i-know-this-is-not-local` |
| `scripts/inspect_prod.py` | read-only questions against the production database | opens `SET TRANSACTION READ ONLY`, SELECTs only |
| `scripts/inspect_notion.py` | read-only dump of the Notion "Analysis Schedule" | hard method+path allowlist; refuses `/pages` and `/blocks` |
| `scripts/i18n_audit.py` | translation coverage / missing / stale keys | read-only |

Both inspectors never build a Flask app: `create_app()` runs `db.create_all()`
and can insert seed rows, which must not happen against production. Both refuse
to run if they cannot prove they are read-only.

```bash
venv/bin/python scripts/inspect_prod.py            # counts, date ranges, board verdict
venv/bin/python scripts/inspect_notion.py          # schedule, schema drift, date analysis
venv/bin/python scripts/inspect_notion.py --selftest   # prove the allowlist refuses writes
```

## Logging

Logging is configured in `app/logging_config.py` and writes to stderr plus
`instance/logs/app.log` (rotating). Every request logs method, path, status,
duration, user and a correlation id, so `grep` on the request id gives you the
whole story of one request, including the chart-data diagnostics.

```
LOG_LEVEL=INFO            # DEBUG / INFO / WARNING / ERROR  (default: DEBUG in debug mode)
APP_LOG_LEVEL=DEBUG       # level for the app.* loggers only
LOG_HTTP_REQUESTS=true    # one line per request
SLOW_REQUEST_MS=1000      # slower than this logs at WARNING
LOG_SQL=false             # true logs every SQL statement
LOG_FILE=app.log          # "" disables the file log
```

## Tests

```bash
venv/bin/python -m pytest -q                 # fast, hermetic: 546 passed
KI_NETWORK_TESTS=1 venv/bin/python -m pytest # also runs tests that hit Yahoo/DeepSeek
```

`tests/conftest.py` forces a throwaway SQLite database before the app is
imported, so **the suite can never touch the deployment database**, even though
`.env` points at it.

The `tests/` directory also contains some older ad-hoc scripts that execute
application code at import time; `pytest.ini` excludes those. The real suite is
`test_i18n.py`, `test_templates.py`, `test_brave_search.py`,
`test_brave_with_context.py`, `test_tickers.py`, `test_yahooquery.py` and
`test_verification.py`.

There are also two browser-level checks that need `jsdom` and a rendered page
(they cover things pytest cannot see, such as whether a chart actually gets
drawn or whether a template rewrite mangled the markup). See the header comments
in `tests/js/`.

## Before you deploy

Pushing to `main` deploys to production automatically. Check first:

```bash
venv/bin/python -m pytest -q
venv/bin/python scripts/i18n_audit.py --strict
```

A fresh `pip install -r requirements.txt` must work too — `requirements.txt`
pins `SQLAlchemy<2.1` on purpose (2.1 defaults bare `postgresql://` URLs to
psycopg3, which is not installed, and the app then fails to boot).
