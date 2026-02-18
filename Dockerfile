# Analyst Performance Tracker Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (for psycopg2, sqlite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY .env.example .env.example
COPY .gitignore .
COPY README.md .
COPY Procfile .
COPY render_start.py .

# Create instance directory for SQLite
RUN mkdir -p instance

# Set environment variables
ENV FLASK_APP=app
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Expose port (Zeabur uses 8080)
EXPOSE 8080

# Run with render_start.py (handles DB init + gunicorn start)
CMD ["python", "render_start.py"]