# Monitoring Guide

Monitoring and observability for KI Asset Management.

---

## 📊 Health Checks

### Application Health

The app provides a health check endpoint:

```bash
curl https://your-app.com/health
```

**Expected Response:**
```json
{"status": "healthy"}
```

Use this for:
- Uptime monitoring (UptimeRobot)
- Load balancer health checks
- Container orchestration (Kubernetes)

### Database Health

```bash
# PostgreSQL (neon.tech)
psql "$DATABASE_URL" -c "SELECT 1;"

# Should return: 1
```

---

## 📋 Log Monitoring

### Application Logs

**Render:**
- Dashboard → Service → Logs
- Shows stdout/stderr from app

**Koyeb:**
- Dashboard → Service → Logs
- Real-time streaming

**Docker:**
```bash
docker-compose logs -f web
```

**Server (systemd):**
```bash
journalctl -u ki-asset-management -f
```

### What to Watch

**Normal:**
- Startup messages
- Request logs (200 OK)
- Scheduled job completion

**Warning:**
- Slow queries (>500ms)
- Rate limit warnings
- Cache misses

**Error:**
- Database connection failures
- External API errors
- Exception tracebacks
- Authentication failures

### Log Levels

Configure via environment:

```bash
# Development
FLASK_ENV=development  # DEBUG level

# Production
FLASK_ENV=production   # INFO level
```

---

## 📈 Metrics

### Key Metrics

| Metric | Target | Alert If |
|--------|--------|----------|
| Uptime | >99.9% | <99% |
| Response Time | <500ms | >1s |
| Error Rate | <0.1% | >1% |
| Database Connections | <20 | >15 |

### Performance Monitoring

**Response Times:**
```bash
# Check response time
curl -o /dev/null -s -w '%{time_total}\n' https://your-app.com
```

**Database Performance:**
- Monitor query times in logs
- Watch for slow queries
- Check connection pool usage

---

## 🔔 Alerting

### Uptime Monitoring

**UptimeRobot (Free):**
1. Sign up at [uptimerobot.com](https://uptimerobot.com)
2. Add HTTP(s) monitor
3. URL: `https://your-app.com/health`
4. Interval: 5 minutes
5. Set alert contacts (email/SMS)

**Alert Conditions:**
- HTTP code != 200
- Response time > 5 seconds
- SSL certificate expiring

### Error Alerting

**Log-Based Alerts:**
- Set up log filtering
- Alert on ERROR level logs
- Monitor specific patterns:
  - "Database connection failed"
  - "Exception"
  - "Permission denied"

---

## 🔍 Debugging in Production

### Safe Debugging

```python
# Add to specific route for debugging
import logging
logger = logging.getLogger(__name__)

@app.route('/debug-route')
def debug_route():
    logger.info(f"Debug: user={current_user}, args={request.args}")
    # Your code here
```

### Log Analysis

```bash
# Search for errors
grep -i "error" /var/log/app.log

# Find slow queries
grep "Slow query" /var/log/app.log

# Count requests by IP
awk '{print $1}' /var/log/nginx/access.log | sort | uniq -c | sort -nr
```

---

## 📊 Dashboards

### Simple Status Page

Create a basic status page:

```python
@app.route('/status')
def status():
    return jsonify({
        'app': 'healthy',
        'database': check_db(),
        'version': '1.0.0',
        'timestamp': datetime.utcnow()
    })
```

### Third-Party Monitoring

**Options:**
- **New Relic** - Full observability
- **Datadog** - Cloud monitoring
- **Grafana + Prometheus** - Self-hosted

---

## 🔄 Regular Checks

### Daily

- [ ] Check uptime status
- [ ] Review error logs
- [ ] Verify backups completed

### Weekly

- [ ] Performance metrics review
- [ ] Disk space check
- [ ] Security log review

### Monthly

- [ ] Full system health check
- [ ] Capacity planning review
- [ ] Update monitoring thresholds

---

## 🆘 Incident Response

### High Error Rate

1. Check logs for pattern
2. Identify affected routes
3. Check external dependencies
4. Consider rollback if needed

### Slow Performance

1. Check database performance
2. Review recent changes
3. Check external API response times
4. Consider scaling up

### Database Issues

1. Check connection pool
2. Review slow query log
3. Check disk space
4. Contact database provider if needed

---

<p align="center">
  <strong>Monitor early, monitor often</strong>
</p>
