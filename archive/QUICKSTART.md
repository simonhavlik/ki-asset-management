# Quick Start Guide

Get the KI Asset Management app running in 5 minutes.

## For Local Development (SQLite)

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/ki-asset-management.git
cd ki-asset-management

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment file
cp .env.example .env

# 5. Edit .env - set these values:
# SECRET_KEY=your-random-key-here
# USE_LOCAL_SQLITE=True

# 6. Initialize database
flask init-db

# 7. Create admin user
flask create-admin

# 8. Run!
flask run
```

Open http://127.0.0.1:5000

---

## For Production (Render + neon.tech or Koyeb + neon.tech)

### Step 1: Prepare Your Code
```bash
# Make sure everything is committed
git add .
git commit -m "Ready for deployment"
git push origin main
```

### Step 2: Create Database (neon.tech)
1. Go to https://neon.tech → Sign up with GitHub
2. Click **New Project** → Name: `ki-asset-management`
3. Copy the connection string from **Connection Details**

### Step 3: Deploy to Render
1. Go to https://render.com → Sign up with GitHub
2. Click **New +** → **Web Service**
3. Select your repository
4. Configure:
   - **Name**: `ki-asset-management`
   - **Runtime**: Python 3
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `gunicorn app:create_app()`
5. Click **Create Web Service**

### Step 4: Environment Variables
In Render dashboard, click **Environment**, then add:

```
SECRET_KEY=copy-from-output-of-python-c-secrets-token_hex-32
USE_LOCAL_SQLITE=False
DATABASE_URL=postgresql://... (paste from neon.tech)
FLASK_ENV=production
```

### Step 5: Initialize Database
1. In Render, click **Shell**
2. Run: `flask init-db`
3. Run: `flask create-admin`

### Done!
Your app is live at: `https://ki-asset-management.onrender.com`

**⚠️ Keep Your App Awake:**
Render free tier spins down after 15 min inactivity. To prevent cold starts:
1. Sign up at [https://uptimerobot.com](https://uptimerobot.com) (free)
2. Add monitor: Type=`HTTP(s)`, URL=`https://ki-asset-management.onrender.com`, Interval=`5 min`

---

### Alternative: Deploy to Koyeb (Always-On, No Cold Starts)

Want your app to stay awake without sleeping? Use Koyeb instead:

1. **Same preparation** - push to GitHub, create neon.tech database

2. **Deploy to Koyeb**
   - Go to https://www.koyeb.com → Sign up with GitHub
   - Click **Create Web Service** → Select your repo
   - Configure:
     - **Name**: `ki-asset-management`
     - **Build**: `pip install -r requirements.txt`
     - **Start**: `gunicorn app:create_app()`
     - **Port**: `8000`
   - Click **Deploy**

3. **Set Environment Variables** (same as Render, plus PORT=8000)

4. **Initialize Database** (Koyeb Console)
   - In Koyeb, click **Console**
   - Run: `flask init-db` then `flask create-admin`

Your app is live at: `https://ki-asset-management.koyeb.app`

📖 Full Koyeb guide: [KOYEB.md](KOYEB.md)

---

## Quick Commands Reference

| Task | Command |
|------|---------|
| Run locally | `flask run` |
| Initialize DB | `flask init-db` |
| Create admin | `flask create-admin` |
| Install deps | `pip install -r requirements.txt` |
| Deploy to GitHub | `git push origin main` |

---

## Environment Variables Quick Reference

| Variable | Local Dev | Production |
|----------|-----------|------------|
| `USE_LOCAL_SQLITE` | `True` | `False` |
| `DATABASE_URL` | Not needed | Required (neon.tech) |
| `SECRET_KEY` | Any string | Strong random (32+ chars) |
| `FLASK_ENV` | `development` | `production` |

---

## Troubleshooting Quick Fixes

**App won't start:**
- Check `.env` file exists
- Verify `SECRET_KEY` is set

**Database error:**
- Local: Run `flask init-db` again
- Production: Check `DATABASE_URL` in Render

**404 errors:**
- Wait 2-3 minutes after deployment
- Check service shows "Live" status

---

For detailed instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)
