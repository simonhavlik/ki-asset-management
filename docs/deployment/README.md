# Deployment Guide

Complete deployment options for KI Asset Management. Choose the platform that best fits your needs.

---

## 🎯 Quick Comparison

<div align="center">

| Platform | Best For | Cost | Complexity | Always-On |
|:---:|:---:|:---:|:---:|:---:|
| **[Production](production.md)** | This club | Club VPS | — | No* |
| **[Render + PostgreSQL](render.md)** | Beginners | Free tier | Easy | No* |
| **[Koyeb + Postgres](koyeb.md)** | Always-on | Free tier | Easy | ✅ Yes |
| **[Dockploy](dockploy.md)** | Multiple apps | $5/month | Medium | ✅ Yes |
| **[Docker](docker.md)** | Flexibility | Your server | Medium | ✅ Yes |
| **[Server Setup](server-setup.md)** | Full control | Your server | Hard | ✅ Yes |

</div>

*Render free tier sleeps after 15 min inactivity (can be prevented with ping service)

---

## 🚀 Production (this club): Render + self-hosted PostgreSQL

**What we actually run:** the Flask app on **Render** (free, Frankfurt) talking to a
**self-hosted PostgreSQL 17** on the club VPS.

- ✅ Auto-deploy on push to `main`
- ✅ Full control of the database (no managed quota limits)
- ✅ Secrets live in Render env vars — the repo is public, the keys never are
- ⚠️ Self-hosted Postgres has **no automatic backups** — the scheduled `pg_dump`
  in [Backup & Restore](../operations/backup-restore.md) is mandatory

**Get started:** [Production Infrastructure](production.md)

---

## 🚀 Alternative: Koyeb + managed PostgreSQL

**Best for:** Production use, always-on requirement

**Why Koyeb?**
- ✅ **Always-on** (no cold starts!)
- ✅ European servers (Frankfurt) - great for Prague
- ✅ Fast deployments
- ✅ Free tier includes 1 always-on web service

**Get started:** [Koyeb Guide](koyeb.md)

---

## 🚀 Alternative: Dockploy (Self-Hosted PaaS)

**Best for:** Running multiple apps, full control, fixed costs

**Why Dockploy?**
- ✅ **Unlimited apps** on one server (~$5/month)
- ✅ **Self-hosted** - full data control
- ✅ **Built-in databases** (PostgreSQL, MySQL, MongoDB, Redis)
- ✅ **Automatic SSL** with Let's Encrypt
- ✅ **Vercel-like UI** but on your infrastructure

**Get started:** [Dockploy Guide](dockploy.md)

---

## 🐳 Docker Deployment

**Best for:** DevOps teams, consistent environments, multi-cloud

**Benefits:**
- ✅ Identical environment across all platforms
- ✅ Easy local development matching production
- ✅ Portable between cloud providers
- ✅ Simple scaling with docker-compose

**Get started:** [Docker Guide](docker.md)

---

## 🖥️ Self-Hosted Server

**Best for:** Full control, compliance requirements, high performance

**Options:**
- DigitalOcean Droplet
- AWS EC2
- Linode VPS
- Hetzner Cloud
- Any Debian/Ubuntu server

**Requirements:**
- 1GB RAM minimum
- 20GB storage
- Ubuntu 22.04+ or Debian 11+

**Get started:** [Server Setup Guide](server-setup.md)

---

## 📊 Decision Matrix

### Choose Render if...
- You're new to deployment
- You want the easiest setup
- You don't mind occasional cold starts (30-60 sec)
- You can use UptimeRobot to prevent sleeping

### Choose Koyeb if...
- You need always-on availability
- You're in Europe (lower latency)
- You want zero cold starts
- You prefer modern serverless platform

### Choose Dockploy if...
- You have multiple applications to deploy
- You want full control over your infrastructure
- You prefer fixed monthly costs ($5-6/month)
- You need built-in database hosting
- You're comfortable managing a VPS

### Choose Docker if...
- You need environment consistency
- You're deploying to multiple platforms
- You have DevOps experience
- You want easy local-to-prod parity

### Choose Self-Hosted if...
- You need full control
- You have compliance requirements
- You want the best performance
- You have sysadmin experience

---

