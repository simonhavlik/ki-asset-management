# Deploy to Koyeb + Neon.tech

Deploy KI Asset Management to Koyeb for **always-on availability** with no cold starts.

> **⏱️ Time Required:** 20-25 minutes  
> **💰 Cost:** Free tier (1 always-on web service)  
> **🎯 Difficulty:** Beginner-friendly  
> **✅ Benefit:** No cold starts, European servers

---

## Why Koyeb?

| Feature | Render | Koyeb |
|---------|--------|-------|
| **Cold Starts** | Yes (30-60 sec) | **No** ✅ |
| **Always-On** | No (sleeps after 15 min) | **Yes** ✅ |
| **European Servers** | No (US only) | **Yes** (Frankfurt) ✅ |
| **Free Tier** | Yes | Yes |

**Best for:** Production use, European users, zero-tolerance for cold starts

---

## Overview

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Your Browser  │────▶│   Koyeb (Free)   │────▶│  neon.tech      │
│   (Prague/EU)   │     │   Web Server     │     │  PostgreSQL     │
└─────────────────┘     │   (Frankfurt)    │     └─────────────────┘
                        └──────────────────┘
                              │
                              ▼
                        ┌──────────────────┐
                        │  GitHub Repo     │
                        │  (Auto-deploy)   │
                        └──────────────────┘
```

---

## Step 1: Prepare Your Code

### 1.1 Ensure Code is Ready

Your repository should have:
- `requirements.txt` at root
- `app/` directory with Flask application
- `.env.example` with all needed variables
- `Procfile` (optional, Koyeb can auto-detect)

### 1.2 Push to GitHub

```bash
# Make sure everything is committed
git add .
git commit -m "Ready for Koyeb deployment"
git push origin main
```

---

## Step 2: Create neon.tech Database

Same process as Render deployment:

1. Go to [neon.tech](https://neon.tech)
2. Sign up with GitHub
3. Click **New Project**
   - Name: `ki-asset-management`
   - Database: `analyst_db`
4. Wait 1-2 minutes for creation
5. Go to **Connection Details**
6. Copy the PostgreSQL connection string
7. **Save it safely** for Step 4

---

## Step 3: Deploy to Koyeb

### 3.1 Create Koyeb Account

1. Go to [koyeb.com](https://www.koyeb.com)
2. Click **Get Started** or **Sign Up**
3. Sign up with **GitHub** (easiest)
4. Authorize Koyeb to access your repositories

### 3.2 Create Web Service

1. In Koyeb dashboard, click **Create Web Service**
2. Select **GitHub** as deployment method
3. Find and select your `ki-asset-management` repository
4. Click **Build and Deployment Settings**

### 3.3 Configure Build & Deployment

**Build Settings:**

| Setting | Value |
|---------|-------|
| **Builder** | Buildpack (or Dockerfile if you have one) |
| **Build Command** | `pip install -r requirements.txt` |

**Deployment Settings:**

| Setting | Value |
|---------|-------|
| **Run Command** | `gunicorn "app:create_app()"` |
| **Port** | `8000` |
| **Region** | **fra** (Frankfurt) - closest to Prague |
| **Instance Type** | Free (nano) |

**Advanced Settings:**
- **Health Check Path**: `/health`
- **Auto-deploy**: Enabled (on git push)

Click **Create Web Service**

### 3.4 Wait for Deployment

- Initial deployment takes 3-5 minutes
- You'll see build logs streaming
- Status will change to "Healthy" when ready

---

## Step 4: Configure Environment Variables

### 4.1 Open Environment Settings

1. In your Koyeb service dashboard, click **Variables** (top menu)
2. Click **Add Variable** for each variable

### 4.2 Add Required Variables

| Variable Name | Value | Notes |
|--------------|-------|-------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` | Generate locally |
| `USE_LOCAL_SQLITE` | `False` | Must use PostgreSQL |
| `DATABASE_URL` | Your neon.tech connection string | From Step 2 |
| `FLASK_ENV` | `production` | Production mode |
| `PORT` | `8000` | Required for Koyeb |
| `ADMIN_EMAIL` | `admin@klubinvestoru.com` | Your admin email |

### 4.3 Email Configuration (REQUIRED)

**SendGrid Setup (Recommended):**

