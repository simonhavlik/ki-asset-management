# Environment Variables Reference

Complete reference for all environment variables used by KI Asset Management.

---

## ⚠️ Required Variables

These **must** be set for the application to run:

### Core Application

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for sessions | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_ENV` | Environment mode | `development` or `production` |

### Database (Choose ONE)

**Option 1: SQLite (Development)**
```bash
USE_LOCAL_SQLITE=True
```

**Option 2: PostgreSQL (Production)**
```bash
USE_LOCAL_SQLITE=False
DATABASE_URL=postgresql://user:password@host.neon.tech/db?sslmode=require
```

---

## 📧 Email Configuration (REQUIRED)

Email is required for user registration and password reset.

**Option 1: SendGrid (Recommended for Production)**

| Variable | Description | Example |
|----------|-------------|---------|
| `SENDGRID_API_KEY` | SendGrid API key | `SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `MAIL_DEFAULT_SENDER` | Default from address | `admin@klubinvestoru.com` |

**Option 2: SMTP (Local Development)**

| Variable | Description | Example |
|----------|-------------|---------|
| `MAIL_SERVER` | SMTP server | `smtp.gmail.com` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_USE_TLS` | Use TLS encryption | `true` |
| `MAIL_USERNAME` | SMTP username | `your-email@gmail.com` |
| `MAIL_PASSWORD` | SMTP password | `your-app-password` |
| `MAIL_DEFAULT_SENDER` | Default from address | `your-email@gmail.com` |

---

## 🔌 Optional API Keys

### DeepSeek AI

Used for:
- AI-assisted ticker matching
- Blog SEO optimization
- Document processing

```bash
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Get key:** [platform.deepseek.com](https://platform.deepseek.com)

### Brave Search

Used for:
- Ticker lookup fallback
- Web search for company info

```bash
BRAVE_SEARCH_API_KEY=BSxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Get key:** [api.search.brave.com](https://api.search.brave.com)

### Unsplash

Used for:
- Blog featured images
- Image search and selection

```bash
UNSPLASH_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Get key:** [unsplash.com/developers](https://unsplash.com/developers)

---

## 👤 Admin Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `ADMIN_EMAIL` | Email that becomes admin automatically | `admin@klubinvestoru.com` |
| `ADMIN_PASSWORD` | Pre-create admin (optional) | `YourSecurePass123!` |
| `ALLOWED_EMAIL_DOMAIN` | Domain for registration | `klubinvestoru.com` |

**How it works:**
- If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set → Admin auto-created on deploy
- If only `ADMIN_EMAIL` is set → First user to register with this email becomes admin

---

## 🚀 Deployment Variables

### Render/Koyeb

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Port to bind to (Koyeb) | `8000` |

**Note:** Render auto-sets `PORT`, don't override.

### Docker

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Internal Docker network URL | `postgresql://user:pass@db:5432/dbname` |

---

## ⚡ Performance & Caching

| Variable | Description | Default |
|----------|-------------|---------|
| `NEON_OPTIMIZE` | Enable Neon.tech optimizations | `true` |
| `CACHE_TYPE` | Cache backend | `SimpleCache` |
| `CACHE_DEFAULT_TIMEOUT` | Default cache TTL | `300` (5 min) |
| `PUBLIC_DATA_CACHE_TIMEOUT` | Public page cache | `3600` (1 hour) |
| `STATIC_DATA_CACHE_TIMEOUT` | Static data cache | `86400` (24 hours) |
| `SHORT_CACHE_TIMEOUT` | Interactive content | `60` (1 min) |

**For Redis:**
```bash
CACHE_TYPE=RedisCache
CACHE_REDIS_URL=redis://localhost:6379/0
```

---

## 🔒 Security Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SESSION_COOKIE_SECURE` | HTTPS-only cookies | `True` (production) |
| `SESSION_COOKIE_HTTPONLY` | Prevent JS cookie access | `True` |
| `SESSION_COOKIE_SAMESITE` | CSRF protection | `Lax` |

**Note:** These are auto-configured based on `FLASK_ENV`, rarely need manual setting.

---

## 📋 Complete .env Example

```bash
# =============================================================================
# CORE CONFIGURATION (REQUIRED)
# =============================================================================
SECRET_KEY=your-super-secret-key-change-this-in-production
FLASK_ENV=production

# =============================================================================
# DATABASE (CHOOSE ONE)
# =============================================================================

# Option 1: Local Development (SQLite)
# USE_LOCAL_SQLITE=True

# Option 2: Production (PostgreSQL)
USE_LOCAL_SQLITE=False
DATABASE_URL=postgresql://username:password@hostname.neon.tech/database?sslmode=require

# =============================================================================
# EMAIL (REQUIRED - CHOOSE ONE)
# =============================================================================

# Option 1: SendGrid (Recommended for Production)
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MAIL_DEFAULT_SENDER=your-verified-sender@klubinvestoru.com

# Option 2: SMTP (Local Development Only)
# MAIL_SERVER=smtp.gmail.com
# MAIL_PORT=587
# MAIL_USE_TLS=true
# MAIL_USERNAME=your-email@gmail.com
# MAIL_PASSWORD=your-gmail-app-password
# MAIL_DEFAULT_SENDER=your-email@gmail.com

# =============================================================================
# EXTERNAL APIS (OPTIONAL)
# =============================================================================
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BRAVE_SEARCH_API_KEY=BSxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
UNSPLASH_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# =============================================================================
# ADMIN CONFIGURATION
# =============================================================================
ADMIN_EMAIL=admin@klubinvestoru.com
# ADMIN_PASSWORD=your-secure-password-here
ALLOWED_EMAIL_DOMAIN=klubinvestoru.com

# =============================================================================
# CACHING (OPTIONAL)
# =============================================================================
NEON_OPTIMIZE=true
CACHE_TYPE=SimpleCache
CACHE_DEFAULT_TIMEOUT=300
PUBLIC_DATA_CACHE_TIMEOUT=3600
STATIC_DATA_CACHE_TIMEOUT=86400

# =============================================================================
# KOYEB ONLY
# =============================================================================
PORT=8000
```

---

## 🔍 Variable Priority

1. **Environment variables** (highest priority)
2. **`.env` file** (loaded by python-dotenv)
3. **Config defaults** (lowest priority)

**Important:** Never commit `.env` to version control!

---

## 🆘 Troubleshooting Variables

**"SECRET_KEY not set"**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Copy output to .env
```

**"Database connection failed"**
- Check `DATABASE_URL` format
- Verify `USE_LOCAL_SQLITE` matches your database choice

**"Email not sending"**
- Verify SendGrid API key is active
- Check sender email is verified in SendGrid
- For SMTP: Use App Password, not account password

---

<p align="center">
  <strong>Keep your .env file secure and never commit it!</strong>
</p>