## 🏗️ Architecture Overview

All deployment options follow this architecture:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Your Browser  │────▶│   Web Server     │────▶│   PostgreSQL    │
│                 │     │   (Flask App)    │     │   Database      │
└─────────────────┘     └──────────────────┘     │  (PostgreSQL 17)│
                              │                   └─────────────────┘
                              ▼
                        ┌──────────────────┐
                        │  GitHub Repo     │
                        │  (Auto-deploy)   │
                        └──────────────────┘
```

**Components:**
- **Web Server:** Runs the Flask application
- **Database:** Stores all application data
- **GitHub:** Source code and auto-deployment trigger
- **External APIs:** Yahoo Finance, DeepSeek AI (optional)

---

## 📋 Pre-Deployment Checklist

Before deploying to production:

### Security
- [ ] `SECRET_KEY` is a cryptographically secure random value (32+ bytes)
- [ ] `.env` file is in `.gitignore` (never committed)
- [ ] Repository is set to **Private** on GitHub
- [ ] Admin password is strong (12+ characters)

### Configuration
- [ ] `FLASK_ENV=production` is set
- [ ] `USE_LOCAL_SQLITE=False` for PostgreSQL
- [ ] `DATABASE_URL` configured (PostgreSQL 17+)
- [ ] Email configured (SendGrid for Render, SMTP for others)

### Domain (Optional)
- [ ] Custom domain configured (if using)
- [ ] SSL certificate enabled (HTTPS)

### Monitoring
- [ ] Ping service configured (for Render free tier)
- [ ] Log monitoring setup

---

## 🔄 Post-Deployment Workflow

Once deployed, updating is easy:

```bash
# 1. Make changes locally
# Edit files, test locally

# 2. Commit and push
git add .
git commit -m "Your changes"
git push origin main

# 3. Auto-deploy happens automatically!
# Render/Koyeb will detect the push and redeploy
```

**Deployment takes:** 2-3 minutes

---

## 💰 Cost Estimates

### Free Tier (Sufficient for 20-50 users)

| Service | Provider | Monthly Cost |
|---------|----------|--------------|
| Web Hosting | Render | $0 |
| Web Hosting | Koyeb | $0 |
| Database | self-hosted PostgreSQL (own VPS) | $0 |
| Email | SendGrid | $0 (100 emails/day) |
| Domain (optional) | Various | $10-15/year |
| **Total** | | **$0-15/year** |

### When to Upgrade

Consider paid tiers when:
- Database outgrows the free tier / VPS
- You need more than 20 concurrent connections
- Build minutes exceed 500/month (Render)
- Cold start delays become problematic
- You need custom domain with SSL

---

## 🆘 Deployment Troubleshooting

### Issue: "Application failed to start"

**Solution:**
1. Check logs in platform dashboard
2. Verify all environment variables are set
3. Ensure `SECRET_KEY` is configured
4. Check `DATABASE_URL` is correct

### Issue: "Database connection failed"

**Solution:**
1. Verify the database host is reachable and PostgreSQL is running
2. Check `DATABASE_URL` format
3. Ensure `USE_LOCAL_SQLITE=False`
4. Re-check `DATABASE_URL` (host, port, credentials, `sslmode=require`)

### Issue: "Build failed"

**Solution:**
1. Verify `requirements.txt` is in repo
2. Check all dependencies are listed
3. Test locally: `pip install -r requirements.txt`

### Issue: "404 Not Found"

**Solution:**
1. Wait 2-3 minutes after deployment
2. Check service shows "Live" status
3. Try `https://` not `http://`

---

## 📚 Next Steps

Choose your deployment platform:

1. **[Production](production.md)** - What this club actually runs (Render + self-hosted Postgres)
2. **[Render + PostgreSQL](render.md)** - Generic Render recipe
3. **[Koyeb](koyeb.md)** - Always-on alternative
4. **[Dockploy](dockploy.md)** - Self-hosted PaaS for multiple apps
5. **[Docker](docker.md)** - Container deployment
6. **[Server Setup](server-setup.md)** - Self-hosted PostgreSQL

---

<p align="center">
  <strong>Ready to deploy?</strong><br>
  Start with <a href="production.md">Production Infrastructure</a>
</p>
