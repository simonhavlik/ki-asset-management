# Production Infrastructure

> **This page documents what the club actually runs in production.**
> For "how do I deploy this app anywhere", see the other guides in this folder.
> Last reviewed: **2026-09-28**.

The repository is public, but **only the technology is documented here — never the
keys**. Connection strings, passwords and API keys live exclusively in Render's
environment variables (and in the club's secret store), not in this repo.

---

## Topology

```
 Browser ──HTTPS──▶ Cloudflare ──▶ Render web service (Frankfurt)
                                        │  Flask 2.3 + gunicorn
                                        │  DATABASE_URL  (secret, set in Render)
                                        ▼
                                   PostgreSQL 17
                                   self-hosted VPS ("charizard", Debian 12)
```

Public site: **https://ki.havliksimon.eu**

### Components

| Layer | What | Where | Notes |
|---|---|---|---|
| Web app | Flask + gunicorn | **Render free** web service, Frankfurt | Auto-deploys on push to `main`; sleeps after ~15 min idle |
| Database | **PostgreSQL 17** | Club VPS **charizard** (Debian 12, Ionos) | TLS + `scram-sha-256`, port `5432`, memory-capped |
| Server DNS | NextDNS over **DNS-over-TLS** | charizard `systemd-resolved` | Native DoT, no `nextdns` daemon |
| Tailnet | **Headscale** (self-hosted Tailscale control) | charizard | MagicDNS `*.home.arpa`, private admin access |
| Object/analyses | served from the app container | Render | No local state — all state is in PostgreSQL |

---

## Render configuration

| Setting | Value |
|---|---|
| Service type | Web Service (Python) |
| Plan / region | Free / Frankfurt |
| Repo / branch | `github.com/havliksimon/ki-asset-management` / `main` |
| Auto-deploy | Yes (every push to `main`) |
| Build command | `pip install -r requirements.txt` |
| Start command | `python render_start.py` |

`render_start.py` creates missing tables and then boots gunicorn, so a fresh
deploy is self-initialising.

### Environment variables (set in the Render dashboard — **not** in the repo)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql://<user>:<password>@<vps-host>:5432/<db>?sslmode=require` — **secret** |
| `USE_LOCAL_SQLITE` | `False` (must be False to use PostgreSQL) |
| `NEON_OPTIMIZE` | `true` — despite the legacy name, this just enables the aggressive in-memory cache |
| `SECRET_KEY` | Flask session signing key — **secret** |
| `SENDGRID_API_KEY`, mail vars | Outbound email (Render free blocks SMTP) — see [Outbound email](#outbound-email-outbox-relay-on-the-database-host) |
| `FLASK_ENV`, `ADMIN_EMAIL`, `ALLOWED_EMAIL_DOMAIN` | Runtime / access control |

Full list: [Environment Variables](../reference/environment-variables.md).

---

## Database host (charizard)

PostgreSQL 17 is installed from the **PGDG** repository, because Debian 12 ships
PostgreSQL 15 — and a database dumped from 17 **cannot** be restored into 15.

Low-memory profile (the VPS is small and shares the box with other club services):

| Setting | Value |
|---|---|
| `shared_buffers` | `32MB` |
| `max_connections` | `20` |
| `work_mem` | `1MB` |
| `maintenance_work_mem` | `32MB` |
| `synchronous_commit` | `off` (faster; a hard crash can lose the last fraction of a second) |

**Hard memory cap** — a systemd cgroup keeps Postgres from ever OOM-killing the
co-hosted services (e.g. the Anki API):

```ini
# /etc/systemd/system/postgresql@17-main.service.d/limits.conf
[Service]
MemoryHigh=112M
MemoryMax=160M
```

**Access** (`pg_hba.conf`): `scram-sha-256` over SSL for the tailnet
(`100.64.0.0/10`) and for the app's egress (`0.0.0.0/0` — required because
Render's outbound IPs are dynamic). TCP `5432` is opened in the Ionos firewall.

> ⚠️ Because Render egress is dynamic, `5432` is open to the internet and
> protected by TLS + SCRAM + `fail2ban` only. To tighten: give Render static
> outbound IPs and allow just those, or move the app onto the same tailnet.

---

## Server DNS (charizard)

The `nextdns` CLI daemon was removed to save RAM. Filtering is preserved by
pointing `systemd-resolved` straight at NextDNS over DoT:

```ini
# /etc/systemd/resolved.conf
[Resolve]
DNS=<nextdns-anycast-ip>#<profile-id>.dns.nextdns.io
DNSOverTLS=yes
DNSSEC=allow-downgrade
Domains=~.
Cache=yes
```

(Exact anycast IP and profile id are environment-specific and kept off this repo.)

---

## Outbound email (Gmail API over HTTPS)

**Render cannot send email over SMTP.** The production log is unambiguous:

```
sendgrid failed: HTTP Error 401: Unauthorized     <- daily quota is 0, plan is dead
smtp failed: [Errno 101] Network is unreachable   <- Render blocks the SMTP ports
```

SendGrid cannot be revived on the free plan (`GET /v3/user/credits` reports
`total: 0, remain: 0, is_hard_limit: true`). So mail goes out through the
**Gmail API**, which is plain HTTPS to `googleapis.com` and therefore allowed.

Because `klubinvestoru.com` is a Google Workspace domain (MX = `aspmx.l.google.com`),
the OAuth client is **Internal**:

- no Google verification and no "unverified app" warning
- **the refresh token does not expire** (an External client left in "Testing"
  has its refresh tokens revoked after 7 days, which would break mail weekly)

### One-time setup

Create the credentials with `scripts/gmail_oauth_setup.py` — it walks through
the console, opens the consent screen, and prints the values to paste into
Render. Then set:

| Variable | Value |
| --- | --- |
| `GMAIL_CLIENT_ID` | from the OAuth client (Desktop app) |
| `GMAIL_CLIENT_SECRET` | from the OAuth client |
| `GMAIL_REFRESH_TOKEN` | printed by the setup script |
| `GMAIL_SENDER` | `simon.havlik@klubinvestoru.com` |
| `MAIL_PROVIDER` | `gmail_api` (optional — it is auto-detected first) |

Provider order is `gmail_api → brevo → resend → sendgrid → smtp`, so adding any
other key takes effect without further changes.

### Nothing is ever silently dropped

If every provider fails, `send_email()` parks the message in the `email_outbox`
table instead of logging and dropping it (which is why reset links used to
vanish without trace). The in-process scheduler retries the queue every 15
minutes, and it can be drained on demand:

```bash
flask mail-status                  # provider config, order, outbox depth
flask send-outbox --limit 50       # retry now
flask send-test-email you@example.com
```

Rows are retried at most 5 times, then marked `failed` so a permanently broken
provider cannot grow the table. This retry lives in the web process — **no
infrastructure on the database host is involved.**

## Backups — **important**

Self-hosted PostgreSQL has **no managed backups**. The scheduled `pg_dump`
described in [Backup & Restore](../operations/backup-restore.md) is the only
safety net and it must exist. Verify it runs.

---

## Known caveats

- Render's free web service has an **ephemeral filesystem** — never store state on
  disk; everything lives in PostgreSQL.
- The in-memory `SimpleCache` (`CACHE_TYPE=SimpleCache`) is per-worker and is wiped
  on every deploy, so the first requests after a deploy hit the database cold.
- Render free **sleeps after inactivity**; the first request after a sleep is slow.
- `synchronous_commit=off` trades a tiny durability window for write speed.

---

## History

- Pre-2026-09: PostgreSQL was hosted on **Neon** (serverless). The free-tier quota
  was exhausted, production went read-only/down, and the database was migrated to
  the club's own VPS. See [changelog](../reference/changelog.md).
