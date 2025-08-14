# Multi-stage build for Job Bot Python services
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd --create-home --shell /bin/bash app

# Set work directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Install additional dependencies for the job bot
RUN pip install \
    uvicorn[standard] \
    fastapi \
    rq \
    psycopg2-binary \
    redis \
    sqlalchemy \
    tenacity \
    pydantic \
    pydantic-settings \
    httpx \
    playwright \
    python-docx \
    python-multipart \
    jinja2 \
    google-auth \
    google-auth-oauthlib \
    google-api-python-client

# Install Playwright browsers (for web scraping)
RUN playwright install chromium && \
    playwright install-deps chromium

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p artifacts config logs && \
    chown -R app:app /app

# Switch to app user
USER app

# Health check script
COPY --chown=app:app <<EOF /app/healthcheck.py
#!/usr/bin/env python3
import sys
import requests
import os

def check_api_health():
    try:
        response = requests.get('http://localhost:8000/health', timeout=5)
        return response.status_code == 200
    except:
        return False

def check_worker_health():
    # For worker, just check if it can import main modules
    try:
        from apps.worker.worker import main
        return True
    except:
        return False

if __name__ == '__main__':
    service_type = os.environ.get('SERVICE_TYPE', 'api')
    
    if service_type == 'api':
        if check_api_health():
            sys.exit(0)
        else:
            sys.exit(1)
    elif service_type == 'worker':
        if check_worker_health():
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        sys.exit(1)
EOF

RUN chmod +x /app/healthcheck.py

# Expose port for API service
EXPOSE 8000

# Default command (can be overridden in docker-compose.yml)
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
