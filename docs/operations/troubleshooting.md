# Troubleshooting Guide

Common issues and their solutions for KI Asset Management.

---

## 🚨 Quick Fixes

### Application Won't Start

```bash
# Check virtual environment is activated
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows

# Verify dependencies installed
pip install -r requirements.txt

# Check environment variables
cat .env

# Reset database (WARNING: loses data)
rm instance/analyst.db  # Linux/Mac
flask init-db
flask create-admin
```

### Database Errors

**"Unable to open database file"**
```bash
mkdir -p instance
chmod 755 instance
```

**"Database is locked"** (SQLite)
```bash
# Close all terminals
# Kill Python processes
pkill -f flask
# Try again
```

**"Database connection failed"** (PostgreSQL)
- Check `DATABASE_URL` is correct
- Verify database is running
- Ensure `USE_LOCAL_SQLITE=False`

### Email Issues

**Emails not sending:**
- Verify `SENDGRID_API_KEY` or SMTP settings
- Check sender email is verified (SendGrid)
- Look for errors in application logs
- Check spam folders

**"CSRF token missing":**
```bash
# Generate secret key
python -c "import secrets; print(secrets.token_hex(32))"
# Add to .env
```

---

## 🔧 Common Issues

### Installation Issues

**"pip: command not found"**
```bash
# Debian/Ubuntu
sudo apt install python3-pip

# macOS
brew install python

# Windows
# Reinstall Python and check "Add to PATH"
```

**"No module named 'flask'"**
```bash
# Virtual environment not activated
source venv/bin/activate
```

**Permission denied when installing**
```bash
# Never use sudo pip
# Use virtual environment instead
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Runtime Issues

**"Port 5000 already in use"**
```bash
# Use different port
flask run --port=5001

# Or kill process using port 5000
lsof -ti:5000 | xargs kill -9  # Linux/Mac
```

**Static files not loading**
```bash
# Check file permissions
chmod -R 755 app/static

# Verify paths in templates
# Should use: url_for('static', filename='...')
```

**Slow page loads**
- Check internet connection (Yahoo Finance API)
- Verify caching is enabled
- Check database query performance

### CSV Upload Issues

**"CSV format invalid"**
- Ensure required columns: Date, Company, Sector, Analysts, Status
- Check CSV uses commas, not semicolons
- Verify UTF-8 encoding
- Remove special characters from company names

**"Companies not created"**
- Check company names are not empty
- Verify analyst names format
- Look for errors in upload summary

### Performance Calculation Issues

**"No tickers found"**
- Go to **Admin → Company Ticker Mappings**
- Add ticker symbols manually
- Or use "Auto-fill with DeepSeek"

**"Yahoo Finance API error"**
- Check internet connection
- Verify ticker symbols are valid
- Yahoo Finance may be temporarily down
- Try again later

**"Calculation timeout"**
- Large datasets may take time
- Check for invalid tickers
- Verify API rate limits not exceeded

---

## 🌐 Deployment Issues

### Render-Specific

**"Application failed to start"**
- Check logs in Render dashboard
- Verify all environment variables set
- Ensure `SECRET_KEY` is configured
- Check `DATABASE_URL` is correct

**"Build failed"**
- Verify `requirements.txt` in repo
- Check Python version compatibility
- Review build logs for errors

**Service sleeping (cold starts)**
- Render free tier sleeps after 15 min
- Set up UptimeRobot to ping every 5 min
- Or upgrade to paid tier

### Koyeb-Specific

**"Service unhealthy"**
- Check `PORT=8000` is set
- Verify start command: `gunicorn "app:create_app()"`
- Review application logs

**Database connection issues**
- Neon.tech database may be suspended
- Check connection string format
- Verify network connectivity

### Docker-Specific

**"Container won't start"**
```bash
# Check logs
docker-compose logs web

# Rebuild
docker-compose down
docker-compose up -d --build
```

**"Permission denied"**
```bash
docker-compose exec web chown -R root:root /app
```

---

## 🔍 Debugging

### Enable Debug Logging

```python
# Add to app/__init__.py temporarily
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Routes

```bash
flask routes
```

### Inspect Database

```bash
# Open SQLite CLI
sqlite3 instance/analyst.db

# List tables
.tables

# Query data
SELECT * FROM users;

# Exit
.quit
```

### View Environment

```bash
# Check Flask config
flask shell
>>> from flask import current_app
>>> current_app.config

# Check environment variables
env | grep FLASK
```

---

## 📊 Performance Issues

### High Memory Usage

**Causes:**
- Caching too much data
- Large result sets
- Memory leaks

**Solutions:**
- Reduce cache TTL
- Implement pagination
- Restart application

### Slow Database Queries

**Solutions:**
- Add database indexes
- Optimize queries
- Use query caching
- Consider PostgreSQL over SQLite for large datasets

### API Rate Limits

**Yahoo Finance:**
- May hit rate limits with many requests
- Implement caching
- Add delays between requests

**DeepSeek/Brave:**
- Check API usage limits
- Implement request queuing

---

## 🆘 Getting Help

### Before Asking

1. Check this troubleshooting guide
2. Review application logs
3. Check [AI Orientation](../AI-ORIENTATION.md)
4. Search existing issues

### Information to Provide

When reporting issues:
- Error message (full traceback)
- Steps to reproduce
- Environment details (OS, Python version)
- Recent changes made
- Logs relevant to the issue

---

## 📝 Common Error Messages

| Error | Solution |
|-------|----------|
| `ImportError: No module named 'X'` | Run `pip install -r requirements.txt` |
| `KeyError: 'SECRET_KEY'` | Set SECRET_KEY in .env |
| `OperationalError: no such table` | Run `flask init-db` |
| `PermissionError: [Errno 13]` | Check file permissions |
| `Connection refused` | Check if service is running |

---

<p align="center">
  <strong>Most issues are solved by:</strong><br>
  1. Activating virtual environment<br>
  2. Installing dependencies<br>
  3. Setting environment variables<br>
  4. Initializing database
</p>
