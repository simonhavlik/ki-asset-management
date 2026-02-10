# AI Coding Assistant Orientation

> **Quick Reference for AI Tools (Roo Code, Cursor, Claude, etc.)**

This document helps AI coding assistants understand the project structure, environment setup, and common operations.

---

## 🎯 Essential Context

**Project Type:** Flask Web Application (Python 3.10+)
**Framework:** Flask 2.3.3 with SQLAlchemy ORM
**Database:** SQLite (dev) / PostgreSQL (prod via neon.tech)
**Frontend:** Bootstrap 5 + Tailwind CSS + Jinja2 Templates

**Key Principle:** Always activate the virtual environment before running any Python commands.

---

## 🚀 Quick Start for AI Assistants

### 1. Environment Setup

```bash
# ALWAYS run this first in every new terminal/session
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate     # Windows

# Verify you're in the venv
which python  # Should show: /path/to/venv/bin/python
```

### 2. Running the Application

```bash
# Development mode
flask run

# With custom port (if 5000 is taken)
flask run --port=5001

# Production mode (uses gunicorn)
gunicorn "app:create_app()"
```

### 3. Database Operations

```bash
# Initialize/create tables
flask init-db

# Create admin user (interactive)
flask create-admin

# Reset database (WARNING: deletes all data)
rm instance/analyst.db  # Linux/Mac
# OR manually delete instance/analyst.db on Windows
flask init-db
flask create-admin
```

---

## 📁 Project Structure

```
analyst_website/
├── app/                          # Main Flask application
│   ├── __init__.py              # App factory, CLI commands
│   ├── config.py                # Environment configurations
│   ├── extensions.py            # Flask extensions (db, login, mail, cache)
│   ├── models.py                # SQLAlchemy database models
│   ├── email_service.py         # Email service abstraction
│   ├── security.py              # Security headers, rate limiting
│   ├── scheduler.py             # Background task scheduler
│   │
│   ├── auth/                    # Authentication blueprint
│   │   ├── routes.py            # Login, logout, register, reset
│   │   ├── forms.py             # WTForms classes
│   │   └── utils.py             # Token generation, email
│   │
│   ├── admin/                   # Admin panel blueprint
│   │   ├── routes.py            # Admin dashboard, CSV upload
│   │   └── forms.py             # Admin forms
│   │
│   ├── analyst/                 # Analyst dashboard blueprint
│   │   └── routes.py            # Personal performance views
│   │
│   ├── main/                    # Public pages blueprint
│   │   └── routes.py            # Landing page, about, terms
│   │
│   ├── blog/                    # Blog system blueprint
│   │   └── routes.py            # Blog posts, AI features
│   │
│   ├── utils/                   # Utility modules
│   │   ├── csv_import.py        # CSV parsing & import
│   │   ├── performance.py       # Performance calculations
│   │   ├── yahooquery_helper.py # Yahoo Finance integration
│   │   ├── ticker_resolver.py   # AI ticker matching
│   │   ├── brave_search.py      # Web search fallback
│   │   ├── deepseek_client.py   # DeepSeek AI integration
│   │   └── blog_ai_utils.py     # Blog AI features
│   │
│   ├── templates/               # Jinja2 HTML templates
│   │   ├── base.html            # Base layout
│   │   ├── main/                # Public pages
│   │   ├── auth/                # Auth pages
│   │   ├── admin/               # Admin panel
│   │   ├── analyst/             # Analyst dashboard
│   │   └── blog/                # Blog templates
│   │
│   └── static/                  # Static assets
│       ├── css/                 # Stylesheets
│       ├── js/                  # JavaScript
│       └── images/              # Images, logos
│
├── instance/                    # Instance-specific data (gitignored)
│   ├── analyst.db               # SQLite database
│   └── overview_cache/          # Cached public data
│
├── tests/                       # Test suite
├── scripts/                     # Utility scripts
├── migrations/                  # Database migrations (if using Alembic)
├── docs/                        # Documentation
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
├── .env                         # Local environment (gitignored)
└── render_start.py             # Production startup script
```

---

## 🔧 Key Files for AI Understanding

### Configuration
- `app/config.py` - Environment-based configuration (dev/prod)
- `.env` - Local environment variables (never commit this)
- `.env.example` - Template showing all available variables

