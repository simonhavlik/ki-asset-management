# Backup & Restore

Data protection and disaster recovery for KI Asset Management.

---

## 💾 Backup Strategy

### PostgreSQL (self-hosted) — this one is on you

Production runs on **self-hosted PostgreSQL**, which has **no managed backups**.
A scheduled `pg_dump` is the only safety net:

```bash
# /etc/cron.daily/kiam-pgdump  (run as the postgres user)
pg_dump -Fc --no-owner -d "$DATABASE_URL" -f /var/backups/kiam-$(date +%F).dump
find /var/backups -name 'kiam-*.dump' -mtime +14 -delete
```

Keep a copy **off the database host** (object storage or another machine) —
losing the host without an offsite dump means losing everything.

### Manual Backups

**SQLite (Local Development):**

```bash
# Backup
cp instance/analyst.db backups/analyst_$(date +%Y%m%d).db

# Or use SQLite CLI
sqlite3 instance/analyst.db ".backup backups/analyst_$(date +%Y%m%d).db"
```

**PostgreSQL:**

```bash
# Export database
pg_dump "$DATABASE_URL" > backup_$(date +%Y%m%d).sql

# With compression
pg_dump "$DATABASE_URL" | gzip > backup_$(date +%Y%m%d).sql.gz
```

---

## 🔄 Automated Backup Script

Create `scripts/backup.sh`:

```bash
#!/bin/bash
# Database backup script

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/path/to/backups"
RETENTION_DAYS=30

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
if [ -n "$DATABASE_URL" ]; then
    pg_dump "$DATABASE_URL" | gzip > "$BACKUP_DIR/backup_$DATE.sql.gz"
    echo "PostgreSQL backup completed: backup_$DATE.sql.gz"
fi

# Backup SQLite (fallback)
if [ -f "instance/analyst.db" ]; then
    cp instance/analyst.db "$BACKUP_DIR/analyst_$DATE.db"
    echo "SQLite backup completed: analyst_$DATE.db"
fi

# Delete old backups (keep last 30 days)
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "analyst_*.db" -mtime +$RETENTION_DAYS -delete

echo "Backup cleanup completed"
```

Make executable and schedule:

```bash
chmod +x scripts/backup.sh

# Add to crontab (daily at 2 AM)
0 2 * * * /path/to/analyst_website/scripts/backup.sh >> /var/log/backup.log 2>&1
```

---

## ♻️ Restore Procedures

### PostgreSQL Restore (self-hosted)

**From a dump:**
```bash
pg_restore -O --no-owner -d "$DATABASE_URL" /path/to/kiam-YYYY-MM-DD.dump
```

**Rebuild on a fresh host:** install PostgreSQL **17+** (older majors cannot load
a 17 dump) → create the role and database → `pg_restore` the dump → update
`DATABASE_URL` → redeploy.

**From Manual Backup:**

```bash
# Restore from SQL file
psql "$DATABASE_URL" < backup_20240115.sql

# Or with gzip
gunzip -c backup_20240115.sql.gz | psql "$DATABASE_URL"
```

### SQLite Restore

```bash
# Stop application
ctrl+c  # or kill flask process

# Restore from backup
cp backups/analyst_20240115.db instance/analyst.db

# Restart application
flask run
```

---

## 📋 Disaster Recovery

### Scenario 1: Database Corruption

1. **Stop application**
   ```bash
   systemctl stop ki-asset-management
   ```

2. **Restore from backup**
   ```bash
   # Find most recent good backup
   ls -lt backups/ | head -5
   
   # Restore
   cp backups/analyst_20240115.db instance/analyst.db
   ```

3. **Verify data integrity**
   ```bash
   flask shell
   >>> from app.models import User
   >>> User.query.count()
   ```

4. **Restart application**
   ```bash
   systemctl start ki-asset-management
   ```

### Scenario 2: Complete Server Failure

1. **Provision new server**
   - Follow [Server Setup Guide](../deployment/server-setup.md)

2. **Restore application code**
   ```bash
   git clone <repo-url>
   cd analyst_website
   ```

3. **Restore configuration**
   - Copy `.env` file from secure storage
   - Restore environment variables

4. **Restore database**
   - Use backup file
   - Run restore procedure above

5. **Verify functionality**
   - Check application loads
   - Test login
   - Verify data integrity

### Scenario 3: Accidental Data Deletion

1. **Identify what was deleted**
   - Check application logs
   - Review user activity

2. **Stop writes immediately**
   - Prevent further changes

3. **Restore to point-in-time**
   - Restore the most recent dump (self-hosted Postgres has no PITR unless you add WAL archiving)
   - Or restore manual backup

4. **Extract specific data**
   - May need to manually merge data
   - Or accept data loss

---

## ✅ Backup Verification

### Test Restore Monthly

```bash
# Create test restore
cp backup_latest.sql restore_test.sql

# Restore to test database
psql "postgresql://user:pass@localhost/test_db" < restore_test.sql

# Verify data
psql "$TEST_DATABASE_URL" -c "SELECT COUNT(*) FROM users;"

# Clean up
rm restore_test.sql
```

### Automated Verification

Add to backup script:

```bash
# After backup
if pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
    echo "Backup verified: $BACKUP_FILE"
else
    echo "ERROR: Backup verification failed!"
    exit 1
fi
```

---

## 🏪 Backup Storage

### Local Storage

```
backups/
├── daily/
│   ├── backup_20240115.sql.gz
│   └── backup_20240114.sql.gz
├── weekly/
│   └── backup_20240114_weekly.sql.gz
└── monthly/
    └── backup_20240101_monthly.sql.gz
```

### Cloud Storage (Recommended)

**AWS S3:**
```bash
# Upload to S3
aws s3 cp backup_$(date +%Y%m%d).sql.gz s3://your-backup-bucket/analyst/

# Sync entire backup directory
aws s3 sync backups/ s3://your-backup-bucket/analyst/backups/
```

**Google Cloud Storage:**
```bash
# Upload
gsutil cp backup_$(date +%Y%m%d).sql.gz gs://your-backup-bucket/analyst/

# Sync
gsutil -m rsync -r backups/ gs://your-backup-bucket/analyst/backups/
```

**Rsync to remote server:**
```bash
rsync -avz --delete backups/ user@backup-server:/path/to/backups/
```

---

## 📝 Backup Checklist

### Daily

- [ ] Verify automatic backups completed
- [ ] Check backup file sizes (shouldn't be zero)

### Weekly

- [ ] Review backup logs for errors
- [ ] Verify retention policy working

### Monthly

- [ ] Test restore procedure
- [ ] Verify data integrity after restore
- [ ] Review backup storage usage
- [ ] Update disaster recovery plan

---

## 🆘 Emergency Information

Keep this information documented and accessible to your team:

- **Database Provider:** Support contact for your database service
- **Hosting Provider:** Support contact for your hosting platform
- **Domain Registrar:** Contact for domain issues
- **DNS Provider:** Contact for DNS changes
- **Team Contacts:** Internal team contact list

---

<p align="center">
  <strong>Backups are insurance - test them before you need them</strong>
</p>
