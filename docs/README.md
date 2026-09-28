# 📚 Documentation Hub

<p align="center">
  <a href="https://flask.palletsprojects.com/">
    <img src="https://img.shields.io/badge/Flask-2.3.3-blue?style=for-the-badge&logo=flask" alt="Flask">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge&logo=python" alt="Python">
  </a>
  <img src="https://img.shields.io/badge/License-Internal-orange?style=for-the-badge" alt="License">
</p>

<p align="center">
  <strong>Complete documentation for the Prague Club of Investors Analyst Performance Tracker</strong>
</p>

---

## 🚀 Quick Navigation

<div align="center">

| 🎯 **Getting Started** | 🚢 **Deployment** | 💻 **Development** |
|:---:|:---:|:---:|
| [Installation](getting-started/installation.md) | [Overview](deployment/README.md) | [Contributing](development/contributing.md) |
| [First Steps](getting-started/first-steps.md) | [Render](deployment/render.md) | [Architecture](development/architecture.md) |
| [Quick Reference](reference/README.md) | [Koyeb](deployment/koyeb.md) | [AI Coding Tools](../AGENTS.md) |

| 📖 **User Guides** | 🔧 **Operations** | 📋 **Reference** |
|:---:|:---:|:---:|
| [Admin Panel](user-guides/admin.md) | [Security](operations/security.md) | [Environment Variables](reference/environment-variables.md) |
| [Analyst Dashboard](user-guides/analyst.md) | [Troubleshooting](operations/troubleshooting.md) | [Database Schema](reference/database-schema.md) |
| [Blog System](user-guides/blog.md) | [Monitoring](operations/monitoring.md) | [API Endpoints](reference/api-endpoints.md) |

</div>

---

## 🎓 Start Here

**New to the project?** Choose your path:

<div align="center">

| 👤 **I'm an Investor** | 👨‍💻 **I'm a Developer** | 🤖 **I'm an AI Assistant** |
|:---:|:---:|:---:|
| Start with [User Guides](user-guides/README.md) | Check [Development](development/README.md) | Read the [AI agent guide](../AGENTS.md) |
| Learn the [Blog System](user-guides/blog.md) | Set up [Locally](getting-started/installation.md) | See [Project Structure](../AGENTS.md#-key-project-structure) |
| Understand [Performance Tracking](user-guides/analyst.md) | Review [Architecture](development/architecture.md) | Learn [Common Operations](../AGENTS.md) |

</div>

---

## 📊 Project Overview

**KI Asset Management** is a production-grade web application for tracking and comparing investment analyst performance at the Prague Club of Investors (Klub Investorů).

### ✨ Key Features

- **📊 Performance Tracking** - Real-time stock prices with benchmark comparisons
- **🗳️ Board Voting** - Democratic portfolio construction with voting system  
- **🤖 AI-Assisted Workflows** - Smart ticker matching and content generation
- **📝 Blog System** - SEO-optimized content with AI-powered article generation
- **🔐 Enterprise Security** - CSRF protection, rate limiting, domain-restricted access

---

## 🛠️ Tech Stack

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend: Bootstrap 5 + Tailwind CSS + Jinja2 Templates    │
├─────────────────────────────────────────────────────────────┤
│  Backend: Flask 2.3.3 + SQLAlchemy ORM                      │
├─────────────────────────────────────────────────────────────┤
│  Database: SQLite (dev) / PostgreSQL (production)           │
├─────────────────────────────────────────────────────────────┤
│  APIs: Yahoo Finance, DeepSeek AI, Brave Search, Unsplash   │
├─────────────────────────────────────────────────────────────┤
│  Deployment: Render + self-hosted PostgreSQL / Docker       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Documentation Structure

```
docs/
└── (AI guidance lives at the repo root: AGENTS.md)
├── 📁 getting-started/            # Installation & first steps
├── 📁 deployment/                 # Deployment guides
├── 📁 development/                # Developer documentation
├── 📁 user-guides/                # End-user documentation
├── 📁 operations/                 # Maintenance & operations
└── 📁 reference/                  # API & technical reference
```

---

## 🎯 Mission & Vision

**Investment Objective:** Outperforming **EEMS** (MSCI Emerging Markets Index) through disciplined, research-driven stock selection.

### Our Values

| Value | Description |
|-------|-------------|
| 🧘 **Patience** | Long-term thinking over short-term speculation |
| 🔮 **Foresight** | Anticipating market trends before they materialize |
| 🛡️ **Integrity** | Transparent analysis and honest reporting |

---

## 🚦 Quick Commands

```bash
# Setup (first time)
git clone <repo-url>
cd analyst_website
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp .env.example .env

# Initialize
flask init-db
flask create-admin

# Run locally
flask run

# Run tests
pytest
```

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](development/contributing.md) for:

- Code style guidelines
- Git workflow
- Pull request process
- Testing requirements

---

## 📞 Support

- **Technical Issues:** Check [Troubleshooting](operations/troubleshooting.md)
- **Deployment Help:** See [Deployment Guides](deployment/README.md)
- **Security:** Review [Security Policy](operations/security.md)

---

<p align="center">
  <strong>Built with 💚 by the Prague Club of Investors</strong><br>
  <em>Empowering the next generation of investment professionals</em>
</p>

<p align="center">
  <a href="reference/changelog.md">Changelog</a> •
  <a href="operations/security.md">Security</a> •
  <a href="development/contributing.md">Contributing</a>
</p>
