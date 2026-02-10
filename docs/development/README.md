# Development Guide

Welcome, developers! This guide covers everything you need to contribute to KI Asset Management.

---

## 🚀 Quick Start for Developers

```bash
# 1. Clone and setup
git clone <repo-url>
cd analyst_website
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 2. Configure
# Edit .env: Set SECRET_KEY, USE_LOCAL_SQLITE=True

# 3. Initialize
flask init-db
flask create-admin

# 4. Run with auto-reload
flask run --debug
```

---

## 📁 Project Structure

```
app/
├── __init__.py           # App factory, CLI commands
├── config.py             # Environment configurations
├── extensions.py         # Flask extensions (db, login, mail)
├── models.py             # SQLAlchemy database models
├── email_service.py      # Email service abstraction
├── security.py           # Security headers, rate limiting
├── scheduler.py          # Background tasks
│
├── auth/                 # Authentication blueprint
│   ├── routes.py         # Login, logout, register
│   ├── forms.py          # WTForms classes
│   └── utils.py          # Token generation
│
├── admin/                # Admin panel blueprint
│   ├── routes.py         # Admin dashboard, CSV upload
│   └── forms.py          # Admin forms
│
├── analyst/              # Analyst dashboard blueprint
│   └── routes.py         # Personal performance views
│
├── main/                 # Public pages blueprint
│   └── routes.py         # Landing page, about
│
├── blog/                 # Blog system blueprint
│   └── routes.py         # Blog posts, AI features
│
├── utils/                # Utility modules
│   ├── csv_import.py     # CSV parsing
│   ├── performance.py    # Performance calculations
│   ├── yahooquery_helper.py  # Stock prices
│   ├── ticker_resolver.py    # AI ticker matching
│   ├── brave_search.py       # Web search
│   ├── deepseek_client.py    # DeepSeek AI
│   └── blog_ai_utils.py      # Blog AI features
│
├── templates/            # Jinja2 HTML templates
└── static/               # Static assets (CSS, JS, images)
```

---

## 🔄 Development Workflow

### Daily Development Cycle

```bash
# 1. Pull latest changes
git pull origin main

# 2. Create feature branch
git checkout -b feature/my-feature

# 3. Make changes
# Edit files, test locally with: flask run

# 4. Run tests
pytest

# 5. Commit changes
git add .
git commit -m "feat: Add new feature"

# 6. Push and create PR
git push origin feature/my-feature
# Create Pull Request on GitHub
```

### Branch Naming

```
feature/description      # New features
bugfix/description       # Bug fixes
hotfix/description       # Critical fixes
docs/description         # Documentation
test/description         # Tests
refactor/description     # Refactoring
```

---

## 📝 Code Style

### Python

- **PEP 8** compliant
- Max 100 characters per line
- 4 spaces indentation
- Single quotes for strings
- Docstrings for all functions

```python
# ✅ Good
def calculate_return(price_buy: float, price_now: float) -> float:
    """
    Calculate percentage return between two prices.
    
    Args:
        price_buy: Price when stock was purchased
        price_now: Current market price
        
    Returns:
        Percentage return (e.g., 10.5 for 10.5%)
    """
    if price_buy == 0:
        return 0.0
    return ((price_now - price_buy) / price_buy) * 100
```

### HTML/Jinja2

```html
<!-- ✅ Good -->
<div class="card analyst-card">
    <div class="card-header">
        <h2 class="card-title">Performance</h2>
    </div>
    <div class="card-body">
        {% if data %}
            <table class="table">
                <!-- Content -->
            </table>
        {% else %}
            <p class="text-muted">No data available.</p>
        {% endif %}
    </div>
</div>
```

### CSS

```css
/* ✅ Good - BEM naming */
.analyst-card {
    padding: 1.5rem;
    margin-bottom: 1rem;
    border-radius: 0.75rem;
    background: linear-gradient(135deg, #fff 0%, #f8f9fa 100%);
}

.analyst-card__title {
    font-weight: 600;
    color: #212529;
}
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test
pytest tests/test_performance.py

# Run specific function
pytest tests/test_performance.py::test_calculate_return

# Verbose output
pytest -v
```

### Writing Tests

```python
# tests/test_example.py
import pytest
from app.utils.performance import calculate_return


def test_calculate_return_positive():
    """Test positive return calculation."""
    result = calculate_return(100.0, 110.0)
    assert result == 10.0


def test_calculate_return_negative():
    """Test negative return calculation."""
    result = calculate_return(100.0, 90.0)
    assert result == -10.0
```

---

## 🏗️ Common Tasks

### Adding a New Route

```python
# app/main/routes.py
@main_bp.route('/new-page')
def new_page():
    """Description of the page."""
    data = SomeModel.query.all()
    return render_template('main/new_page.html', data=data)
```

```html
<!-- app/templates/main/new_page.html -->
{% extends "base.html" %}
{% block title %}New Page - KI Asset Management{% endblock %}
{% block content %}
<div class="container">
    <h1>New Page</h1>
</div>
{% endblock %}
```

### Adding a Database Model

```python
# app/models.py
class NewModel(db.Model):
    __tablename__ = 'new_models'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<NewModel {self.name}>'
```

Then run: `flask init-db` (adds new tables without deleting data)

### Adding a Form

```python
# app/auth/forms.py (or appropriate forms.py)
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

class MyForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    submit = SubmitField('Submit')
```

---

## 🔐 Security Guidelines

### Do's

✅ Use Flask-WTF for all forms (CSRF protection)  
✅ Validate all user inputs  
✅ Use SQLAlchemy ORM (prevents SQL injection)  
✅ Store secrets in environment variables  
✅ Use `current_app.logger` for logging  
✅ Implement rate limiting on sensitive endpoints  

### Don'ts

❌ Never hardcode secrets in code  
❌ Never trust user input  
❌ Never use raw SQL with string formatting  
❌ Never commit `.env` files  
❌ Never expose stack traces in production  

---

## 🐛 Debugging

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

## 📚 Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Flask Mega-Tutorial](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world)
- [SQLAlchemy Docs](https://docs.sqlalchemy.org/)
- [Bootstrap 5 Docs](https://getbootstrap.com/docs/5.3/)

---

## 🤝 Contributing

See [Contributing Guide](contributing.md) for:
- Pull request process
- Code review checklist
- Git workflow
- Commit message format

---

## 🆘 Getting Help

- Check [AI Orientation](../AI-ORIENTATION.md) for technical reference
- Review [Troubleshooting](../operations/troubleshooting.md)
- Ask in team channels
