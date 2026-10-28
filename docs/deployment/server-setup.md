# Self-Hosted Server Setup

Complete guide for deploying KI Asset Management on your own server (DigitalOcean, AWS EC2, Linode, Hetzner, etc.).

> **⏱️ Time Required:** 45-60 minutes  
> **🎯 Difficulty:** Advanced  
> **✅ Benefit:** Full control, best performance, compliance

---

## Requirements

- **OS:** Ubuntu 22.04+ or Debian 11+
- **RAM:** 1GB minimum (2GB recommended)
- **Storage:** 20GB minimum
- **Access:** SSH root or sudo access
- **Domain:** Optional but recommended

---

## Quick Setup Script

For experienced users, here's a condensed version:

```bash
# Update system
apt update && apt upgrade -y

# Install dependencies
apt install -y python3 python3-pip python3-venv git nginx postgresql postgresql-contrib supervisor

# Setup PostgreSQL
sudo -u postgres psql -c "CREATE DATABASE analyst_db;"
sudo -u postgres psql -c "CREATE USER analyst_user WITH PASSWORD 'secure-password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE analyst_db TO analyst_user;"

# Create app user
useradd -m -s /bin/bash analyst

# Setup application (as analyst user)
su - analyst
git clone <repo-url>
cd analyst_website
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cat > .env << 'EOF'
FLASK_ENV=production
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
USE_LOCAL_SQLITE=False
DATABASE_URL=postgresql://analyst_user:secure-password@localhost:5432/analyst_db
EOF

# Initialize database
flask init-db
flask create-admin
```

---

## Step-by-Step Guide

### Step 1: Connect to Server

```bash
ssh root@your-server-ip
```

### Step 2: Update System

```bash
apt update && apt upgrade -y
```

### Step 3: Install Dependencies

```bash
apt install -y python3 python3-pip python3-venv git nginx postgresql postgresql-contrib supervisor
```

### Step 4: Configure PostgreSQL

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL shell:
CREATE DATABASE analyst_db;
CREATE USER analyst_user WITH ENCRYPTED PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE analyst_db TO analyst_user;
\q
```

### Step 5: Create Application User

```bash
useradd -m -s /bin/bash analyst
usermod -aG sudo analyst
su - analyst
```

### Step 6: Clone and Setup Application

```bash
git clone <repository-url>
cd analyst_website

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Create environment file
cat > .env << 'EOF'
FLASK_ENV=production
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
USE_LOCAL_SQLITE=False
DATABASE_URL=postgresql://analyst_user:your-secure-password@localhost:5432/analyst_db
SENDGRID_API_KEY=your-sendgrid-api-key
MAIL_DEFAULT_SENDER=admin@yourdomain.com
ADMIN_EMAIL=admin@yourdomain.com
EOF
```

### Step 7: Initialize Database

```bash
flask init-db
flask create-admin
```

### Step 8: Create Systemd Service

Exit to root user (`exit`), then:

```bash
tee /etc/systemd/system/ki-asset-management.service << 'EOF'
[Unit]
Description=KI Asset Management Flask Application
After=network.target

[Service]
User=analyst
Group=analyst
WorkingDirectory=/home/analyst/analyst_website
Environment="PATH=/home/analyst/analyst_website/venv/bin"
EnvironmentFile=/home/analyst/analyst_website/.env
ExecStart=/home/analyst/analyst_website/venv/bin/gunicorn --workers 4 --bind 127.0.0.1:8000 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ki-asset-management
systemctl start ki-asset-management
```

### Step 9: Configure Nginx

```bash
tee /etc/nginx/sites-available/ki-asset-management << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /home/analyst/analyst_website/app/static;
        expires 30d;
    }
}
EOF

ln -s /etc/nginx/sites-available/ki-asset-management /etc/nginx/sites-enabled
rm /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
```

### Step 10: Set Up SSL (Let's Encrypt)

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

### Step 11: Configure Firewall

```bash
ufw allow 'Nginx Full'
ufw allow OpenSSH
ufw enable
```

---

## Maintenance Commands

```bash
# View application logs
journalctl -u ki-asset-management -f

# Restart application
systemctl restart ki-asset-management

# Update application
cd /home/analyst/analyst_website
git pull
source venv/bin/activate
pip install -r requirements.txt
flask init-db  # If there are database migrations
systemctl restart ki-asset-management

# Backup database
sudo -u postgres pg_dump analyst_db > backup_$(date +%Y%m%d).sql

# Restore database
sudo -u postgres psql analyst_db < backup_file.sql
```

---

## Troubleshooting

**Application won't start:**
```bash
journalctl -u ki-asset-management -n 50
```

**Nginx 502 error:**
- Ensure Gunicorn is running on port 8000
- Check: `systemctl status ki-asset-management`

**Permission denied:**
```bash
chown -R analyst:analyst /home/analyst/analyst_website
```

**Database connection failed:**
```bash
systemctl status postgresql
sudo -u postgres psql -c "\l"  # List databases
```

---

## Next Steps

- [Security Hardening](../operations/security.md)
- [Monitoring Setup](../operations/monitoring.md)
- [Backup Automation](../operations/backup-restore.md)
