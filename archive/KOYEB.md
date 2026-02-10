# Deployment Guide: Koyeb + neon.tech

This guide will walk you through deploying the KI Asset Management application to **Koyeb** (modern serverless platform) with **neon.tech** (free PostgreSQL database).

> **No prior experience required.** Follow these steps exactly as written.

---

## Table of Contents

1. [Overview](#overview)
2. [Step 1: Set Up GitHub Repository](#step-1-set-up-github-repository)
3. [Step 2: Create neon.tech Database](#step-2-create-neontech-database)
4. [Step 3: Deploy to Koyeb](#step-3-deploy-to-koyeb)
5. [Step 4: Configure Environment Variables](#step-4-configure-environment-variables)
6. [Step 5: Database & Admin Setup](#step-5-database--admin-setup)
7. [Post-Deployment: Regular Use](#post-deployment-regular-use)
8. [Troubleshooting](#troubleshooting)

---

## Overview

### What We're Building

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Your Browser  │────▶│   Koyeb (Free)   │────▶│  neon.tech      │
│                 │     │   Web Service    │     │  PostgreSQL     │
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
| **Koyeb** | Web hosting | Free tier | Serverless, fast cold starts |
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

## Step 3: Deploy to Koyeb

### 3.1 Create Koyeb Account

1. Go to https://www.koyeb.com
2. Click **Start for Free**
3. Sign up with **GitHub** (recommended - connects automatically)
4. Authorize Koyeb to access your GitHub repositories

### 3.2 Create New Web Service

1. In Koyeb dashboard, click **Create Web Service**
2. Select **Deploy a GitHub repository**
3. Find and select your `ki-asset-management` repository
4. Click **Import Repository** (if it's your first time) or select it

### 3.3 Configure Web Service

Fill in the deployment form:

| Setting | Value | Explanation |
|---------|-------|-------------|
| **Name** | `ki-asset-management` | Your app URL will be ki-asset-management.koyeb.app |
| **Region** | Select closest to Prague (Frankfurt or Paris) | Lower latency |
| **Branch** | `main` | Which git branch to deploy |
| **Runtime** | `Python` | Flask runs on Python |
| **Python Version** | `3.10` or `3.11` | Select Python 3.10+ |
| **Build Command** | `pip install -r requirements.txt` | Installs dependencies |
| **Start Command** | `gunicorn app:create_app()` | Starts the Flask app |
| **Port** | `8000` | Koyeb's default port |

Click **Advanced** → Make sure **Web Service** is selected (not Worker)

Click **Deploy**

### 3.4 Wait for First Deploy

The service will deploy automatically. You'll see build logs streaming. Wait for it to complete (usually 2-3 minutes).

> **Note**: The app might show an error initially - this is OK! It just needs the environment variables we'll add next.

---

## Step 4: Configure Environment Variables

### 4.1 Open Environment Settings

1. In your Koyeb service dashboard, click **Settings** tab
2. Click **Environment Variables** section
3. Click **Add Environment Variable**

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
| `PORT` | `8000` | Koyeb's expected port |

#### Email Configuration (REQUIRED)

**⚠️ IMPORTANT:** Koyeb free tier allows outbound connections, but SendGrid is still recommended for reliable email delivery.

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

**Optional: SMTP Configuration (Alternative to SendGrid)**

If you prefer to use SMTP instead of SendGrid:

| Variable Name | Value | Notes |
|--------------|-------|-------|
| `MAIL_SERVER` | `smtp.gmail.com` | Gmail SMTP server |
| `MAIL_PORT` | `587` | Gmail SMTP port |
| `MAIL_USE_TLS` | `true` | Enable TLS encryption |
| `MAIL_USERNAME` | your-email@gmail.com | Sender email address |
| `MAIL_PASSWORD` | your-app-password | Gmail App Password |
| `MAIL_DEFAULT_SENDER` | your-email@gmail.com | Same as MAIL_USERNAME |

### 4.3 Save and Redeploy

1. After adding all variables, click **Save** at the bottom
2. Koyeb will automatically redeploy
3. Wait 2-3 minutes for deployment

---

## Step 5: Database & Admin Setup

### 5.1 Initialize Database

Unlike Render's auto-initialization, you'll need to manually initialize the database on first deploy:

**Method 1: Using Koyeb Console (Recommended)**

1. In Koyeb dashboard, click your service
2. Go to **Overview** tab
3. Click **Console** (shell access)
4. Run the following commands:

```bash
flask init-db
```

You should see:
```
✓ Database tables created successfully!
```

### 5.2 Create Admin User

You have two options:

#### Option A: Register as Admin (Recommended)

The simplest approach - just register with your admin email:

1. Go to your app's URL: `https://ki-asset-management.koyeb.app`
2. Navigate to `/auth/register`
3. Register with the email you set as `ADMIN_EMAIL` (e.g., `admin@klubinvestoru.com`)
4. Check your email and click the verification link
5. You'll be automatically made an admin because your email matches `ADMIN_EMAIL`

**How it works**: During registration, if your email matches `ADMIN_EMAIL`, you get `is_admin=True` automatically.

#### Option B: Pre-create Admin User via Console

If you want the admin user to exist immediately:

1. Add `ADMIN_PASSWORD` environment variable in Koyeb:
   - Go to **Settings** → **Environment Variables**
   - Add: `ADMIN_PASSWORD` = `YourSecurePassword123!`
   - Save and wait for redeploy

2. Open Koyeb Console and run:

```bash
flask create-admin
```

3. Enter the email and password when prompted

### 5.3 Verify Everything Works

1. Open your app's URL: `https://ki-asset-management.koyeb.app`
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

3. **Koyeb automatically redeploys**:
   - Go to your Koyeb dashboard
   - Watch the build logs (takes 2-3 minutes)
   - Your live site updates automatically!

#### What Happens During Update?

```
You: git push origin main
    ↓
GitHub: Receives new code
    ↓
Koyeb: Detects push → Starts new build
    ↓
Build: pip install -r requirements.txt
    ↓
Start: gunicorn app:create_app()
    ↓
Live: New version running at your URL!
```

#### Rolling Back (If Something Breaks)

If you push something that breaks:

**Option 1: Quick Rollback in Koyeb**
1. Go to Koyeb dashboard → Your service
2. Click **Deployments** tab
3. Find the last working deployment
4. Click the **...** menu → **Redeploy this version**

**Option 2: Revert in Git**
```bash
# Revert last commit
git revert HEAD

# Push the revert
git push origin main
```

### Database Changes

If your update includes database changes (new tables/columns):

1. **Access Koyeb Console**:
   - Go to your service → **Console**

2. **Run migration commands**:
   ```bash
   flask init-db  # Creates new tables (safe to run multiple times)
   ```

3. For complex migrations, you may need to run SQL manually via neon.tech dashboard

### Database Backups (neon.tech)

neon.tech automatically backs up your database:
- Free tier: 7 days of backup history
- To restore: Go to neon.tech dashboard → Branches → Restore

### Viewing Logs

If something isn't working:

1. In Koyeb dashboard, click your service
2. Go to **Logs** tab
3. Look for error messages (red text)
4. You can filter by time and severity

---

## Troubleshooting

### Issue: "Application failed to start"

**Solution:**
1. Check logs in Koyeb dashboard (Logs tab)
2. Most common cause: Missing `SECRET_KEY` or `DATABASE_URL`
3. Go to Settings → Environment and verify all variables are set
4. Check that `PORT` is set to `8000`

### Issue: "Database connection failed"

**Solution:**
1. Verify `DATABASE_URL` is correct (copy from neon.tech again)
2. Ensure `USE_LOCAL_SQLITE=False`
3. Check that neon.tech database is active (not suspended)
4. Make sure the connection string includes `?sslmode=require`

### Issue: "Build failed"

**Solution:**
1. Check that `requirements.txt` is in your GitHub repo
2. Verify all dependencies are listed
3. Try build command locally: `pip install -r requirements.txt`
4. Check if any Python version conflicts (use Python 3.10 or 3.11)

### Issue: "404 Not Found" when visiting site

**Solution:**
1. Wait 2-3 minutes after deployment (Koyeb takes time to start)
2. Check that your service shows "Healthy" status (green dot)
3. Try accessing with `https://` (not `http://`)
4. Verify your domain is correct: `ki-asset-management.koyeb.app`

### Issue: Database tables don't exist

**Solution:**
1. Open Koyeb Console
2. Run: `flask init-db`
3. If it fails, check that `DATABASE_URL` is correct
4. Try redeploying: Settings → Save (forces redeploy)

### Issue: Can't log in as admin

**Solution:**
1. Make sure you registered with the exact `ADMIN_EMAIL` address
2. Check your email for the verification link
3. If email isn't working, use the Console to create admin directly:
   ```bash
   flask create-admin
   ```
4. As last resort, delete the admin user from neon.tech dashboard and recreate

### Issue: Emails not sending

**Solution:**
1. Verify `SENDGRID_API_KEY` is correct
2. Check that `MAIL_DEFAULT_SENDER` matches your verified sender in SendGrid
3. Look for email errors in Koyeb logs
4. Test with a different email provider (SMTP instead of SendGrid)

---

## Security Checklist

Before sharing your app with others, verify:

- [x] `.env` file is in `.gitignore` (never committed to GitHub)
- [x] `SECRET_KEY` is strong and unique (32+ random characters)
- [x] Database uses SSL (`sslmode=require` in neon.tech URL)
- [x] Admin password is strong (12+ characters, mixed case, numbers)
- [x] Repository is **Private** on GitHub
- [x] Only necessary team members have Koyeb access
- [x] SendGrid API key is kept secret (not in logs)

---

## Free Tier Limits

### Koyeb Free Tier
- **Web Services**: 1 service, always on (no sleeping)
- **Instance Type**: Nano (0.25 vCPU, 512MB RAM)
- **Bandwidth**: 100 GB/month
- **Build time**: 100 build minutes/month
- **Custom domains**: Supported with automatic SSL

### neon.tech Free Tier
- **Storage**: 0.5 GB
- **Compute**: Autoscales to zero (may have cold start delay ~1-2 seconds)
- **Connections**: 20 concurrent connections
- **Projects**: 1 project

### When to Upgrade

Consider upgrading when:
- You need more than 1 web service
- Database exceeds 0.5 GB
- You need more than 20 concurrent users
- Cold start delays become annoying (1-2 seconds on neon.tech free tier)
- Build minutes exceed 100/month

---

## Comparison: Koyeb vs Render

| Feature | Koyeb | Render |
|---------|-------|--------|
| **Free tier uptime** | Always on | 24/7 (but sleeps after 15 min) |
| **Cold starts** | None | ~30 seconds wake-up |
| **Server locations** | Frankfurt, Paris, etc. | Frankfurt, Oregon, etc. |
| **Custom domains** | Free SSL | Free SSL |
| **Build speed** | Fast | Moderate |
| **Console access** | Yes (web-based) | Yes (SSH-like) |
| **Email (SMTP)** | Allowed | Blocked on free tier |

**Recommendation**: Use Koyeb if you want always-on service with no cold starts. Use Render if you prefer a more mature platform with extensive documentation.

---

## Need Help?

### Support Links
- **Koyeb Docs**: https://www.koyeb.com/docs
- **neon.tech Docs**: https://neon.tech/docs
- **Flask Docs**: https://flask.palletsprojects.com/

### Emergency Contacts
If you need help with the deployment:
- Check the documentation links above
- Create an issue in the GitHub repository
- Contact your organization's IT team

---

**Congratulations!** Your application is now live on Koyeb! 🎉

Remember: The free tier is perfectly fine for a club of ~20-50 users. Only upgrade if you hit the limits above.
