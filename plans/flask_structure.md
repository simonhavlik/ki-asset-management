# Flask Application Structure

## Directory Layout

```
analyst_website/
├── app/
│   ├── __init__.py                 # Application factory
│   ├── config.py                   # Configuration classes
│   ├── models.py                   # SQLAlchemy models
│   ├── extensions.py               # Flask extensions (db, login, mail)
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── routes.py               # Login, logout, register, password reset
│   │   ├── forms.py                # WTForms for authentication
│   │   └── utils.py                # Email validation, token generation
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── routes.py               # Admin dashboard, user management, CSV upload, performance calculation
│   │   ├── forms.py                # Forms for admin actions
│   │   └── utils.py                # Admin‑specific helpers
│   ├── analyst/
│   │   ├── __init__.py
│   │   ├── routes.py               # Analyst dashboard, personal performance view
│   │   └── utils.py
│   ├── main/
│   │   ├── __init__.py
│   │   └── routes.py               # Public pages (home, about)
│   ├── templates/
│   │   ├── base.html               # Master template with navigation
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
│   │   │   └── activity_logs.html
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
│       ├── csv_import.py           # CSV parsing and database import
│       ├── yfinance_helper.py      # Fetch stock prices, map company to ticker
│       ├── deepseek_client.py      # Integrate DeepSeek API for ticker extraction
│       ├── performance.py          # Calculate returns, generate metrics
│       └── validators.py           # Custom validators (email domain, etc.)
├── migrations/                     # Alembic migrations (if used)
├── instance/                       # Instance folder (database, config secrets)
│   └── config.py                   # Instance‑specific config (not tracked)
├── tests/
│   ├── test_auth.py
│   ├── test_admin.py
│   └── test_utils.py
├── requirements.txt
├── .env.example                    # Environment variables template
├── .gitignore
├── run.py                          # Entry point for development server
└── wsgi.py                         # Production WSGI entry point
```

## Key Flask Extensions

- **Flask‑SQLAlchemy** – ORM for database interactions
- **Flask‑Login** – session management and user authentication
- **Flask‑WTF** – form handling and CSRF protection
- **Flask‑Mail** – sending password‑reset emails
- **Flask‑Migrate** (optional) – database migrations
- **python‑dotenv** – environment variable loading

## Configuration

Three configuration classes:
- `DevelopmentConfig` – debug enabled, SQLite in instance folder
- `ProductionConfig` – debug disabled, secure settings
- `TestingConfig` – in‑memory SQLite, disabled CSRF

Configuration options:
- `SECRET_KEY`
- `SQLALCHEMY_DATABASE_URI`
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`
- `DEEPSEEK_API_KEY` (optional)
- `ALLOWED_EMAIL_DOMAIN = "klubinvestoru.com"`

## Routing Overview

### Public Routes (`main` blueprint)
- `GET /` – landing page (login prompt)
- `GET /about` – information about the platform

### Authentication Routes (`auth` blueprint)
- `GET /login` – login form
- `POST /login` – authenticate user
- `GET /register` – registration form (email domain restricted)
- `POST /register` – create new account (sends password‑reset link)
- `GET /forgot‑password` – request password reset
- `POST /forgot‑password` – send reset email
- `GET /reset‑password/<token>` – reset password form
- `POST /reset‑password/<token>` – update password
- `GET /logout` – log out user

### Analyst Routes (`analyst` blueprint)
- `GET /dashboard` – personal dashboard with recent analyses and performance summary
- `GET /performance` – detailed performance table (approved analyses only)
- `GET /analyses` – list of all analyses where the user is listed as analyst/opponent

### Admin Routes (`admin` blueprint)
- `GET /admin/dashboard` – admin overview (stats, recent activity)
- `GET /admin/users` – list users, toggle active status, promote to admin
- `POST /admin/users/create` – create new user (manual invitation)
- `GET /admin/analyses` – browse all analyses with filter by status
- `GET /admin/upload` – CSV upload form
- `POST /admin/upload` – process uploaded CSV (async or immediate)
- `GET /admin/performance` – performance calculation panel with button to recalculate
- `POST /admin/performance/recalculate` – trigger recalculation for all approved analyses
- `GET /admin/activity` – view activity logs

## Authentication Flow

1. **Registration**: User provides email ending with `@klubinvestoru.com`. System sends a password‑setup link to that email (no pre‑set password).
2. **Password Setup**: Link contains a token that allows setting a password. After setting, account becomes active.
3. **Login**: Standard email/password authentication.
4. **Password Reset**: Standard “forgot password” flow with email token.
5. **Admin Creation**: First admin must be created via script or environment variable. Subsequent admins can be promoted by existing admins.

## Security Considerations

- Passwords hashed with `bcrypt` or `argon2`.
- CSRF protection on all forms.
- Session timeout after inactivity.
- Role‑based access control (admin vs analyst).
- Email domain restriction enforced at registration.
- SQL injection prevented by using ORM.
- XSS protection via template auto‑escaping.

## Next Steps

1. Create the directory structure and initial files.
2. Set up configuration and extensions.
3. Implement authentication blueprint.
4. Build admin and analyst blueprints.
5. Develop utility modules (CSV import, stock data fetching).
6. Write templates with responsive design.
7. Test and deploy.