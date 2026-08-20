# syntax=docker/dockerfile:1.7
# JobPilot — production image.
#
# Base image ships Playwright + all Chromium runtime deps so the browser
# controller works out-of-the-box. Multi-stage keeps the final image lean.

ARG PYTHON_VERSION=3.12
ARG PLAYWRIGHT_VERSION=v1.48.0

FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION}-jammy AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JOBPILOT_HOME=/app \
    API_HOST=0.0.0.0 \
    API_PORT=8000

WORKDIR /app

# Install Python deps first for better layer caching.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip \
 && pip install -e ".[dev]" \
 && pip install pypdf

# Copy application code.
COPY . .

# Runtime data dirs.
RUN mkdir -p /app/data /app/logs \
 && addgroup --system --gid 1001 jobpilot \
 && adduser  --system --uid 1001 --gid 1001 jobpilot \
 && chown -R jobpilot:jobpilot /app

USER jobpilot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)" \
    || exit 1

CMD ["python", "main.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
