# AI Agent Context: Analyst Website

> **Quick Start for AI Coding Assistants**  
> Flask 2.3.3 | SQLAlchemy ORM | Bootstrap 5 + Tailwind | SQLite (dev) / PostgreSQL (prod)

---

## ⚡ Critical First Steps

### 1. Always Activate Virtual Environment
```bash
source venv/bin/activate  # Every new terminal session
```

### 2. Run Python Commands with App Context
```bash
# One-liner for database queries
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
flask run --port=5001       # If 5000 is taken
flask init-db               # Create tables (safe, non-destructive)
flask create-admin          # Interactive admin user creation
pytest                      # Run tests
```

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
| "No module named 'flask'" | `source venv/bin/activate` |
| "Unable to open database file" | `mkdir -p instance && chmod 755 instance` |
| "CSRF token missing" | Check SECRET_KEY in `.env` |
| Port 5000 in use | `flask run --port=5001` |
| Database locked (SQLite) | Close all terminals, reopen, retry |

---

## 📋 Pre-Flight Checklist

Before suggesting changes, verify:
- [ ] Virtual environment activated
- [ ] New imports at top of file
- [ ] Database ops use SQLAlchemy ORM
- [ ] Forms use Flask-WTF with CSRF
- [ ] No hardcoded secrets
- [ ] Error handling included
- [ ] Follows existing code style

---

## 🔗 Key Dependencies

- **Flask** - Web framework
- **SQLAlchemy** - ORM
- **Flask-Login** - Sessions
- **yahooquery** - Yahoo Finance API
- **yfinance** - Alternative finance API (data validation)
- **pandas** - Data manipulation
- **pytest** - Testing

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

**Last Updated:** 2026-02-10  
**Location:** `/AGENTS.md` (project root)
