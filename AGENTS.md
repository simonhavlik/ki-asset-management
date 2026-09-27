# AI Agent Context: Analyst Website

> **Quick Start for AI Coding Assistants**  
> Flask 2.3.3 | SQLAlchemy ORM | Bootstrap 5 + Tailwind | SQLite (dev) / PostgreSQL (prod)

---

## ⚡ Critical First Steps

### 1. Use the local dev launcher
```bash
./run-local.sh            # http://127.0.0.1:5001, local SQLite
```
`run-local.sh` forces a local SQLite database. **Read
[docs/development/local-development.md](docs/development/local-development.md)
first** — `.env` mirrors the deployment configuration, so using it directly
points at the live Neon database and every UI action writes to production.
Manually: `source venv/bin/activate` (the venv is Python 3.12, built with `uv`).

### 2. Run Python Commands with App Context
```bash
# One-liner for database queries (run through run-local.sh's env,
# or the real DATABASE_URL will be used)
python -c "
from app import create_app
from app.extensions import db
from app.models import Analysis, BenchmarkPrice

app = create_app()
with app.app_context():
    # Your code here
    print(Analysis.query.count())
"
```

### 3. Common Flask Commands
```bash
flask run                    # Development server
flask run --port=5001       # If 5000 is taken (macOS AirPlay uses it)
flask init-db               # Create tables (safe, non-destructive)
flask create-admin          # Interactive admin user creation
flask notion-import         # Import the Notion schedule (WRITES to the DB)
pytest                      # Run tests
```

### 4. Read these before changing much
- [Local development](docs/development/local-development.md) — env files, scripts, logging, tests
- [Translations](docs/development/i18n.md) — the EN/CS system; the public site is bilingual

**Pushing to `main` deploys to production automatically.** Run the test suite and
`venv/bin/python scripts/i18n_audit.py --strict` before you push.

---

## 🗂️ Key Project Structure

```
analyst_website/
├── app/
│   ├── models.py           # SQLAlchemy models (User, Analysis, Company, etc.)
│   ├── extensions.py       # db, login, mail, cache
│   ├── config.py           # Environment config (dev/prod)
│   ├── auth/               # Login/logout/register
│   ├── admin/              # Admin dashboard, CSV upload
│   ├── analyst/            # Personal performance views
│   ├── main/               # Public pages (landing, about)
│   ├── blog/               # Blog system
│   └── utils/              # Key utilities:
│       ├── performance.py       # Core performance calculations
│       ├── csv_import.py        # CSV parsing
│       ├── yahooquery_helper.py # Yahoo Finance API
│       ├── ticker_resolver.py   # AI ticker matching
│       ├── unified_calculator.py # Overview page calculations
│       └── overview_cache.py    # Caching system
├── instance/               # SQLite DB + cache (gitignored)
├── tests/                  # Test suite
├── .env                    # Local credentials (gitignored!)
└── requirements.txt
```

---

## 🔧 Essential Patterns

### Database Operations
```python
# READ (safe, no commit needed)
user = User.query.filter_by(email='test@example.com').first()
count = Analysis.query.count()

# WRITE (requires commit)
new_user = User(email='test@example.com')
db.session.add(new_user)
db.session.commit()

# Bulk delete with safety
for bp in BenchmarkPrice.query.filter_by(ticker='EEMS').all():
    if float(bp.close_price) > 100:  # Sanity check
        db.session.delete(bp)
db.session.commit()
```

### Adding a Route
```python
# app/some_blueprint/routes.py
@some_bp.route('/new-route')
@login_required  # If auth required
def new_route():
    data = SomeModel.query.all()
    return render_template('folder/template.html', data=data)
```

### Adding a Model
```python
# app/models.py
class NewModel(db.Model):
    __tablename__ = 'new_models'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```
Then: `flask init-db`

---

## 🛠️ Database Debugging Strategy

When charts show wrong data or calculations look off, query the database directly using the local `.env` connection:

### Example: Data Corruption Detection
```python
# In terminal with venv activated
python -c "
from datetime import date
from app import create_app
from app.extensions import db
from app.models import BenchmarkPrice
import yfinance as yf

app = create_app()
with app.app_context():
    # 1. Find suspicious values
    for bp in BenchmarkPrice.query.filter_by(ticker='EEMS').all():
        price = float(bp.close_price)
        if price > 100 or price < 30:  # EEMS range: 40-80
            print(f'Corrupted: {bp.date} = {price}')
    
    # 2. Verify against real market data
    ticker = yf.Ticker('EEMS')
    hist = ticker.history(start='2024-11-01', end='2025-01-15')
    print(hist[['Close']])
    
    # 3. Clean if needed
    # for bp in BenchmarkPrice.query.filter_by(ticker='EEMS').all():
    #     if float(bp.close_price) > 100:
    #         db.session.delete(bp)
    # db.session.commit()
"
```

### Why This Approach Works
- **Uses existing `.env`** - No manual credential setup
- **Direct DB access** - See actual production data
- **Fast iteration** - Quick sanity checks
- **Safe** - Can inspect before modifying
- **No credential leaks** - `.env` stays in `.gitignore`

