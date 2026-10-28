# Deploy with Dockploy

> ⚠️ **Note:** Neon's free tier suspends a project when its monthly quota is
> exceeded (that is why this club moved to self-hosted PostgreSQL — see
> [Production Infrastructure](production.md)). Everything below works with
> **any PostgreSQL 17+** database; treat Neon as one managed option.


Deploy KI Asset Management using **Dockploy** - a self-hosted PaaS that gives you Vercel-like deployment on your own server.

> **⏱️ Time Required:** 25-30 minutes  
> **💰 Cost:** Free (use your own VPS - ~$5-10/month)  
> **🎯 Difficulty:** Intermediate  
> **✅ Benefit:** Full control, no platform limits, unlimited apps

---

## Why Dockploy?

| Feature | Dockploy | Render | Koyeb |
|---------|----------|--------|-------|
| **Self-Hosted** | ✅ Yes | ❌ No | ❌ No |
| **Unlimited Apps** | ✅ Yes | ❌ Limited | ❌ Limited |
| **No Cold Starts** | ✅ Yes | ❌ Yes | ✅ No |
| **Custom Domains** | ✅ Unlimited | ✅ Yes | ✅ Yes |
| **Database Options** | ✅ Built-in OR Neon.tech | ❌ External only | ❌ External only |
| **Cost Control** | ✅ Fixed price | Usage-based | Usage-based |

**Best for:** Teams wanting full control, multiple projects, or avoiding platform limits

---

## Overview

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│   Your Browser  │────▶│   Dockploy       │────▶│  PostgreSQL              │
│                 │     │   (Your VPS)     │     │  Docker OR neon.tech     │
└─────────────────┘     │   + Traefik      │     └──────────────────────────┘
                        │   + SSL          │                 │
                        └──────────────────┘                 │
                               │                             │
                               ▼                             ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │  GitHub Repo     │     │  Your App       │
                        │  (Auto-deploy)   │     │  (Docker)       │
                        └──────────────────┘     └─────────────────┘
```

**Database Options:**
- **Built-in:** PostgreSQL runs in Docker on your server
- **Neon.tech:** Managed PostgreSQL in the cloud (recommended for production)

---

## Step 1: Get a VPS (Virtual Private Server)

### Recommended Providers

| Provider | Plan | Price | Location |
|----------|------|-------|----------|
| **Hetzner** | CX11 (2 vCPU, 4GB RAM) | €4.51/month | Germany/Finland |
| **DigitalOcean** | Basic (1 vCPU, 1GB RAM) | $6/month | Multiple |
| **Vultr** | Cloud Compute (1 vCPU, 1GB RAM) | $5/month | Multiple |
| **Linode** | Nanode (1 vCPU, 1GB RAM) | $5/month | Multiple |

### Create Your Server

1. Sign up with your chosen provider
2. Create a new VPS:
   - **OS:** Ubuntu 22.04 LTS (recommended)
   - **Plan:** 1 vCPU, 1GB RAM minimum (2GB+ recommended)
   - **Location:** Choose closest to your users (Frankfurt for Europe)
3. Add your SSH key (recommended) or use password
4. Note the **IP address** of your server

---

## Step 2: Install Dockploy

### 2.1 Connect to Your Server

```bash
# Using SSH (replace with your server's IP)
ssh root@YOUR_SERVER_IP

# Or use your provider's web console
```

### 2.2 Update System

```bash
# Update package lists
apt update && apt upgrade -y

# Install curl if not present
apt install curl -y
```

### 2.3 Install Dockploy

```bash
# Run the installation script
curl -sSL https://dokploy.com/install.sh | bash
```

This will:
- Install Docker and Docker Compose
- Install Traefik (reverse proxy with auto SSL)
- Install Dockploy management interface
- Set up automatic HTTPS certificates

**Installation takes:** 3-5 minutes

### 2.4 Verify Installation

```bash
# Check if Dockploy is running
docker ps

# You should see containers for:
# - dokploy
# - traefik
```

---

## Step 3: Access Dockploy Dashboard

### 3.1 Get Admin Password

```bash
# The installation will output your admin password
# Or retrieve it with:
docker logs dokploy 2>&1 | grep "Admin Password"
```

### 3.2 Open Dashboard

1. Go to: `http://YOUR_SERVER_IP:3000`
2. Login credentials:
   - **Email:** `admin@localhost.local`
   - **Password:** (from installation output)
