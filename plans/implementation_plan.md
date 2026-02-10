# Implementation Plan

## Project Overview
Build a Flask web application for tracking analyst performance based on a Notion‑exported CSV, using Yahoo Finance data, with password protection for `@klubinvestoru.com` emails and an admin panel.

## Prerequisites
- Python 3.9+
- SQLite
- Internet access for Yahoo Finance and optional DeepSeek API.

## Step‑by‑Step Implementation

### Phase 1: Project Setup
1. **Create virtual environment** and install dependencies (`requirements.txt`).
2. **Initialize Flask project structure** as outlined in `flask_structure.md`.
3. **Set up configuration** (`config.py`) with development/production profiles.
4. **Initialize extensions** (`extensions.py`): SQLAlchemy, LoginManager, Mail, etc.
5. **Create `app/__init__.py`** application factory.

### Phase 2: Database Models
1. **Define SQLAlchemy models** in `app/models.py` reflecting the schema from `schema.md`.
2. **Add relationships** (many‑to‑many for analysts‑analyses).
3. **Implement password hashing** using `werkzeug.security` or `bcrypt`.
4. **Create database initialization script** (`create_db.py`) or use Flask‑Migrate.

### Phase 3: Authentication Blueprint
1. **Create `app/auth/`** with routes, forms, utils.
2. **Implement registration flow**:
   - Email domain validation.
   - Token generation and storage.
   - Sending password‑setup email via Flask‑Mail.
3. **Implement login/logout** using Flask‑Login.
4. **Implement password reset flow**.
5. **Create templates** for login, register, forgot‑password, reset‑password.
6. **Add role‑based decorators** (`@admin_required`).

### Phase 4: Core Utilities
1. **CSV import module** (`app/utils/csv_import.py`):
   - Parse CSV with `csv` or `pandas`.
   - Map columns to database fields.
   - Handle multiple analysts per row.
   - Integrate ticker resolution (call DeepSeek or Yahoo).
   - Store analyses and link to analysts.
2. **Yahoo Finance helper** (`app/utils/yfinance_helper.py`):
   - Fetch historical prices.
   - Search ticker by company name.
3. **DeepSeek client** (`app/utils/deepseek_client.py`) – optional.
4. **Performance calculation module** (`app/utils/performance.py`):
   - Compute returns for approved analyses.
   - Aggregate analyst metrics.

### Phase 5: Admin Blueprint
1. **Create `app/admin/`** with routes and forms.
2. **Implement user management**:
   - List users, toggle active, promote/admin.
   - Create user (manual invitation).
3. **CSV upload page**:
   - File upload handling.
   - Background processing with progress feedback.
   - Display upload history.
4. **Performance calculation page**:
   - Trigger recalculation.
   - Show analyst ranking.
5. **Activity logs page** – display logs from database.
6. **Settings page** – edit system settings (store in DB or config file).
7. **Create admin templates** using Bootstrap.

### Phase 6: Analyst Blueprint
1. **Create `app/analyst/`** with routes.
2. **Dashboard** – show summary metrics and recent analyses.
3. **Performance detail page** – table of approved analyses with returns.
4. **Ensure data isolation** (each analyst sees only their own analyses).

### Phase 7: Main Blueprint & UI Polish
1. **Landing page** (`app/main/routes.py`).
2. **Base template** (`templates/base.html`) with navigation conditional on role.
3. **Static assets** (CSS, JS) – style with Bootstrap 5.
4. **Responsive design** adjustments.
5. **Add icons** (Bootstrap Icons).

### Phase 8: Testing & Validation
1. **Unit tests** for authentication, CSV import, performance calculation.
2. **Integration tests** for admin and analyst flows.
3. **Manual testing** with sample CSV.
4. **Security review** (CSRF, SQL injection, XSS).

### Phase 9: Deployment Preparation
1. **Production configuration** (environment variables, secret key, SMTP credentials).
2. **Database migrations** (if using Flask‑Migrate).
3. **WSGI setup** (gunicorn, waitress).
4. **Dockerize** (optional).

## File Structure (Detailed)

```
analyst_website/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── forms.py
│   │   └── utils.py
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── forms.py
│   │   └── utils.py
│   ├── analyst/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── utils.py
│   ├── main/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   ├── register.html
│   │   │   ├── forgot_password.html
│   │   │   └── reset_password.html
│   │   ├── admin/
│   │   │   ├── dashboard.html
│   │   │   ├── users.html
│   │   │   ├── upload_csv.html
│   │   │   ├── performance.html
│   │   │   ├── activity_logs.html
│   │   │   └── settings.html
│   │   ├── analyst/
│   │   │   ├── dashboard.html
│   │   │   └── performance.html
│   │   └── main/
│   │       └── index.html
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   ├── js/
│   │   │   └── app.js
│   │   └── images/
│   └── utils/
│       ├── __init__.py
│       ├── csv_import.py
│       ├── yfinance_helper.py
│       ├── deepseek_client.py
│       ├── performance.py
│       └── validators.py
├── migrations/ (optional)
├── instance/
│   ├── config.py
│   └── analyst.db
├── tests/
│   ├── test_auth.py
│   ├── test_admin.py
│   └── test_utils.py
├── requirements.txt
├── .env.example
├── .gitignore
├── run.py
└── wsgi.py
```

## Dependencies (`requirements.txt`)

```
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
Flask-Login==0.6.3
Flask-WTF==1.1.1
Flask-Mail==0.9.1
python-dotenv==1.0.0
yfinance==0.2.28
pandas==2.1.4
requests==2.31.0
bcrypt==4.1.2
email-validator==2.1.0
```

## Configuration Variables (`.env`)

```
SECRET_KEY=your-secret-key
SQLALCHEMY_DATABASE_URI=sqlite:///instance/analyst.db
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
DEEPSEEK_API_KEY=optional
ALLOWED_EMAIL_DOMAIN=klubinvestoru.com
```

## Key Implementation Notes

### Token Management
- Use `itsdangerous` for signing tokens or store hashed tokens in DB.
- Token expiry: 24 hours for registration, 1 hour for password reset.

### Background Processing
- For long CSV imports, consider using `threading` or `celery`. Simpler approach: process synchronously with progress updates via AJAX polling.

### Error Handling
- Catch `yfinance` network errors and log.
- Validate CSV encoding and format.
- Provide user‑friendly error messages.

### Security
- Never expose API keys in frontend.
- Use HTTPS in production.
- Sanitize user input in templates.

## Success Criteria
1. Users with `@klubinvestoru.com` can register, set password, and log in.
2. Admin can upload CSV, which populates analyses and auto‑creates analyst accounts if enabled.
3. Admin can trigger performance calculation and see analyst ranking.
4. Each analyst sees their own dashboard with performance metrics.
5. System correctly calculates returns based on Yahoo Finance data.
6. Activity logs record key actions.

## Next Steps
- Review this plan with the stakeholder.
- Adjust based on feedback.
- Switch to **Code mode** to begin implementation.

## Estimated Effort
- **Phase 1‑3**: 2‑3 days
- **Phase 4‑6**: 3‑4 days
- **Phase 7‑9**: 1‑2 days
Total: ~1‑2 weeks of development.

*Note: Time estimates are approximate and depend on developer experience.*