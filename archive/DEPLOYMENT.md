# Deployment Guide: Render + neon.tech

This guide will walk you through deploying the KI Asset Management application to **Render** (free web hosting) with **neon.tech** (free PostgreSQL database).

> **No prior experience required.** Follow these steps exactly as written.

---

## Table of Contents

1. [Overview](#overview)
2. [Step 1: Set Up GitHub Repository](#step-1-set-up-github-repository)
3. [Step 2: Create neon.tech Database](#step-2-create-neontech-database)
4. [Step 3: Deploy to Render](#step-3-deploy-to-render)
5. [Step 4: Configure Environment Variables](#step-4-configure-environment-variables)
6. [Step 5: Database & Admin (Automatic!)](#step-5-database--admin-automatic)
7. [Post-Deployment: Regular Use](#post-deployment-regular-use)
8. [Troubleshooting](#troubleshooting)

---

## Overview

### What We're Building

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Your Browser  │────▶│   Render (Free)  │────▶│  neon.tech      │
│                 │     │   Web Server     │     │  PostgreSQL     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌──────────────────┐
                        │  GitHub Repo     │
                        │  (Code Storage)  │
                        └──────────────────┘
```

### Services Used

| Service | Purpose | Cost | Why |
|---------|---------|------|-----|
| **GitHub** | Code storage | Free | Version control & collaboration |
| **Render** | Web hosting | Free tier | Runs your Flask app 24/7 |
| **neon.tech** | PostgreSQL database | Free tier | Persistent data storage |

---

## Step 1: Set Up GitHub Repository

### 1.1 Create a GitHub Account

1. Go to https://github.com/signup
2. Enter your email, create password, choose username
3. Verify your email address
4. Select "Free" plan when prompted

### 1.2 Create a New Repository

1. Click the **+** button (top right) → **New repository**
2. Fill in:
   - **Repository name**: `ki-asset-management` (or any name you prefer)
   - **Description**: "Prague Club of Investors - Analyst Performance Tracker"
   - **Visibility**: Select **Private** (recommended for security)
   - ☑️ Check "Add a README file"
   - ☑️ Check "Add .gitignore" → Select **Python**
3. Click **Create repository**

### 1.3 Upload Your Code to GitHub

**Option A: Using Command Line (Recommended)**

Open Terminal/Command Prompt in your project folder:

```bash
# Navigate to your project folder
cd /path/to/your/project

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit files
git commit -m "Initial commit: KI Asset Management application"

# Connect to GitHub (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/ki-asset-management.git

# Push to GitHub
git branch -M main
git push -u origin main
```

**Option B: Using GitHub Desktop (Easier)**

1. Download GitHub Desktop: https://desktop.github.com/
2. Install and sign in with your GitHub account
3. Click **File** → **Add local repository**
4. Select your project folder
5. Click **Publish repository**
6. Keep "Keep this code private" checked
7. Click **Publish repository**

### 1.4 Verify Upload

1. Go to https://github.com/YOUR_USERNAME/ki-asset-management
2. You should see all your files (app/, templates/, etc.)

---

## Step 2: Create neon.tech Database

### 2.1 Create neon.tech Account

1. Go to https://neon.tech
2. Click **Sign Up**
3. Sign up with GitHub (easiest) or email
4. Verify your email if using email signup

### 2.2 Create a New Project

1. In neon.tech dashboard, click **New Project**
2. Enter:
   - **Project name**: `ki-asset-management`
   - **Database name**: `analyst_db`
3. Click **Create Project**
4. **IMPORTANT**: Wait 1-2 minutes for the database to be ready

### 2.3 Get Your Database Connection String

1. In your project dashboard, click **Connection Details** (or look for "Connect" button)
2. Select **PostgreSQL** as the connection type
3. Copy the connection string. It looks like:
   ```
   postgresql://username:password@hostname.neon.tech/database?sslmode=require
   ```
   
   **Example:**
   ```
   postgresql://user:password@ep-example-123456.us-east-2.aws.neon.tech/database?sslmode=require
   ```

4. **Save this somewhere safe** (you'll need it in Step 4)

### 2.4 Test Connection (Optional but Recommended)

If you have PostgreSQL installed locally:

```bash
psql "postgresql://username:password@hostname.neon.tech/database?sslmode=require"
```

You should see a PostgreSQL prompt (`database=>`). Type `\q` to exit.

---

## Step 3: Deploy to Render

### 3.1 Create Render Account

1. Go to https://render.com
2. Click **Get Started for Free**
3. Sign up with **GitHub** (recommended - connects automatically)
4. Authorize Render to access your GitHub repositories

### 3.2 Create New Web Service

1. In Render dashboard, click **New +** → **Web Service**
2. Find and select your `ki-asset-management` repository
3. Click **Connect**

### 3.3 Configure Web Service

Fill in the form:

| Setting | Value | Explanation |
|---------|-------|-------------|
| **Name** | `ki-asset-management` | Your app URL will be ki-asset-management.onrender.com |
| **Region** | Select closest to Prague (Frankfurt) | Lower latency |
| **Branch** | `main` | Which git branch to deploy |
| **Runtime** | `Python 3` | Flask runs on Python |
| **Build Command** | `pip install -r requirements.txt` | Installs dependencies |
| **Start Command** | `python render_start.py` | Auto-initializes DB and starts app |
| **Plan** | `Free` | No cost |

**⚠️ IMPORTANT**: Use `python render_start.py` (not `gunicorn` directly) - this script automatically initializes your database on first run!

Click **Create Web Service**

### 3.4 Wait for First Deploy

The service will deploy automatically. You'll see build logs streaming. Wait for it to complete (usually 2-3 minutes).

> **Note**: The app might show "Deploy failed" initially - this is OK! It just needs the environment variables we'll add next.

---

## Step 4: Configure Environment Variables

### 4.1 Open Environment Settings

1. In your Render service dashboard, click **Environment** (left sidebar)
2. Click **Add Environment Variable**

### 4.2 Add Required Variables

Add each variable one by one:

#### Required Variables

| Variable Name | Value | How to Get It |
|--------------|-------|---------------|
| `SECRET_KEY` | Generate random string | Run locally: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `USE_LOCAL_SQLITE` | `False` | Must be False for PostgreSQL |
| `DATABASE_URL` | Your neon.tech connection string | From Step 2.3 |
| `FLASK_ENV` | `production` | Tells Flask to run in production mode |
| `ADMIN_EMAIL` | Your email address | e.g., `admin@klubinvestoru.com` - used for auto-admin assignment |

#### Email Configuration (REQUIRED)

**⚠️ IMPORTANT:** Render free tier blocks SMTP (ports 587, 465, 25). You MUST use SendGrid API for email to work.

**Step 1: Create SendGrid Account**
1. Go to https://sendgrid.com and sign up (free tier: 100 emails/day)
2. Verify your email address
3. Complete the account setup

**Step 2: Verify Sender Email**
1. In SendGrid dashboard, go to **Settings** → **Sender Authentication**
2. Click **Verify a Single Sender**
3. Fill in your details:
   - From Name: `KI Asset Management`
   - From Email: `admin@klubinvestoru.com` (your ADMIN_EMAIL)
   - Reply To: same as From Email
4. Check your email and click the verification link

**Step 3: Create API Key**
1. Go to **Settings** → **API Keys**
2. Click **Create API Key**
3. Name: `KI Asset Management Production`
4. Permissions: **Full Access** (or restrict to "Mail Send" only)
5. Click **Create & View**
6. **COPY THE API KEY IMMEDIATELY** (you won't see it again!)

**Step 4: Add Environment Variables**

| Variable Name | Value | Notes |
|--------------|-------|-------|
| `SENDGRID_API_KEY` | `SG.xxx...` | Your SendGrid API key from Step 3 |
| `MAIL_DEFAULT_SENDER` | `admin@klubinvestoru.com` | Must match your verified sender email |

**Optional: For Local Development (SMTP)**

If you want to test email locally with Gmail:

| Variable Name | Value | Notes |
|--------------|-------|-------|
| `MAIL_SERVER` | `smtp.gmail.com` | Gmail SMTP server |
| `MAIL_PORT` | `587` | Gmail SMTP port |
| `MAIL_USE_TLS` | `true` | Enable TLS encryption |
| `MAIL_USERNAME` | your-email@gmail.com | Sender email address |
| `MAIL_PASSWORD` | your-app-password | Gmail App Password |
| `MAIL_DEFAULT_SENDER` | your-email@gmail.com | Same as MAIL_USERNAME |

### 4.3 Save and Redeploy

1. After adding all variables, they save automatically
2. Go back to your service dashboard
3. Click **Manual Deploy** → **Deploy latest commit**
4. Wait 2-3 minutes for deployment

---

## Step 5: Database & Admin (Automatic!)

✅ **Good news**: Everything initializes automatically! No Shell needed.

When you set the environment variables and deploy, `render_start.py` will:
1. Check if database tables exist
2. Create them if missing
3. Start the Gunicorn server

### Admin Setup (Two Options)

#### Option A: Register as Admin (Recommended)

The simplest approach - just register with your admin email:

1. Go to `/auth/register`
2. Register with the email you set as `ADMIN_EMAIL` (e.g., `admin@klubinvestoru.com`)
3. Check your email and click the verification link
4. You'll be automatically made an admin because your email matches `ADMIN_EMAIL`

**How it works**: During registration, if your email matches `ADMIN_EMAIL`, you get `is_admin=True` automatically.

#### Option B: Pre-create Admin User

If you want the admin user to exist immediately without registering:

1. Add BOTH of these environment variables in Render:

| Variable | Value | Example |
|----------|-------|---------|
| `ADMIN_EMAIL` | Your admin email | `admin@klubinvestoru.com` |
| `ADMIN_PASSWORD` | Strong password | `YourSecurePass123!` |

2. Redeploy
3. The app will create the admin user automatically
4. Log in directly with these credentials

### What You'll See in Logs

Open the **Logs** tab in your Render service:

**For Option A (registration):**
```
============================================================
DATABASE INITIALIZATION
============================================================
Creating database tables...
✓ Database tables created successfully!
ℹ Admin auto-creation skipped (ADMIN_EMAIL and/or ADMIN_PASSWORD not set)
ℹ The first user to register with ADMIN_EMAIL will become admin automatically
```

**For Option B (pre-created):**
```
============================================================
AUTO-ADMIN CREATED
============================================================
Admin user created: admin@klubinvestoru.com
You can now log in with this account.
============================================================
```

---

### Test Your Application

1. Open your app's URL: `https://ki-asset-management.onrender.com`
   (Replace with your actual service name)

2. You should see the main page loading

3. Try logging in:
   - Go to `/auth/login`
   - Enter the admin email and password
   - You should be logged in successfully

---

## Post-Deployment: Regular Use

### 🔄 Updating Your Website (New Versions)

The beauty of this setup: **Deploying updates is automatic!**

#### Simple Update Process

1. **Make changes locally** (edit files, test locally)

2. **Commit and push**:
   ```bash
   git add .
   git commit -m "Description of what changed"
   git push origin main
   ```

3. **Render automatically redeploys**:
   - Go to your Render dashboard
   - Watch the build logs (takes 2-3 minutes)
   - Your live site updates automatically!

#### What Happens During Update?

```
You: git push origin main
    ↓
GitHub: Receives new code
    ↓
Render: Detects push → Starts new build
    ↓
Build: pip install -r requirements.txt
    ↓
Start: python render_start.py
    ↓
Live: New version running at your URL!
```

#### Rolling Back (If Something Breaks)

If you push something that breaks:

**Option 1: Quick Rollback in Render**
1. Go to Render dashboard → Your service
2. Click **Manual Deploy** → **Deploy a specific commit**
3. Select the last working commit
4. Click **Deploy**

**Option 2: Revert in Git**
```bash
# Revert last commit
git revert HEAD

# Push the revert
git push origin main
```

### Updating Without Downtime

Render free tier has a brief restart when deploying (30-60 seconds). Users might see a "Service Unavailable" page briefly. This is normal for free tier.

### Database Changes

If your update includes database changes (new tables/columns):

1. **The `render_start.py` script handles this automatically**
2. It runs `db.create_all()` which adds new tables
3. For complex migrations, you may need to run SQL manually via neon.tech dashboard

### Database Backups (neon.tech)

neon.tech automatically backs up your database:
- Free tier: 7 days of backup history
- To restore: Go to neon.tech dashboard → Branches → Restore

### Viewing Logs

If something isn't working:

1. In Render dashboard, click your service
2. Click **Logs** (top menu)
3. Look for error messages (red text)

---

## Troubleshooting

### Issue: "Application failed to start"

**Solution:**
1. Check logs in Render dashboard
2. Most common cause: Missing `SECRET_KEY` or `DATABASE_URL`
3. Go to Environment tab and verify all variables are set

### Issue: "Database connection failed"

**Solution:**
1. Verify `DATABASE_URL` is correct (copy from neon.tech again)
2. Ensure `USE_LOCAL_SQLITE=False`
3. Check that neon.tech database is active (not suspended)

### Issue: "Build failed"

**Solution:**
1. Check that `requirements.txt` is in your GitHub repo
2. Verify all dependencies are listed
3. Try build command locally: `pip install -r requirements.txt`

### Issue: "404 Not Found" when visiting site

**Solution:**
1. Wait 2-3 minutes after deployment (Render takes time to start)
2. Check that your service shows "Live" status (green dot)
3. Try accessing with `https://` (not `http://`)

### Issue: Database tables don't exist

**Solution:**
1. Check the logs - `render_start.py` should create them automatically
2. If it failed, check that `DATABASE_URL` is correct
3. Try redeploying: Manual Deploy → Deploy latest commit
4. If still failing, check logs for specific error messages

### Issue: Can't log in as admin

**Solution:**
1. Check Render logs for the auto-generated password (search for "WARNING: Using randomly generated")
2. Make sure you're using the correct email (default: `admin@klubinvestoru.com`)
3. If you set `ADMIN_EMAIL`/`ADMIN_PASSWORD` variables, use those values
4. Try resetting password using "Forgot Password" if email is configured
5. As last resort, delete the admin user from neon.tech dashboard and redeploy

---

## Security Checklist

Before sharing your app with others, verify:

- [x] `.env` file is in `.gitignore` (never committed to GitHub)
- [x] `SECRET_KEY` is strong and unique (32+ random characters)
- [x] Database uses SSL (`sslmode=require` in neon.tech URL)
- [x] Admin password is strong (12+ characters, mixed case, numbers)
- [x] Repository is **Private** on GitHub
- [x] Only necessary team members have Render access

---

## Free Tier Limits

### Render Free Tier
- **Web Service**: Runs 24/7, spins down after 15 min inactivity
- **Bandwidth**: 100 GB/month
- **Build minutes**: 500 minutes/month
- **Disk**: Ephemeral (files not saved between restarts)

### Keep Your Service Awake (Prevent Sleeping)

Render's free tier spins down after 15 minutes of inactivity, causing a 30-60 second delay when someone visits your site after it's been idle. To prevent this, use a **ping service** to keep it awake.

#### Option 1: UptimeRobot (Recommended - Free)

**Setup:**
1. Go to [https://uptimerobot.com](https://uptimerobot.com) and sign up for free
2. Click **Add New Monitor**
3. Configure:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: `KI Asset Management`
   - **URL**: Your Render app URL (e.g., `https://ki-asset-management.onrender.com`)
   - **Monitoring Interval**: `5 minutes` (free tier minimum)
4. Click **Create Monitor**

✅ UptimeRobot will ping your site every 5 minutes, keeping it awake 24/7.

#### Option 2: UptimeReboot (Alternative)

**Setup:**
1. Go to [https://uptimereboot.com](https://uptimereboot.com)
2. Sign up for a free account
3. Add your Render app URL
4. Set interval to 5-10 minutes

#### Option 3: Cron-Job.org (Free)

**Setup:**
1. Go to [https://cron-job.org](https://cron-job.org)
2. Create account and add a new cron job
3. Set URL to your Render app
4. Set schedule to every 5 minutes

> 💡 **Tip**: You only need ONE of these services. UptimeRobot is the most popular and reliable option.

### neon.tech Free Tier
- **Storage**: 0.5 GB
- **Compute**: Autoscales to zero (may have cold start delay)
- **Connections**: 20 concurrent connections
- **Projects**: 1 project

### When to Upgrade

Consider upgrading when:
- Database exceeds 0.5 GB
- You need more than 20 concurrent users
- Cold start delays become annoying (2-3 seconds)
- Build minutes exceed 500/month

---

## Need Help?

### Support Links
- **Render Docs**: https://render.com/docs
- **neon.tech Docs**: https://neon.tech/docs
- **Flask Docs**: https://flask.palletsprojects.com/

### Emergency Contacts
If you need help with the deployment:
- Check the documentation links above
- Create an issue in the GitHub repository
- Contact your organization's IT team

---

**Congratulations!** Your application is now live on the internet! 🎉

Remember: The free tier is perfectly fine for a club of ~20-50 users. Only upgrade if you hit the limits above.