3. **Immediately change the password** in Settings

---

## Step 4: Configure Custom Domain (Recommended)

### 4.1 Point Domain to Server

In your domain registrar/DNS provider:

1. Create an **A record**:
   - Name: `dockploy` (or subdomain of choice)
   - Value: `YOUR_SERVER_IP`
2. Create another **A record** for your app:
   - Name: `analytics` (or your preferred subdomain)
   - Value: `YOUR_SERVER_IP`

**Example:**
```
dockploy.yourdomain.com → YOUR_SERVER_IP
analytics.yourdomain.com → YOUR_SERVER_IP
```

### 4.2 Set Domain in Dockploy

1. In Dockploy dashboard, go to **Settings** (gear icon)
2. Under **Server Domain**, enter: `dockploy.yourdomain.com`
3. Click **Save**
4. Dockploy will automatically get SSL certificate via Let's Encrypt

### 4.3 Access via HTTPS

Wait 1-2 minutes, then visit:
```
https://dockploy.yourdomain.com
```

✅ You should see the Dockploy dashboard with a secure lock icon.

---

## Step 5: Deploy KI Asset Management

### 5.1 Set Up Database (Choose One)

#### Option A: Dockploy Built-in Database (Easiest)

Use Dockploy's built-in PostgreSQL - everything stays on your server.

1. In Dockploy dashboard, click **Create Service** → **Database**
2. Select **PostgreSQL**
3. Configure:
   - **Name:** `ki-database`
   - **Version:** 15 (or latest)
   - **Username:** `analyst_user`
   - **Password:** Generate strong password
   - **Database:** `analyst_db`
4. Click **Create**
5. Wait for database to be ready (1-2 minutes)

**Note the connection details** - you'll need them in Step 5.4

#### Option B: Neon.tech Database (External)

