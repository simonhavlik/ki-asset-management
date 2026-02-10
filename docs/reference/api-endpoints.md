# API Endpoints Reference

Complete reference for available API endpoints in KI Asset Management.

---

## 🔐 Authentication

All authenticated endpoints require a valid session cookie (set via login).

### Public Endpoints

No authentication required:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Landing page |
| GET | `/about` | About page |
| GET | `/terms` | Terms of service |
| GET | `/blog` | Blog listing |
| GET | `/blog/<slug>` | Individual blog post |

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/auth/login` | User login |
| GET/POST | `/auth/register` | User registration |
| GET | `/auth/logout` | Logout |
| GET/POST | `/auth/reset-password` | Password reset request |
| GET/POST | `/auth/reset-password/<token>` | Password reset confirm |

---

## 👤 User Endpoints

Require authentication (`@login_required`):

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dashboard` | Analyst dashboard |
| GET | `/profile` | User profile |
| POST | `/profile` | Update profile |

---

## 👑 Admin Endpoints

Require admin role (`@admin_required`):

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/` | Admin dashboard |

### User Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/users` | List users |
| POST | `/admin/users/create` | Create user |
| POST | `/admin/users/<id>/toggle` | Toggle active status |
| POST | `/admin/users/<id>/promote` | Promote/demote admin |
| POST | `/admin/users/<id>/reset-password` | Reset password |

### CSV Upload

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/csv-upload` | Upload page |
| POST | `/admin/csv-upload` | Process CSV |

### Company Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/companies` | Company ticker mappings |
| POST | `/admin/companies/<id>/ticker` | Update ticker |
| POST | `/admin/companies/auto-fill` | Auto-fill with AI |

### Performance

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/performance` | Performance dashboard |
| POST | `/admin/performance/calculate` | Recalculate performance |
| GET | `/admin/performance/analyst/<id>` | Analyst detail |

### Board Voting

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/board` | Board voting page |
| POST | `/admin/board/vote` | Submit vote |
| POST | `/admin/board/purchase-date` | Update purchase date |
| POST | `/admin/board/calculate-portfolio` | Calculate portfolio performance |

### Blog Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/blog-posts` | Manage all posts |
| POST | `/admin/blog-posts/<id>/toggle-featured` | Toggle featured |
| POST | `/admin/blog-posts/<id>/delete` | Delete post |

### Activity Logs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/logs` | Activity logs |
| GET | `/admin/logs/export` | Export logs (CSV) |

---

## 📝 Blog Endpoints

### Public

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/blog` | Blog home |
| GET | `/blog/<slug>` | Single post |
| GET | `/blog/category/<category>` | Posts by category |
| GET | `/blog/tag/<tag>` | Posts by tag |

### Authenticated

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/blog/new` | Create post form |
| POST | `/blog/new` | Create post |
| GET | `/blog/edit/<id>` | Edit post form |
| POST | `/blog/edit/<id>` | Update post |
| GET | `/blog/my-posts` | My posts |

### AI Features

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/blog/api/generate-seo` | Generate SEO metadata |
| POST | `/blog/api/generate-article` | Generate article from document |

---

## 🔧 Utility Endpoints

### Health Check

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health status (public) |

**Response:**
```json
{"status": "healthy"}
```

### CSV Export

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/performance/export` | Export performance (CSV) |
| GET | `/admin/board/export` | Export portfolio (CSV) |

---

## 📊 Data Formats

### CSV Upload Format

```csv
Date,Company,Sector,Analysts,Opponents,Comment,Status,Files
2024-01-15,Apple Inc,Technology,John Doe,Jane Smith,Bullish thesis,On Watchlist,analysis.pdf
```

### API Response Format

Standard JSON responses:

```json
{
  "success": true,
  "data": {...},
  "message": "Operation completed"
}
```

Error responses:

```json
{
  "success": false,
  "error": "Error message",
  "code": 400
}
```

---

## 🛡️ Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| Login | 5 attempts | 15 minutes |
| Password reset | 3 attempts | 1 hour |
| Blog SEO generation | 20 requests | 1 hour |
| Document upload | 5 uploads | 1 hour |

---

## 🔍 Query Parameters

### Performance Dashboard

```
/admin/performance?filter=approved&annualized=true
```

| Parameter | Values | Description |
|-----------|--------|-------------|
| `filter` | `approved`, `neutral`, `all` | Filter by decision |
| `annualized` | `true`, `false` | Show annualized returns |
| `period` | `1y`, `ytd`, `all` | Time period |

### Blog

```
/blog?page=2&category=analysis
```

| Parameter | Description |
|-----------|-------------|
| `page` | Page number |
| `category` | Filter by category |
| `tag` | Filter by tag |

---

## 📚 CLI Commands

Flask CLI commands available:

```bash
flask init-db              # Initialize database
flask create-admin         # Create admin user
flask db-upgrade           # Run migrations
flask shell                # Open Python shell with app context
flask routes               # List all routes
```

---

<p align="center">
  <strong>API endpoints follow RESTful conventions</strong>
</p>
