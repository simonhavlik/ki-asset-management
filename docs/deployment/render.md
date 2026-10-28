# Deploy to Render (+ external PostgreSQL)

Deploy the Flask app to **Render** and point it at **any PostgreSQL 17+**
database — self-hosted (see [Server Setup](server-setup.md)) or managed.

> **The club's real production setup is documented in
> [Production Infrastructure](production.md).** This page is the generic recipe.

---

## Architecture

```
 Browser ──HTTPS──▶ Render web service ──▶ PostgreSQL (external)
                        (Flask + gunicorn)
```

Render only runs the **app**. The database lives elsewhere and is reached over
the network using `DATABASE_URL`.

---

## Prerequisites

- A PostgreSQL database reachable from the public internet, on **version 17 or
  newer** (a dump taken from 17 cannot be restored into 15/16).
- The connection string, in the form
  `postgresql://USER:PASSWORD@HOST:5432/DB?sslmode=require`.
- The database server must allow Render's connections. Render's **outbound IPs
  are dynamic** on the free plan, so you either allow `0.0.0.0/0` (with TLS +
  SCRAM enforced) or buy Render's static outbound IPs.

---

## Step 1 — Create the web service

1. [render.com](https://render.com) → **New +** → **Web Service**.
2. Connect the GitHub repo `simonhavlik/ki-asset-management`.
3. Configure:

| Setting | Value |
|---|---|
| Name | `ki-asset-management` |
| Region | Frankfurt (EU Central) |
| Branch | `main` |
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `python render_start.py` |
| Plan | Free (sleeps after ~15 min idle) |

`render_start.py` creates missing tables, then boots gunicorn — so a fresh
deploy initialises itself.

---

## Step 2 — Environment variables

Render dashboard → **Environment**. Secrets stay here; they are never committed.

| Variable | Value |
|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | your PostgreSQL connection string (`?sslmode=require`) |
| `USE_LOCAL_SQLITE` | `False` |
| `FLASK_ENV` | `production` |
| `ADMIN_EMAIL` | your admin address |
| `SENDGRID_API_KEY` | see below |
| `NEON_OPTIMIZE` | `true` (legacy name; enables the in-memory cache) |
| `CACHE_TYPE` | `SimpleCache` |

See the full list in [Environment Variables](../reference/environment-variables.md).

> **Email is required** for registration/password reset. Render's free tier
> **blocks SMTP**, so use the SendGrid HTTP API (`SENDGRID_API_KEY`), not
> `MAIL_SERVER`/`MAIL_PASSWORD`.

---

## Step 3 — First deploy

Click **Create Web Service** and wait for the build. On first boot
`render_start.py` creates the schema. If you are migrating from an existing
database, restore a dump **before** the app starts writing (see
[Backup & Restore](../operations/backup-restore.md)).

---

## Cold starts

Render's free tier sleeps after ~15 minutes of inactivity; the next request takes
30–60 s to wake. Point a free uptime monitor (e.g. UptimeRobot) at `/health` if
you need it warm.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| App boots but pages 500 | `DATABASE_URL` unreachable, wrong password, or DB not allowing the connection |
| `ModuleNotFoundError: psycopg` | connection string must be `postgresql://` (psycopg2), see `requirements.txt` |
| Can't restore dump | destination server is older than the dump's Postgres version |
| Emails not sending | SMTP blocked on Render — configure SendGrid |

More: [Troubleshooting](../operations/troubleshooting.md).