---

## ⚠️ Critical Rules

### Security
- **NEVER** commit `.env` (already gitignored)
- **NEVER** hardcode secrets
- Always use `@login_required` for protected routes
- All forms must use Flask-WTF (CSRF protection)

### Database
- Use `db.session.commit()` after changes
- Use `db.session.rollback()` on errors
- Check records exist before accessing (`.first()` can return `None`)

### Code Style
- 4 spaces, PEP 8
- Type hints encouraged
- Max ~100 chars per line
- Docstrings for non-trivial functions

---

## 🚨 Common Issues

| Issue | Fix |
|-------|-----|
| "No module named 'flask'" | `source venv/bin/activate` (venv is Python 3.12) |
| "Unable to open database file" | `mkdir -p instance && chmod 755 instance` |
| "The CSRF token is missing" | A POST form has no `csrf_token` input. Every POST form needs one; `base.html` also injects it at submit time as a safety net. See `tests/test_templates.py` |
| Port 5000 in use | `flask run --port=5001` (macOS AirPlay holds 5000) |
| Database locked (SQLite) | Close all terminals, reopen, retry |
| "No such function: stddev" | SQLite has no `stddev()`; aggregate in Python instead (see `presentation_export.py`) |
| Text renders as `<<` or tag fragments | A template tag was mangled by a bulk edit. `tests/test_templates.py` catches this |
| Language switch does nothing | `window.LANG` must only be defined in `static/js/i18n.js` |
| App will not boot after a rebuild | `requirements.txt` must keep `SQLAlchemy<2.1` (2.1 wants psycopg3, which is not installed) |

---

## 📋 Pre-Flight Checklist

Before suggesting changes, verify:
- [ ] Using `./run-local.sh` (local SQLite), not raw `.env` (production DB)
- [ ] New imports at top of file
- [ ] Database ops use SQLAlchemy ORM
- [ ] Forms use Flask-WTF with CSRF
- [ ] New user-facing text has `data-i18n`/`data-i18n-html` **and** a Czech entry
- [ ] `venv/bin/python -m pytest -q` passes
- [ ] No hardcoded secrets
- [ ] Error handling included
- [ ] Follows existing code style

---

## 🔗 Key Dependencies

- **Flask** - Web framework
- **Flask-SQLAlchemy** + **SQLAlchemy** (pinned `<2.1`) - ORM
- **Flask-Login** - Sessions
- **yahooquery** - the finance API actually used (prices, ticker search)
- **DeepSeek / Brave Search** - optional, for ticker resolution
- **pandas** / **numpy** / **matplotlib** - data and charts
- **pytest** - Testing

Note: `app/utils/yfinance_helper.py` is dead code — it imports `yfinance`, which
is not a dependency any more, so importing it raises. Nothing in `app/` imports
it; only some old test scripts did.

---

## 🌐 WebFlow Integration

The application supports integration with WebFlow-designed site shells.

### Quick Links
- Documentation: [docs/WEBFLOW_INTEGRATION.md](docs/WEBFLOW_INTEGRATION.md)
- Shell Template: `app/templates/webflow_shell.html`
- Integration Module: `app/webflow_integration.py`
- Route Helpers: `app/routes_webflow.py`

### Usage
1. Set `WEBFLOW_SHELL_URL` in `.env`
2. Add `<div id="flask-content-injection-point">` to your WebFlow site
3. Include the JavaScript injection snippet
4. Access pages with `?_embed=body` for body-only content

---

**Last Updated:** 2026-09-27  
**Location:** `/AGENTS.md` (project root)

---

## 📌 Known open items

Left deliberately undone, with context:

1. **The 1-year portfolio chart** only counts positions that *entered* within the
   last 365 days (`get_portfolio_series`, `_build_analyst_series`,
   `unified_calculator._calculate_series_for_analyses`). A portfolio whose
   positions are all older shows an empty panel with a placeholder. Whether it
   should instead show each holding's return *over* the window (using the price
   at the window start) is a product decision that changes displayed numbers on
   the Board, Overview and per-analyst pages.
2. **`is_other_event()`** is a keyword list and misses real non-stock rows
   ("Investor Insight Evening", "Valuation workshop", Czech names). They surface
   as "missing ticker", which is visible and manually fixable. DeepSeek's
   `classify_stock()` already returns `False` for them, so wiring it into the
   resolution flow would improve this.
3. **AI ticker hallucination.** The raw helper can invent a symbol for a made-up
   company (observed: `ADRS` for `NonexistentCompanyXYZ12345`). `resolve_ticker()`
   catches it because `_validate_ticker()` requires real price data — but a
   hallucinated symbol that *does* trade would pass and be attached to the wrong
   company. There is no cross-check between the resolved ticker's name and the
   requested name.
4. **`i18n.js` is ~120 KB** and loads on every page including the dashboard.
5. **Only 4 Vote rows exist in production**, so just 3 of 28 "On Watchlist"
   analyses count as Board-approved. The Board 1-year chart is empty because of
   that, not because of a bug.
