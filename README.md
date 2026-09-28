# KI Asset Management

[![Flask](https://img.shields.io/badge/Flask-2.3.3-blue)](https://flask.palletsprojects.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-green)](https://www.python.org/)
![License](https://img.shields.io/badge/License-Internal-orange)

> **Production-grade analyst performance tracking for investment clubs**

A Flask web application for tracking and comparing investment analyst performance, featuring AI-assisted workflows, board voting, and comprehensive performance analytics.

---

## ✨ Features

- **📊 Performance Tracking** - Real-time stock prices with benchmark comparisons
- **🗳️ Board Voting** - Democratic portfolio construction with voting system
- **🤖 AI-Assisted Workflows** - Smart ticker matching and content generation
- **📝 Blog System** - SEO-optimized content with AI-powered article generation
- **🔐 Enterprise Security** - CSRF protection, rate limiting, domain-restricted access

---

## 🚀 Quick Start

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/ki-asset-management.git
cd ki-asset-management

# Setup environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp .env.example .env

# Configure
# Edit .env: Set SECRET_KEY and USE_LOCAL_SQLITE=True

# Initialize
flask init-db
flask create-admin

# Run
flask run
```

Visit: [http://127.0.0.1:5000](http://127.0.0.1:5000)

**Full setup guide:** [Getting Started](docs/getting-started/installation.md)

---

## 📚 Documentation

Comprehensive documentation is available in the `/docs` directory:

### [📖 Documentation Hub](docs/README.md)

| Section | Description |
|---------|-------------|
| **[Getting Started](docs/getting-started/)** | Installation, first steps, quick reference |
| **[Deployment](docs/deployment/)** | Render, Koyeb, Docker, server setup |
| **[Development](docs/development/)** | Architecture, contributing, AI coding guide |
| **[User Guides](docs/user-guides/)** | Admin, analyst, and blog guides |
| **[Operations](docs/operations/)** | Security, monitoring, backups |
| **[Reference](docs/reference/)** | Environment variables, database schema |

### 🤖 AI Coding Tools

**[AI agent guide](AGENTS.md)** - Quick reference for Roo Code, Cursor, Claude, and other AI assistants working with this codebase.

---

## 🏗️ Architecture

```
Flask Application
├── Auth (Login/Register)
├── Admin (Management)
├── Analyst (Dashboard)
├── Main (Public Pages)
├── Blog (Content)
└── Utils (Performance, AI)

Database: SQLite (dev) / PostgreSQL (prod)
Frontend: Bootstrap 5 + Tailwind CSS
```

**Full details:** [Architecture Guide](docs/development/architecture.md)

---

## 🚢 Deployment

**Production:** [Production Infrastructure](docs/deployment/production.md) — Render web app + self-hosted PostgreSQL 17 on the club VPS

**Generic recipe:** [Deploy to Render](docs/deployment/render.md) (external PostgreSQL)

**Alternative Options:**
- [Koyeb](docs/deployment/koyeb.md) - Always-on, European servers
- [Dockploy](docs/deployment/dockploy.md) - Self-hosted PaaS, unlimited apps (~$5/month)
- [Docker](docs/deployment/docker.md) - Container deployment
- [Self-hosted](docs/deployment/server-setup.md) - Full control

---

## 💻 Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask 2.3.3, SQLAlchemy |
| Frontend | Bootstrap 5, Tailwind CSS, Jinja2 |
| Database | SQLite (dev), PostgreSQL (prod) |
| APIs | Yahoo Finance, DeepSeek AI, Brave Search |
| Deployment | Render + self-hosted PostgreSQL 17 (prod); Docker / Koyeb / Dockploy alternatives |

---

## 🤝 Contributing

We welcome contributions! Please see:

- **[Contributing Guide](docs/development/contributing.md)** - How to contribute
- **[Development Guide](docs/development/)** - Setup and workflow

---

## 📄 License

Internal project of the Prague Club of Investors. Technology is public; credentials are not.

---

## 🆘 Support

- **Issues:** [GitHub Issues](https://github.com/YOUR_USERNAME/ki-asset-management/issues)
- **Discussions:** [GitHub Discussions](https://github.com/YOUR_USERNAME/ki-asset-management/discussions)
- **Documentation:** [Full Docs](docs/README.md)

---

<p align="center">
  <strong>Built with Flask and modern web technologies</strong><br>
  <a href="docs/README.md">Documentation</a> •
  <a href="docs/getting-started/installation.md">Getting Started</a> •
  <a href="docs/deployment/">Deployment</a>
</p>
