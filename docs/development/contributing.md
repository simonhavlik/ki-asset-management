# Contributing Guide

Thank you for your interest in contributing to KI Asset Management! This guide will help you get started.

---

## 🚀 Quick Start

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/ki-asset-management.git
cd ki-asset-management

# 2. Setup environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 3. Initialize
flask init-db
flask create-admin

# 4. Create branch
git checkout -b feature/my-feature

# 5. Make changes and test
flask run
pytest

# 6. Commit and push
git add .
git commit -m "feat: Add new feature"
git push origin feature/my-feature

# 7. Create Pull Request on GitHub
```

---

## 🌿 Git Workflow

### Branch Naming Convention

```
feature/description      # New features
bugfix/description       # Bug fixes
hotfix/description       # Critical fixes
docs/description         # Documentation
test/description         # Tests
refactor/description     # Refactoring
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
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

Examples:
```bash
git commit -m "feat: Add portfolio CSV export functionality"
git commit -m "fix: Align chart starting points for benchmark comparison"
git commit -m "docs: Add deployment instructions for Heroku"
```

---

## 📝 Code Standards

### Python Style

- Follow **PEP 8**
- Max 100 characters per line
- 4 spaces indentation
- Use type hints where helpful
- Write docstrings for functions

```python
# ✅ Good
def calculate_return(price_buy: float, price_now: float) -> float:
    """Calculate percentage return between two prices."""
    if price_buy == 0:
        return 0.0
    return ((price_now - price_buy) / price_buy) * 100
```

### HTML Templates

- Use 4-space indentation
- Meaningful class names
- Proper Jinja2 syntax

```html
<!-- ✅ Good -->
<div class="card performance-card">
    {% if data %}
        <table class="table">
            <!-- Content -->
        </table>
    {% else %}
        <p class="text-muted">No data available.</p>
    {% endif %}
</div>
```

### CSS Guidelines

- Use BEM naming convention
- Group properties logically

```css
/* ✅ Good */
.analyst-card {
    padding: 1.5rem;
    margin-bottom: 1rem;
    border-radius: 0.75rem;
    background: #fff;
}

.analyst-card__title {
    font-weight: 600;
}
```

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test
pytest tests/test_performance.py

# Run specific function
pytest tests/test_performance.py::test_calculate_return
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


def test_calculate_return_zero_division():
    """Test handling of zero buy price."""
    result = calculate_return(0.0, 100.0)
    assert result == 0.0
```

---

## 🔀 Pull Request Process

### Before Creating a PR

1. **Test your changes locally**
   ```bash
   flask run
   pytest
   ```

2. **Check code style**
   ```bash
   flake8 app/
   ```

3. **Update documentation** if needed

4. **Write a clear PR description:**
   ```markdown
   ## Summary
   Brief description of what this PR does.

   ## Changes
   - List specific changes made
   - Another change

   ## Testing
   - How you tested this
   - What scenarios you checked

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

## 🐛 Common Issues

**Issue: "No module named 'flask'"**
```bash
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows
```

**Issue: "Unable to open database file"**
```bash
mkdir -p instance && chmod 755 instance
```

**Issue: "CSRF token missing"**
```bash
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> .env
```

---

## 📚 Learning Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Flask Mega-Tutorial](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world)
- [Bootstrap 5 Docs](https://getbootstrap.com/docs/5.3/)
- [GitHub Git Cheat Sheet](https://education.github.com/git-cheat-sheet-education.pdf)

---

## ✅ Code Review Template

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

## 💬 Questions?

- Check [Development Guide](README.md)
- Review [AI Orientation](../AI-ORIENTATION.md)
- Ask in team channels

**Remember**: When in doubt, ask! We're here to help each other learn and grow.
