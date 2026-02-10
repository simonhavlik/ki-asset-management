# Contributing Guide

Welcome to the Prague Club of Investors Analyst Performance Tracker project! This guide will help you contribute effectively, even if you're new to web development.

---

## 📋 Table of Contents

1. [Getting Started](#getting-started)
2. [Development Workflow](#development-workflow)
3. [Code Style](#code-style)
4. [Git Workflow](#git-workflow)
5. [Testing](#testing)
6. [Pull Request Process](#pull-request-process)
7. [Common Tasks](#common-tasks)
8. [Troubleshooting](#troubleshooting)

---

## 🚀 Getting Started

### Prerequisites Checklist

Before you start, ensure you have:

- [ ] Python 3.10+ installed (`python --version`)
- [ ] Git installed (`git --version`)
- [ ] A code editor (VS Code recommended)
- [ ] Access to the repository

### First-Time Setup

```bash
# 1. Clone the repository
git clone <repository-url>
cd analyst_website

# 2. Create your own branch
git checkout -b your-name/feature-name

# 3. Set up the environment (see README.md)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 4. Copy environment file
cp .env.example .env

# 5. Initialize database
flask init-db
flask create-admin

# 6. Run the app
flask run
```

---

## 🔄 Development Workflow

### Daily Development Cycle

```
1. Pull latest changes:     git pull origin main
2. Create feature branch:   git checkout -b feature/my-feature
3. Make changes
4. Test locally:            flask run
5. Commit changes:          git add . && git commit -m "message"
6. Push to remote:          git push origin feature/my-feature
7. Create Pull Request
8. Code review
9. Merge to main
```

### File Organization Rules

**Where to put new code:**

| If you want to... | Go to... |
|-------------------|----------|
| Add a new page | `app/templates/` (HTML) + `app/XXX/routes.py` (Python) |
| Add a database table | `app/models.py` |
| Add a utility function | `app/utils/` |
| Add CSS styles | `app/static/css/style.css` |
| Add JavaScript | `app/static/js/app.js` |
| Add images | `app/static/images/` |

---

## 📝 Code Style

### Python Code Style

We follow **PEP 8** with some modifications:

```python
# ✅ GOOD: Clear variable names, docstrings, type hints
def calculate_return(price_at_buy: float, price_now: float) -> float:
    """
    Calculate percentage return between two prices.
    
    Args:
        price_at_buy: Price when stock was purchased
        price_now: Current market price
        
    Returns:
        Percentage return (e.g., 10.5 for 10.5%)
    """
    if price_at_buy == 0:
        return 0.0
    return ((price_now - price_at_buy) / price_at_buy) * 100


# ❌ BAD: Unclear names, no documentation
def calc(p1, p2):
    return ((p2 - p1) / p1) * 100
```

**Key Rules:**
- **Line length**: Max 100 characters
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Use single quotes for strings
- **Imports**: Group as: stdlib → third-party → local
- **Functions**: Max 50 lines, use docstrings

### HTML/Jinja2 Templates

```html
<!-- ✅ GOOD: Proper indentation, meaningful classes -->
<div class="card analyst-performance-card">
    <div class="card-header">
        <h2 class="card-title">Performance Overview</h2>
    </div>
    <div class="card-body">
        {% if analyst_performance %}
            <table class="table">
                <thead>
                    <tr>
                        <th>Analyst</th>
                        <th>Return %</th>
                    </tr>
                </thead>
                <tbody>
                    {% for analyst in analyst_performance %}
                        <tr>
                            <td>{{ analyst.name }}</td>
                            <td>{{ analyst.return_pct }}%</td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p class="text-muted">No data available.</p>
        {% endif %}
    </div>
</div>

<!-- ❌ BAD: Poor indentation, inline styles -->
<div class="card" style="margin:10px">
<div style="font-weight:bold">Performance</div>
<table>
<tr><td>{{analyst.name}}</td></tr>
</table>
</div>
```

### CSS Guidelines

```css
/* ✅ GOOD: BEM naming, organized properties */
.analyst-card {
    /* Positioning */
    position: relative;
    
    /* Box Model */
    padding: 1.5rem;
    margin-bottom: 1rem;
    border-radius: 0.75rem;
    
    /* Visual */
    background: linear-gradient(135deg, #fff 0%, #f8f9fa 100%);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    
    /* Typography */
    font-size: 1rem;
    line-height: 1.5;
}

.analyst-card__title {
    font-weight: 600;
    color: #212529;
}

.analyst-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 12px rgba(0, 0, 0, 0.15);
}

/* ❌ BAD: Poor naming, disorganized */
.card {
    padding:10px;
    background:white;
    border:1px solid gray;
    font-family:Arial;
}
```

---

## 🌿 Git Workflow

### Branch Naming Convention

```
feature/description      # New features
bugfix/description       # Bug fixes
hotfix/description       # Critical fixes
docs/description         # Documentation
test/description         # Test-related
refactor/description     # Code refactoring
```

Examples:
```bash
git checkout -b feature/portfolio-csv-export
git checkout -b bugfix/chart-alignment
git checkout -b docs/deployment-guide
```

### Commit Message Format

```
type: Brief description (max 50 chars)

Longer explanation if needed (wrap at 72 chars).
Can include multiple paragraphs.

- Bullet points are okay
- Reference issues: Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style changes (formatting, semicolons)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

Examples:
```bash
git commit -m "feat: Add portfolio CSV export functionality"
git commit -m "fix: Align chart starting points for benchmark comparison"
git commit -m "docs: Add deployment instructions for Heroku"
```

### Git Commands Cheat Sheet

```bash
# Check status
git status

# See what changed
git diff

# Stage changes
git add filename.py          # Specific file
git add .                    # All changes

# Commit
git commit -m "feat: description"

# Push
git push origin branch-name

# Pull latest changes
git pull origin main

# Switch branches
git checkout branch-name

# Create and switch
git checkout -b new-branch

# See commit history
git log --oneline --graph

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Discard all changes
git checkout -- .
```

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest test_performance.py

# Run specific test function
pytest test_performance.py::test_calculate_return

# Run with coverage report
pytest --cov=app --cov-report=html
# Then open htmlcov/index.html in browser
```

### Writing Tests

```python
# tests/test_performance.py
import pytest
from app.utils.performance import PerformanceCalculator


def test_calculate_return_positive():
    """Test positive return calculation."""
    calc = PerformanceCalculator()
    result = calc.calculate_return(100.0, 110.0)
    assert result == 10.0


def test_calculate_return_negative():
    """Test negative return calculation."""
    calc = PerformanceCalculator()
    result = calc.calculate_return(100.0, 90.0)
    assert result == -10.0


def test_calculate_return_zero_division():
    """Test handling of zero buy price."""
    calc = PerformanceCalculator()
    result = calc.calculate_return(0.0, 100.0)
    assert result == 0.0
```

---

## 🔀 Pull Request Process

### Before Creating a PR

1. **Test your changes locally**
   ```bash
   flask run
   # Test all affected pages
   ```

2. **Check code style**
   ```bash
   # Python linting (if flake8 installed)
   flake8 app/
   ```

3. **Update documentation** if needed
   - README.md for user-facing changes
   - This file for developer changes

4. **Write a clear PR description**:
   ```markdown
   ## Summary
   Brief description of what this PR does.

   ## Changes
   - List specific changes made
   - Another change

   ## Testing
   - How you tested this
   - What scenarios you checked

   ## Screenshots
   (If UI changes)

   ## Related Issues
   Fixes #123
   ```

### PR Review Checklist

For **reviewers**:
- [ ] Code follows style guidelines
- [ ] Changes are properly tested
- [ ] Documentation is updated
- [ ] No security issues
- [ ] Performance is acceptable

For **authors**:
- [ ] Tests pass locally
- [ ] No console errors
- [ ] Works on mobile/desktop
- [ ] Self-reviewed the code

---

## 🛠️ Common Tasks

### Adding a New Page

```python
# app/main/routes.py
@main_bp.route('/new-page')
def new_page():
    """Description of the page."""
    data = fetch_data()  # Get data from database
    return render_template('main/new_page.html', data=data)
```

```html
<!-- app/templates/main/new_page.html -->
{% extends "base.html" %}

{% block title %}New Page - Analyst Tracker{% endblock %}

{% block content %}
<div class="container">
    <h1>New Page Title</h1>
    <!-- Content here -->
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

Then run:
```bash
flask init-db  # Creates tables
```

### Adding a New API Endpoint

```python
# app/admin/routes.py
@admin_bp.route('/api/new-endpoint')
@admin_required
def new_api_endpoint():
    """API endpoint description."""
    data = {
        'key': 'value',
        'count': 42
    }
    return jsonify(data)
```

### Adding Static Files

```bash
# CSS
app/static/css/custom.css

# JavaScript  
app/static/js/features.js

# Images
app/static/images/team/photo.jpg
```

Reference in templates:
```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/custom.css') }}">
<script src="{{ url_for('static', filename='js/features.js') }}"></script>
<img src="{{ url_for('static', filename='images/team/photo.jpg') }}">
```

### Working with Blog AI Features

#### Adding New Document Processing Styles

When adding a new AI document style (like `investment_pitch`):

```python
# app/utils/blog_ai_utils.py
style_instructions = {
    'your_new_style': """Describe the style transformation rules:
- Format requirements
- Tone guidelines
- Structure expectations""",
}

# Update validation in generate_article_from_document()
valid_styles = {'seo_article', 'academic_paper', 'blog_post', 'investment_pitch', 'your_new_style'}
```

#### Security Considerations for AI Endpoints

When modifying AI-powered endpoints, always include:

```python
# 1. Rate limiting to prevent abuse
@rate_limit(limit=10, window=3600)  # 10 requests per hour

# 2. Input length validation
if len(content) > 50000:
    return jsonify({'error': 'Content too long'}), 400

# 3. File size validation (for uploads)
max_file_size = 10 * 1024 * 1024  # 10MB
if file_size > max_file_size:
    return jsonify({'error': 'File too large'}), 400

# 4. File type validation
allowed_extensions = {'pdf', 'docx', 'doc'}
if ext not in allowed_extensions:
    return jsonify({'error': 'Invalid file type'}), 400
```

#### Testing AI Features Locally

1. **Set up API keys in `.env`:**
   ```bash
   DEEPSEEK_API_KEY=your_key_here
   UNSPLASH_API_KEY=your_key_here
   ```

2. **Test document upload:**
   - Use small PDF/DOCX files (< 1MB) for faster testing
   - Test each style (seo_article, investment_pitch, etc.)
   - Verify rate limiting works (try rapid requests)

3. **Test SEO generation:**
   - Test with various content lengths
   - Verify image gallery displays correctly
   - Check Unsplash attribution appears

---

## 🐛 Troubleshooting

### Common Issues

**Issue: "No module named 'flask'"**
```bash
# Solution: Activate virtual environment
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

**Issue: "Unable to open database file"**
```bash
# Solution: Create instance directory
mkdir -p instance
chmod 755 instance
```

**Issue: "CSRF token missing"**
```bash
# Solution: Set SECRET_KEY in .env
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> .env
```

**Issue: Port 5000 already in use**
```bash
# Solution: Use different port
flask run --port=5001
```

### Getting Help

1. Check this guide first
2. Search existing GitHub issues
3. Ask in the team Slack channel
4. Tag @simon-hruby for technical questions

---

## 📚 Learning Resources

### Python & Flask
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Flask Mega-Tutorial](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world)
- [Real Python Flask Tutorials](https://realpython.com/tutorials/flask/)

### Frontend
- [Bootstrap 5 Docs](https://getbootstrap.com/docs/5.3/)
- [Tailwind CSS](https://tailwindcss.com/)
- [MDN Web Docs](https://developer.mozilla.org/)

### Git
- [GitHub Git Cheat Sheet](https://education.github.com/git-cheat-sheet-education.pdf)
- [Oh Shit, Git!?!](https://ohshitgit.com/)

---

## ✅ Code Review Checklist

Use this when reviewing PRs:

```markdown
## Code Review

### Functionality
- [ ] Feature works as described
- [ ] Edge cases handled
- [ ] Error handling present

### Code Quality
- [ ] Clean, readable code
- [ ] Proper naming conventions
- [ ] No duplicated code
- [ ] Comments where needed

### Testing
- [ ] Tests included
- [ ] Tests pass
- [ ] Manual testing done

### Documentation
- [ ] README updated if needed
- [ ] Code comments clear
- [ ] PR description complete

### Security
- [ ] No hardcoded secrets
- [ ] Input validation present
- [ ] SQL injection prevented
```

---

**Remember**: When in doubt, ask! We're here to help each other learn and grow. 🚀