1. Sign up at [sendgrid.com](https://sendgrid.com) (free: 100 emails/day)
2. Verify your email
3. Go to **Settings** → **Sender Authentication** → **Single Sender Verification**
4. Create new sender with your admin email
5. Go to **Settings** → **API Keys** → **Create API Key**
6. Copy the API key (starts with `SG.`)

Add to Koyeb:

| Variable Name | Value |
|--------------|-------|
| `SENDGRID_API_KEY` | `SG.xxxxx...` |
| `MAIL_DEFAULT_SENDER` | Your verified sender email |

### 4.4 Redeploy

After adding all variables:
1. Click **Save**
2. Koyeb will automatically redeploy
3. Wait 2-3 minutes

---

## Step 5: Initialize Database & Create Admin

### 5.1 Open Koyeb Console

1. In your service dashboard, click **Console** (top menu)
2. This opens a terminal in your running container

### 5.2 Initialize Database

In the console, run:

```bash
flask init-db
```

You should see:
```
Database tables created successfully!
```

### 5.3 Create Admin User

```bash
flask create-admin
```

Follow the prompts:
- Enter admin email (should match `ADMIN_EMAIL` variable)
- Enter secure password
- Confirm password

### 5.4 Verify Installation

Visit your app's URL: `https://ki-asset-management-xxx.koyeb.app`

You should see the landing page. Test login:
1. Go to `/auth/login`
2. Enter admin credentials
3. You should be logged in as admin

🎉 **Success! Your app is live with no cold starts!**

---

## Updating Your Application

Updates are automatic when you push to GitHub:

```bash
# 1. Make changes locally
# Edit files, test locally

# 2. Commit and push
git add .
git commit -m "Your changes"
git push origin main

# 3. Koyeb auto-detects and redeploys (watch the logs)
```

**Takes:** 2-3 minutes  
**Downtime:** ~30 seconds (blue-green deployment)

---

## Free Tier Limits

### Koyeb Free Tier
- **Web Services**: 1 always-on service (this is it!)
- **Databases**: Free PostgreSQL available (or use neon.tech)
- **Bandwidth**: 100 GB/month
- **Build time**: 100 build minutes/month
- **Custom domains**: Supported

### neon.tech Free Tier
- **Storage**: 0.5 GB
- **Compute**: Autoscales to zero
- **Connections**: 20 concurrent
- **Backups**: 7 days

### When to Upgrade

Consider upgrading when:
- You need more than 1 web service
- Database exceeds 500MB
- You need more build minutes
- You want larger instance sizes

---

## Troubleshooting

### Issue: "Service Unhealthy"

**Solution:**
1. Check logs in Koyeb dashboard
2. Verify `PORT=8000` is set
3. Ensure start command is: `gunicorn "app:create_app()"`
4. Check that all environment variables are set

### Issue: "Database connection failed"

**Solution:**
1. Verify `DATABASE_URL` is correct
2. Ensure `USE_LOCAL_SQLITE=False`
3. Check neon.tech database is active
4. Verify connection string includes `?sslmode=require`

### Issue: "Build failed"

**Solution:**
1. Check build logs for errors
2. Verify `requirements.txt` is present
3. Ensure no missing dependencies

### Issue: "Email not sending"

**Solution:**
1. Verify SendGrid API key is correct
2. Check that sender email is verified in SendGrid
3. Ensure `MAIL_DEFAULT_SENDER` matches verified sender

### Issue: Can't access console

**Solution:**
1. Wait for deployment to complete
2. Service must be "Healthy" to access console
3. Try refreshing the page

---

## Custom Domain (Optional)

### Add Your Domain

1. In Koyeb dashboard, go to your service
2. Click **Domains** (top menu)
3. Click **Add Domain**
4. Enter your domain: `analytics.yourclub.com`
5. Follow DNS configuration instructions
6. Add CNAME record pointing to Koyeb

### SSL Certificate

Koyeb automatically provisions SSL certificates for custom domains via Let's Encrypt.

---

## Koyeb vs Render Comparison

| Feature | Koyeb | Render |
|---------|-------|--------|
| Cold starts | ❌ None | ✅ Yes (30-60s) |
| Always-on | ✅ Yes | ❌ Sleeps after 15min |
| EU servers | ✅ Frankfurt | ❌ US only |
| Free tier | ✅ Generous | ✅ Generous |
| Custom domains | ✅ Easy | ✅ Easy |
| Build minutes | 100/month | 500/month |
| GitHub integration | ✅ Auto-deploy | ✅ Auto-deploy |

**Choose Koyeb if:** You need always-on availability or are in Europe  
**Choose Render if:** You want more build minutes or prefer US-based

---

## Next Steps

- [Configure Email](../getting-started/first-steps.md#2-configure-email)
- [Upload Initial Data](../getting-started/first-steps.md#3-upload-initial-data)
- [User Guides](../user-guides/README.md)
- [Monitoring](../operations/monitoring.md)

---

<p align="center">
  <strong>🎉 Your application is live with zero cold starts!</strong><br>
  <em>Koyeb's always-on service means instant response times</em>
</p>
