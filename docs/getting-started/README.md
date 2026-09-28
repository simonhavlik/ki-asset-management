# Getting Started

Welcome to KI Asset Management! Choose your path below to get up and running.

---

## 🚀 Quick Start Options

<div align="center">

| ⏱️ **5 Minutes** | 🎯 **Complete Setup** | 🚢 **Deploy to Production** |
|:---:|:---:|:---:|
| [Quick Installation](installation.md#quick-setup-5-minutes) | [Full Installation](installation.md) | [Deployment Guide](../deployment/README.md) |
| Get running locally fast | Platform-specific instructions | Go live on Render/Koyeb |

</div>

---

## 📋 Installation Guides

### [Local Development Setup](installation.md)

Complete guide for setting up on your local machine:
- Prerequisites and requirements
- Step-by-step installation
- Platform-specific instructions (Linux, macOS, Windows)
- Verification steps

### [First Steps & Configuration](first-steps.md)

After installation, learn to:
- Navigate the application
- Configure email for user registration
- Upload your first CSV data
- Set up company tickers
- Run performance calculations

---

## 🎯 By Use Case

### 👤 I Want to Use the Application

Start here if you're an analyst or admin user:

1. **[Installation](installation.md)** - Get the app running
2. **[First Steps](first-steps.md)** - Initial configuration
3. **[User Guides](../user-guides/README.md)** - Learn to use features

### 👨‍💻 I Want to Develop/Contribute

Start here if you're a developer:

1. **[Installation](installation.md)** - Set up local environment
2. **[Development Guide](../development/README.md)** - Coding standards and workflow
3. **[AI Coding Tools](../../AGENTS.md)** - Quick reference for AI assistants

### 🏢 I Want to Deploy for My Organization

Start here if you're deploying to production:

1. **[Deployment Overview](../deployment/README.md)** - Choose your platform
2. **[Production Infrastructure](../deployment/production.md) & [Render guide](../deployment/render.md)** - Recommended (free tier)
3. **[Koyeb Guide](../deployment/koyeb.md)** - Alternative (always-on)

---

## ⚡ TL;DR - Just Get It Running

```bash
# 1. Clone and setup
git clone <repo-url>
cd analyst_website
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env: Set SECRET_KEY and email settings

# 3. Initialize
flask init-db
flask create-admin

# 4. Run
flask run
```

Visit: [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 📚 Documentation Map

```
Getting Started (You are here)
├── Installation
├── First Steps
└── Quick Commands

Deployment
├── Overview
├── Render + self-hosted PostgreSQL (this club)
├── Koyeb
├── Docker
└── Server Setup

Development
├── Contributing
├── Architecture
├── Testing
└── AI Coding Tools

User Guides
├── Admin Panel
├── Analyst Dashboard
└── Blog System

Operations
├── Security
├── Troubleshooting
├── Monitoring
└── Backup/Restore

Reference
├── Environment Variables
├── Database Schema
├── API Endpoints
└── Changelog
```

---

## 🤝 Need Help?

- **Installation Issues:** See [Troubleshooting](../operations/troubleshooting.md)
- **Deployment Questions:** Check [Deployment Guides](../deployment/)
- **Development Help:** Read [AI Orientation](../../AGENTS.md)
- **Feature Questions:** Browse [User Guides](../user-guides/)

---

<p align="center">
  <strong>Ready to start?</strong> → <a href="installation.md">Installation Guide</a>
</p>