### Database Models (`app/models.py`)
Key models to understand:
- `User` - User accounts with roles (admin/analyst)
- `Analysis` - Stock analysis records
- `Company` - Company information with ticker symbols
- `PerformanceCalculation` - Cached performance metrics
- `BoardVote` - Board voting records
- `BlogPost` - Blog articles with SEO fields
- `Idea` / `IdeaComment` - Public wall feature

### Important Utilities
- `app/utils/performance.py` - Core performance calculation logic
- `app/utils/csv_import.py` - CSV parsing and data import
- `app/utils/ticker_resolver.py` - AI-powered ticker matching
- `app/utils/yahooquery_helper.py` - Stock price fetching

---

## 🧪 Testing Guidelines

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test
pytest tests/test_performance.py

# Run with verbose output
pytest -v
```

**Test Location:** All tests in `tests/` directory, named `test_*.py`

---

## 💡 Common Operations

### Adding a New Route

```python
# In appropriate blueprint (e.g., app/main/routes.py)
@main_bp.route('/new-page')
def new_page():
    """Description of what this page does."""
    data = SomeModel.query.all()
    return render_template('main/new_page.html', data=data)
```

```html
<!-- Create template: app/templates/main/new_page.html -->
{% extends "base.html" %}
{% block title %}New Page - KI Asset Management{% endblock %}
{% block content %}
<div class="container">
    <h1>New Page</h1>
    <!-- Content here -->
</div>
{% endblock %}
```

### Adding a Database Model

```python
# In app/models.py
class NewModel(db.Model):
    __tablename__ = 'new_models'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<NewModel {self.name}>'
```

Then run: `flask init-db` (creates new tables without deleting existing data)

### Adding a Form

```python
# In appropriate forms.py file
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

class MyForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    submit = SubmitField('Submit')
```

---

## ⚠️ Important Rules

### Security
- **Never** hardcode secrets in code
- Always use `current_app.config` for sensitive values
- All forms must use Flask-WTF with CSRF protection
- Validate all user inputs
- Use parameterized queries (SQLAlchemy ORM)

### Database
- Use `db.session.add()` + `db.session.commit()` for changes
- Use `db.session.rollback()` on errors
- Always check if records exist before creating
- Use relationships properly (e.g., `user.analyses`)

### Environment
- Check `FLASK_ENV` before enabling debug features
- Use `current_app.logger` for logging, not print()
- Cache expensive operations appropriately

### Code Style
- Follow PEP 8 (4 spaces, max 100 chars)
- Use type hints where helpful
- Write docstrings for functions
- Keep functions under 50 lines when possible

---

## 🔍 Debugging Tips

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check current config
from flask import current_app
print(current_app.config)

# Inspect database
from app.extensions import db
print(db.engine.table_names())

# Check routes
flask routes
```

---

## 📚 Key Dependencies

| Package | Purpose |
|---------|---------|
| Flask | Web framework |
| Flask-SQLAlchemy | ORM for database |
| Flask-Login | User session management |
| Flask-WTF | Forms with CSRF protection |
| Flask-Mail / SendGrid | Email sending |
| Flask-Caching | In-memory caching |
| yahooquery | Yahoo Finance API |
| gunicorn | WSGI server (production) |
| pytest | Testing framework |

---

## 🆘 Troubleshooting Common Issues

**"No module named 'flask'"**
→ Virtual environment not activated. Run: `source venv/bin/activate`

**"Unable to open database file"**
→ Create instance directory: `mkdir -p instance && chmod 755 instance`

**"CSRF token missing"**
→ SECRET_KEY not set in .env. Generate one: `python -c "import secrets; print(secrets.token_hex(32))"`

**"Port 5000 already in use"**
→ Use different port: `flask run --port=5001`

**Database locked (SQLite)**
→ Close all terminal windows, reopen, try again. Or use PostgreSQL.

---

## 📝 AI Assistant Checklist

Before suggesting code changes, verify:

- [ ] Virtual environment is activated
- [ ] Import statements are at top of file
- [ ] Models properly imported from `app.models`
- [ ] Blueprints properly imported
- [ ] Database operations use SQLAlchemy ORM
- [ ] Forms use Flask-WTF with CSRF
- [ ] No hardcoded secrets or credentials
- [ ] Proper error handling included
- [ ] Code follows existing style patterns

---

## 🔗 Quick Links

- [Main Documentation](../README.md)
- [Development Guide](development/README.md)
- [Deployment Guide](deployment/README.md)
- [Troubleshooting](operations/troubleshooting.md)

---

**Last Updated:** 2026-02-07  
**Maintained by:** AI Coding Assistants & Development Team