Use [neon.tech](https://neon.tech) for managed PostgreSQL with automatic backups and branching.

**Why Neon.tech?**
- ✅ Automatic backups (7 days on free tier)
- ✅ Database branching for testing
- ✅ Auto-scaling compute
- ✅ Separates database from your server
- ✅ Free tier: 500MB storage

**Setup:**

1. Go to [neon.tech](https://neon.tech) and sign up with GitHub
2. Click **New Project**
   - Name: `ki-asset-management`
   - Database: `analyst_db`
3. Wait 1-2 minutes for creation
4. Go to **Connection Details**
5. Copy the **PostgreSQL connection string** (looks like:
   `postgresql://user:password@ep-xxx.us-east-1.aws.neon.tech/analyst_db?sslmode=require`)
6. **Save it safely** - you'll need it in Step 5.4

**For Step 5.4:** Use the neon.tech connection string instead of the Dockploy internal one.

**Which database should you choose?**

| Factor | Dockploy Built-in | Neon.tech |
|--------|------------------|-----------|
| **Setup** | One-click in Dockploy | Separate signup |
| **Backups** | Manual configuration | Automatic (7 days free) |
| **Server resources** | Uses your VPS RAM/CPU | Zero VPS resources |
| **Cost** | Included in VPS price | Free tier (500MB) |
| **Scaling** | Manual upgrade | Auto-scaling |
| **Best for** | Simple/single app setups | Production, multiple apps |
| **Branching** | ❌ No | ✅ Yes (test changes) |

**Recommendation:** Use **Neon.tech** for production or if you plan to run multiple applications. Use **Dockploy built-in** for simple setups or testing.

### 5.2 Create Application

1. Click **Create Service** → **Application**
2. Configure:
   - **Name:** `ki-asset-management`
   - **Description:** KI Asset Management Platform
   - **Repository:** Select GitHub → your repository
   - **Branch:** `main`
3. Click **Create**

### 5.3 Configure Build Settings

In your application settings:

**Build Configuration:**
- **Builder:** Docker
- **Dockerfile Path:** `./Dockerfile` (or use Buildpack)

**If using Buildpack (easier):**
- **Builder:** Buildpack
- **Build Command:** `pip install -r requirements.txt`

**Deployment Configuration:**
- **Start Command:** `gunicorn "app:create_app()" --bind 0.0.0.0:8000`
- **Port:** `8000`
- **Health Check Path:** `/health`

### 5.4 Configure Environment Variables

Click **Environment** tab, add these variables:

| Variable Name | Value | Notes |
|--------------|-------|-------|
| `SECRET_KEY` | Generate with: `openssl rand -hex 32` | 64-character random string |
| `USE_LOCAL_SQLITE` | `False` | Must use PostgreSQL |
| `DATABASE_URL` | See below ↓ | Database connection string |

**For DATABASE_URL:**

- **Option A (Dockploy DB):** `postgresql://analyst_user:PASSWORD@ki-database:5432/analyst_db`
  - Use internal Docker network name `ki-database`
  
- **Option B (Neon.tech):** `postgresql://user:pass@ep-xxx.neon.tech/analyst_db?sslmode=require`
  - Copy directly from neon.tech dashboard
| `FLASK_ENV` | `production` | Production mode |
| `PORT` | `8000` | Must match port setting |
| `ADMIN_EMAIL` | `admin@yourdomain.com` | Your admin email |

### 5.5 Email Configuration (REQUIRED)

**Option A: SendGrid (Recommended)**

1. Sign up at [sendgrid.com](https://sendgrid.com)
2. Verify your sender email
3. Create API Key
4. Add to environment variables:

| Variable Name | Value |
|--------------|-------|
| `SENDGRID_API_KEY` | `SG.xxxxx...` |
| `MAIL_DEFAULT_SENDER` | Your verified sender email |

**Option B: SMTP (Your Email Provider)**

| Variable Name | Value |
|--------------|-------|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Your email |
| `SMTP_PASSWORD` | App-specific password |
| `MAIL_DEFAULT_SENDER` | Your email |

### 5.6 Configure Domain

1. Click **Domains** tab
2. Click **Add Domain**
3. Enter: `analytics.yourdomain.com`
4. Enable **HTTPS** (auto SSL)
5. Click **Save**

### 5.7 Deploy

1. Click **Deploy** button
2. Watch the build logs
3. Wait for status to show **Running** (2-3 minutes)

---

## Step 6: Initialize Database & Create Admin

### 6.1 Open Application Console

1. In your application page, click **Console** tab
2. This opens a terminal inside your running container

### 6.2 Initialize Database

```bash
flask init-db
```

Expected output:
```
Database tables created successfully!
```

### 6.3 Create Admin User

```bash
flask create-admin
```

Follow prompts:
- Enter admin email (must match `ADMIN_EMAIL` variable)
- Enter secure password (12+ characters)
- Confirm password

### 6.4 Verify Deployment

Visit your app: `https://analytics.yourdomain.com`

You should see:
- Landing page loads
- Login works at `/auth/login`
- Admin panel accessible

🎉 **Success! Your app is running on your own server!**

---

## Step 7: Enable Auto-Deploy (Optional but Recommended)

### 7.1 Configure GitHub Webhook

1. In Dockploy, go to your application → **Settings** → **Git**
2. Copy the **Webhook URL**
3. Go to your GitHub repository → **Settings** → **Webhooks**
4. Click **Add webhook**
5. Paste the Dockploy webhook URL
6. Content type: `application/json`
7. Select **Just the push event**
8. Click **Add webhook**

### 7.2 Test Auto-Deploy

```bash
# Make a small change locally
echo "# Test" >> README.md

# Commit and push
git add .
git commit -m "Test auto-deploy"
git push origin main
```

Check Dockploy dashboard - you should see a new deployment start automatically!

---

## Updating Your Application

With auto-deploy enabled:

```bash
# 1. Make changes locally
# Edit files, test locally

# 2. Commit and push
git add .
git commit -m "Your changes"
git push origin main

# 3. Dockploy auto-detects and redeploys
```

**Takes:** 2-3 minutes  
**Downtime:** Near zero (blue-green deployment)

---

## Server Requirements & Costs

### Minimum Requirements
- **RAM:** 1GB (2GB+ recommended for multiple apps)
- **Storage:** 20GB SSD
- **OS:** Ubuntu 22.04 LTS or Debian 11+
- **Network:** Static IP address

### Estimated Costs

| Component | Provider | Monthly Cost |
|-----------|----------|--------------|
| **VPS** | Hetzner CX11 | €4.51 (~$5) |
| **VPS** | DigitalOcean Basic | $6 |
| **VPS** | Vultr Cloud | $5 |
| **Database** | Dockploy Built-in | $0 (included) |
| **Database** | Neon.tech | $0 (500MB free tier) |

**Total Cost:** $5-6/month for unlimited applications + database!

Compare to:
- Render: $7/month per web service + database costs
- Koyeb: $0-5/month (limited free tier) + database costs
- Heroku: $7/month per dyno + database costs

---

## Troubleshooting

### Issue: "Cannot connect to server"

**Solution:**
1. Check server is running: `ping YOUR_SERVER_IP`
2. Verify firewall allows port 3000 (initial setup)
3. Check provider's firewall/security groups

### Issue: "Dockploy installation failed"

**Solution:**
1. Ensure Ubuntu 22.04+ or Debian 11+
2. Check Docker is not already installed conflicting version
3. Try: `apt remove docker docker-engine docker.io containerd runc`
4. Re-run installation script

### Issue: "SSL certificate not working"

**Solution:**
1. Verify DNS records propagated (can take up to 24 hours)
2. Check domain points to server IP
3. Verify port 80 is open (required for Let's Encrypt)
4. Try: `docker restart traefik`

### Issue: "Database connection failed"

**For Dockploy Built-in Database:**
1. Check database is running in Dockploy dashboard
2. Verify `DATABASE_URL` uses internal Docker network name
3. Format should be: `postgresql://user:pass@ki-database:5432/dbname`
4. Ensure `USE_LOCAL_SQLITE=False`

**For Neon.tech Database:**
1. Verify neon.tech database is active (not suspended)
2. Check `DATABASE_URL` includes `?sslmode=require` at the end
3. Ensure `USE_LOCAL_SQLITE=False`
4. Try copying the connection string fresh from neon.tech dashboard
5. Check that your VPS IP is allowed (neon.tech connection settings)

### Issue: "Build failed"

**Solution:**
1. Check build logs in Dockploy
2. Verify `requirements.txt` is present
3. Test locally: `pip install -r requirements.txt`
4. Check Python version compatibility

### Issue: "Application unhealthy"

**Solution:**
1. Check application logs in Dockploy
2. Verify `PORT` environment variable matches setting
3. Ensure start command binds to `0.0.0.0`
4. Check all required environment variables are set

---

## Backups

### Automatic Database Backups

**For Dockploy Built-in Database:**
1. In Dockploy, go to your database → **Backups**
2. Enable **Automatic Backups**
3. Set schedule (e.g., daily at 2 AM)
4. Configure backup retention

**For Neon.tech Database:**
- Backups are automatic (7 days retention on free tier)
- Point-in-time recovery available
- No configuration needed!

### Manual Backup

```bash
# In application console
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql
```

---

## Next Steps

- [Configure Email](../getting-started/first-steps.md#2-configure-email)
- [Upload Initial Data](../getting-started/first-steps.md#3-upload-initial-data)
- [User Guides](../user-guides/README.md)
- [Monitoring](../operations/monitoring.md)
- Deploy additional apps on the same server!

---

## Dockploy vs Other Platforms

| Feature | Dockploy | Render | Koyeb |
|---------|----------|--------|-------|
| **Cost for 5 apps** | $5/month | $35/month | $0-25/month |
| **Self-hosted** | ✅ Yes | ❌ No | ❌ No |
| **Data privacy** | ✅ Full control | ❌ Third-party | ❌ Third-party |
| **Custom domains** | ✅ Unlimited | ✅ Yes | ✅ Yes |
| **SSL certificates** | ✅ Auto (Let's Encrypt) | ✅ Auto | ✅ Auto |
| **Database hosting** | ✅ Built-in | ❌ External | ❌ External |
| **Setup complexity** | Medium | Easy | Easy |
| **Maintenance** | You manage | Fully managed | Fully managed |

**Choose Dockploy if:** You want full control, have multiple apps, or prefer fixed costs  
**Choose Render/Koyeb if:** You prefer fully-managed, hands-off deployment

---

<p align="center">
  <strong>🎉 You now have your own deployment platform!</strong><br>
  <em>Deploy unlimited apps on your own infrastructure</em>
</p>
