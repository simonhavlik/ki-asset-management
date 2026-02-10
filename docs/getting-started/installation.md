# Getting Started

Welcome! This guide will help you set up the KI Asset Management application locally for development or testing.

---

## Prerequisites

Before you begin, ensure you have:

- [ ] **Python 3.10 or higher** installed (`python --version`)
- [ ] **Git** installed (`git --version`)
- [ ] **500MB** free disk space
- [ ] **1GB RAM** minimum

---

## Quick Setup (5 Minutes)

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/ki-asset-management.git
cd ki-asset-management
```

### 2. Create Virtual Environment

**Linux / macOS:**
```bash
python -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

> 💡 **Tip:** You'll know the virtual environment is active when you see `(venv)` in your terminal prompt.

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install Flask, SQLAlchemy, and all other required packages.

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```bash
SECRET_KEY=your-super-secret-random-key-here
FLASK_ENV=development
USE_LOCAL_SQLITE=True
```

> 💡 **Generate a secure key:** Run `python -c "import secrets; print(secrets.token_hex(32))"`

**For email functionality** (required for user registration):

```bash
# Using Gmail SMTP (for local development)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-gmail-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

See [Environment Variables Reference](../reference/environment-variables.md) for all options.

### 5. Initialize Database

```bash
flask init-db
```

This creates the SQLite database and all required tables.

### 6. Create Admin User

```bash
flask create-admin
```

When prompted:
- Enter your `@klubinvestoru.com` email
- Set a secure password
- You'll now have admin access

### 7. Run the Application

```bash
flask run
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

🎉 **Success!** The application is now running locally.

---

## Platform-Specific Instructions

### Arch Linux / Manjaro

```bash
# Install Python and Git
sudo pacman -S python python-pip git

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# If you get "externally-managed-environment" error:
pip install -r requirements.txt --break-system-packages
# OR use the venv method above (recommended)
```

### Debian / Ubuntu / Linux Mint

```bash
# Install Python and Git
sudo apt update
sudo apt install python3 python3-pip python3-venv git -y

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# If psycopg2 fails, install:
sudo apt install python3-dev libpq-dev -y
```

### macOS

```bash
# Install Homebrew if not present: https://brew.sh
# Then install Python
brew install python git

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Verification

After setup, verify everything works:

```bash
# Check Flask is installed
flask --version

# Verify database exists
ls -la instance/analyst.db

# Run the development server
flask run
```

Visit these URLs to confirm:
- Main page: [http://127.0.0.1:5000](http://127.0.0.1:5000)
- Admin login: [http://127.0.0.1:5000/auth/login](http://127.0.0.1:5000/auth/login)

---

## Next Steps

Now that you're set up:

1. **[First Steps](first-steps.md)** - Learn the basics and initial configuration
2. **[Development Guide](../development/README.md)** - Start contributing code
3. **[User Guides](../user-guides/README.md)** - Learn to use the application

---

## Troubleshooting

**Issue: `pip: command not found`**
- **Solution:** Ensure Python is properly installed and in your PATH
- **Linux:** `sudo apt install python3-pip`

**Issue: `No module named 'flask'`**
- **Solution:** Virtual environment not activated
- **Fix:** Run `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)

**Issue: `Permission denied` when installing packages**
- **Solution:** Never use `sudo pip`. Always use virtual environment.

**Issue: `Unable to open database file`**
- **Solution:** Create the instance directory: `mkdir -p instance && chmod 755 instance`

**Issue: `Port 5000 already in use`**
- **Solution:** Use a different port: `flask run --port=5001`

---

## Getting Help

- Check our [Troubleshooting Guide](../operations/troubleshooting.md)
- Review [Common Issues](../operations/troubleshooting.md#common-issues)
- See [AI Assistant Orientation](../AI-ORIENTATION.md) for technical details
