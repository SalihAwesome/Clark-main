# ============================================================================
#  Clark Backend — FastAPI + Playwright + Chromium
#  Uses the official Playwright Python image (includes Chromium + deps).
# ============================================================================
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app

# Install Python dependencies (layer caching)
COPY requirements.txt .
RUN pip install --upgrade --no-cache-dir pip \
    && pip install --no-cache-dir -r requirements.txt

# Ensure Playwright Chromium is installed — the base image ships one for its
# own version, but when pip installs a different (pinned) version this step
# downloads the matching browser and system deps.
RUN python -m playwright install chromium

# Copy application code
COPY . .

# Runtime config — headless in Docker, no persistent Chrome profile
ENV BROWSER_HEADLESS=true
ENV BROWSER_PERSISTENT=false
ENV BROWSER_CDP_AUTODETECT=false
ENV BROWSER_DOCKER=true
ENV PYTHONUNBUFFERED=1

EXPOSE 8008

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008"]
