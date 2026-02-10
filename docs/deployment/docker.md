# Docker Deployment

Deploy KI Asset Management using Docker for consistent environments across all platforms.

> **⏱️ Time Required:** 15-20 minutes  
> **🎯 Difficulty:** Intermediate  
> **✅ Benefit:** Environment consistency, portable across clouds

---

## Quick Start

```bash
# 1. Clone repository
git clone <repo-url>
cd analyst_website

# 2. Create environment file
cp .env.example .env
# Edit .env with your settings

# 3. Build and run with Docker Compose
docker-compose up -d --build

# 4. Initialize database
docker-compose exec web flask init-db
docker-compose exec web flask create-admin

# 5. Access the app
open http://localhost:5000
```

---

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- Git

---

## Production Deployment

### With PostgreSQL

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=postgresql://postgres:password@db:5432/analyst_db
      - SENDGRID_API_KEY=${SENDGRID_API_KEY}
      - MAIL_DEFAULT_SENDER=${MAIL_DEFAULT_SENDER}
    depends_on:
      - db
    restart: always

  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=analyst_db
    restart: always

volumes:
  postgres_data:
```

Run:

```bash
# Start services
docker-compose -f docker-compose.prod.yml up -d

# Initialize database
docker-compose -f docker-compose.prod.yml exec web flask init-db
docker-compose -f docker-compose.prod.yml exec web flask create-admin

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

---

## Docker Commands Reference

```bash
# Build image
docker-compose build

# Start containers
docker-compose up -d

# View logs
docker-compose logs -f

# Stop containers
docker-compose down

# Restart
docker-compose restart

# Access container shell
docker-compose exec web /bin/bash

# Update after code changes
docker-compose up -d --build
```

---

## Dockerfile

The project includes a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:create_app()"]
```

---

## Environment Variables

Create `.env` file:

```bash
FLASK_ENV=production
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://postgres:password@db:5432/analyst_db
SENDGRID_API_KEY=your-sendgrid-key
MAIL_DEFAULT_SENDER=admin@yourdomain.com
```

---

## Deploying to Cloud Providers

### AWS ECS / Azure Container Apps / Google Cloud Run

1. Build image locally:
```bash
docker build -t ki-asset-management .
```

2. Push to container registry:
```bash
# AWS ECR
docker tag ki-asset-management:latest YOUR_AWS_ACCOUNT.dkr.ecr.region.amazonaws.com/ki-asset-management
docker push YOUR_AWS_ACCOUNT.dkr.ecr.region.amazonaws.com/ki-asset-management

# Or use Docker Hub, GitHub Container Registry, etc.
```

3. Deploy via your cloud provider's container service

---

## Troubleshooting

**Container won't start:**
```bash
# Check logs
docker-compose logs web

# Verify environment variables
docker-compose exec web env
```

**Database connection failed:**
- Ensure PostgreSQL container is running: `docker-compose ps`
- Check `DATABASE_URL` uses service name `db` as hostname
- Verify PostgreSQL is ready before web starts

**Permission denied:**
```bash
# Fix permissions
docker-compose exec web chown -R root:root /app
```

---

## Next Steps

- [Server Setup](server-setup.md) - Self-hosted with Docker
- [Operations](../operations/README.md) - Monitoring and maintenance
