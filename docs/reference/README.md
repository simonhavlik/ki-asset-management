# Reference

Quick reference documentation for KI Asset Management.

---

## 📚 Quick Reference Guides

| Guide | Purpose |
|-------|---------|
| **[Environment Variables](environment-variables.md)** | Complete .env reference |
| **[Database Schema](database-schema.md)** | Table structures and relationships |
| **[API Endpoints](api-endpoints.md)** | Available API routes |
| **[Changelog](changelog.md)** | Version history |

---

## 🚀 Quick Commands

### Development

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run
flask run
flask run --port=5001
flask run --debug

# Database
flask init-db
flask create-admin
flask shell

# Testing
pytest
pytest -v
pytest --cov=app
```

### Git

```bash
# Daily workflow
git pull origin main
git checkout -b feature/name
git add .
git commit -m "feat: description"
git push origin feature/name

# Useful commands
git status
git log --oneline
git diff
```

---

## 📊 Key Configuration

### Environment Variables

**Required:**
```bash
SECRET_KEY=your-secret-key
FLASK_ENV=production
USE_LOCAL_SQLITE=False
DATABASE_URL=postgresql://...
```

**Email (Choose one):**
```bash
# SendGrid (Production)
SENDGRID_API_KEY=SG.xxx
MAIL_DEFAULT_SENDER=admin@domain.com

# SMTP (Local)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=...
MAIL_PASSWORD=...
```

**Optional APIs:**
```bash
DEEPSEEK_API_KEY=...
BRAVE_SEARCH_API_KEY=...
UNSPLASH_API_KEY=...
```

---

## 🏗️ Project Structure

```
app/
├── __init__.py          # App factory
├── config.py            # Configuration
├── extensions.py        # Flask extensions
├── models.py            # Database models
├── email_service.py     # Email abstraction
├── security.py          # Security headers
├── scheduler.py         # Background tasks
├── auth/                # Authentication
├── admin/               # Admin panel
├── analyst/             # Analyst dashboard
├── main/                # Public pages
├── blog/                # Blog system
├── utils/               # Utilities
├── templates/           # HTML templates
└── static/              # CSS, JS, images
```

---

## 🔗 External Services

| Service | Purpose | Documentation |
|---------|---------|---------------|
| Yahoo Finance | Stock prices | yahooquery |
| DeepSeek | AI processing | platform.deepseek.com |
| Brave Search | Web search | api.search.brave.com |
| Unsplash | Images | unsplash.com/developers |
| SendGrid | Email | sendgrid.com |
| PostgreSQL 17 | Database | self-hosted (club VPS) |

---

## 📝 File Locations

| File Type | Location |
|-----------|----------|
| Config | `.env` (root) |
| Database | `instance/analyst.db` (dev) |
| Logs | Platform dependent |
| Uploads | `instance/` or temp |
| Static | `app/static/` |
| Templates | `app/templates/` |

---

## 🆘 Quick Help

**Issue? Check:**
1. [Troubleshooting](../operations/troubleshooting.md)
2. [AI Orientation](../../AGENTS.md)
3. [Deployment Guides](../deployment/)

**Need more?**
- See full documentation in sidebar
- Check specific guides above

---

<p align="center">
  <strong>Quick reference for common tasks</strong>
</p>
