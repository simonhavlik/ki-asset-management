# System Architecture

Technical architecture and design overview of KI Asset Management.

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Main Page   │  │   Dashboard  │  │  Analytics   │          │
│  │  (Public)    │  │  (Private)   │  │  (Private)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼ HTTP/HTTPS
┌─────────────────────────────────────────────────────────────────┐
│                    FLASK APPLICATION                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                      BLUEPRINTS                           │  │
│  │  ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────────────┐  │  │
│  │  │  main  │ │  auth  │ │  analyst │ │     admin      │  │  │
│  │  │(public)│ │(public)│ │(private) │ │   (private)    │  │  │
│  │  └────────┘ └────────┘ └──────────┘ └────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                      UTILITIES                            │  │
│  │  ┌────────────┐ ┌─────────────┐ ┌─────────────────────┐  │  │
│  │  │ csv_import │ │ performance │ │ yfinance_helper     │  │  │
│  │  └────────────┘ └─────────────┘ └─────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼ SQLAlchemy
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  SQLite (Dev)  │  PostgreSQL (Prod)  │  CSV Exports     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Database Schema

### Core Entities

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│     User        │     │     Analysis     │     │    Company      │
├─────────────────┤     ├──────────────────┤     ├─────────────────┤
│ id (PK)         │◄────┤ id (PK)          │────►│ id (PK)         │
│ email           │     │ company_id (FK)  │     │ name            │
│ password_hash   │     │ date             │     │ ticker_symbol   │
│ is_admin        │     │ sector           │     │ sector          │
│ full_name       │     │ comment          │     │ exchange        │
│ created_at      │     │ status           │     └─────────────────┘
└─────────────────┘     │ created_at       │
         │              └──────────────────┘
         │                        │
         │              ┌──────────────────┐
         │              │  AnalysisAnalyst │
         └─────────────►│  (junction table)│◄───────────────────────┘
                        └──────────────────┘
```

### Key Models

#### User
```python
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    full_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

#### Analysis
```python
class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))
    date = db.Column(db.Date, nullable=False)
    sector = db.Column(db.String(100))
    comment = db.Column(db.Text)
    status = db.Column(db.String(50), default='Scheduled')
    # Relationships
    company = db.relationship('Company', backref='analyses')
    analysts = db.relationship('User', secondary='analysis_analysts')
```

#### Company
```python
class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    ticker_symbol = db.Column(db.String(20))
    sector = db.Column(db.String(100))
    exchange = db.Column(db.String(50))
```

#### Performance Calculation
```python
class PerformanceCalculation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analyses.id'))
    price_at_buy = db.Column(db.Float)
    price_current = db.Column(db.Float)
    return_pct = db.Column(db.Float)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)
```

---

## 🔀 Request Flow

### Public Page Request

```
Browser → Nginx → Flask → Blueprint → Template → HTML → Browser
                    ↓
              Cache Check (optional)
```

### Authenticated Request

```
Browser → Nginx → Flask → Login Required → Blueprint → Database → Template → HTML → Browser
                              ↓
                    Check session/token
```

### API/Data Request

```
Browser → Nginx → Flask → Blueprint → Service Layer → External API → JSON → Browser
                                               ↓
                                         Yahoo Finance / DeepSeek
```

---

## 🔐 Security Architecture

### Authentication Flow

```
1. User submits login form
2. Flask-WTF validates CSRF token
3. Password verified against bcrypt hash
4. Flask-Login creates session
5. Session cookie set (HttpOnly, Secure, SameSite)
```

### Authorization Levels

| Level | Access | Decorator |
|-------|--------|-----------|
| Public | Landing page, blog | None |
| Authenticated | Dashboard, profile | `@login_required` |
| Admin | All admin functions | `@admin_required` |

### Security Headers

All responses include:
- `Content-Security-Policy`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (production)
- `Referrer-Policy: strict-origin-when-cross-origin`

---

## 🧩 Component Details

### Blueprints

| Blueprint | Purpose | Routes |
|-----------|---------|--------|
| `main` | Public pages | `/`, `/about`, `/terms` |
| `auth` | Authentication | `/login`, `/register`, `/logout` |
| `analyst` | Analyst dashboard | `/dashboard`, `/performance` |
| `admin` | Admin panel | `/admin/*` |
| `blog` | Blog system | `/blog/*` |

### Utility Modules

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `csv_import.py` | CSV parsing | `parse_csv()`, `import_analyses()` |
| `performance.py` | Calculations | `calculate_return()`, `get_analyst_metrics()` |
| `yahooquery_helper.py` | Stock prices | `get_current_price()`, `get_historical_price()` |
| `ticker_resolver.py` | AI ticker matching | `resolve_ticker()`, `search_company()` |
| `deepseek_client.py` | AI integration | `generate_completion()`, `extract_tickers()` |

---

## 🔄 Data Flow: Performance Calculation

```
1. Admin clicks "Recalculate Performance"
                    ↓
2. Query all approved analyses
                    ↓
3. For each analysis:
   ├─ Get ticker symbol from Company
   ├─ Fetch current price (Yahoo Finance)
   ├─ Fetch historical price at analysis date
   ├─ Calculate return percentage
   └─ Store in PerformanceCalculation
                    ↓
4. Aggregate metrics per analyst
                    ↓
5. Cache results
                    ↓
6. Display in dashboard
```

---

## 📦 Caching Strategy

### Cache Levels

1. **In-Memory Cache** (Flask-Caching)
   - Public page data
   - Stock prices (5 min TTL)
   - Performance metrics (1 hour TTL)

2. **Database Cache**
   - Performance calculations table
   - Last calculated timestamp

3. **Client Cache**
   - Static assets (CSS, JS, images)
   - 30-day expiry via Nginx/CDN

---

## 🚀 Deployment Architecture

### Production Setup

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   User      │────►│   Nginx     │────►│  Gunicorn   │
│   Browser   │     │   (Proxy)   │     │   (Flask)   │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                        ┌────────────────┐
                                        │ PostgreSQL 17  │
                                        │ (self-hosted)  │
                                        └────────────────┘
```

### Scaling Considerations

- **Horizontal**: Multiple Gunicorn workers (configured in systemd)
- **Database**: a single self-hosted PostgreSQL 17 instance (memory-capped)
- **Static Files**: Serve via Nginx or CDN
- **Caching**: Redis for distributed caching (optional)

---

## 🔧 Configuration

### Environment-Based Config

```python
# app/config.py
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/analyst.db'

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
```

### Configuration Priority

1. Environment variables (highest)
2. `.env` file
3. Config class defaults (lowest)

---

## 🧪 Testing Architecture

```
tests/
├── conftest.py              # Fixtures and configuration
├── test_auth.py             # Authentication tests
├── test_performance.py      # Calculation tests
├── test_csv_import.py       # CSV parsing tests
└── test_security.py         # Security tests
```

### Test Strategy

- **Unit Tests**: Individual functions
- **Integration Tests**: Route handlers
- **End-to-End**: Critical user flows

---

## 📚 External Integrations

| Service | Purpose | API Type |
|---------|---------|----------|
| Yahoo Finance | Stock prices | REST API (yahooquery) |
| DeepSeek | AI ticker matching | REST API |
| Brave Search | Web search fallback | REST API |
| Unsplash | Blog images | REST API |
| SendGrid | Email delivery | REST API/SMTP |

---

## 🔄 Background Tasks

### Scheduler (APScheduler)

```python
# app/scheduler.py
scheduler = BackgroundScheduler()

# Daily performance refresh
scheduler.add_job(
    func=refresh_performance_cache,
    trigger="cron",
    hour=6,  # 6 AM daily
)

# Weekly report generation
scheduler.add_job(
    func=generate_weekly_report,
    trigger="cron",
    day_of_week="mon",
    hour=8,
)
```

---

## 📝 Key Design Decisions

1. **Flask over Django**: Lighter weight, more flexible for our use case
2. **SQLAlchemy ORM**: Database agnostic, migration support
3. **Blueprint pattern**: Modular, maintainable code organization
4. **Server-side rendering**: Simpler SEO, no SPA complexity
5. **PostgreSQL in production**: Better concurrency than SQLite
6. **Yahooquery over yfinance**: Better cloud compatibility
7. **AI-assisted workflows**: Reduce manual data entry

---

## 🆘 Troubleshooting Architecture

### Common Issues

**Database locked (SQLite)**
- Cause: Concurrent writes
- Solution: Use PostgreSQL in production

**High memory usage**
- Cause: Caching too much data
- Solution: Reduce cache TTL, use Redis

**Slow page loads**
- Cause: Synchronous external API calls
- Solution: Implement caching, async where possible

---

<p align="center">
  <strong>Questions about the architecture?</strong><br>
  Check <a href="../../AGENTS.md">AI Orientation</a> for technical details
</p>
