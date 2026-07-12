# ============================================================================
#  Clark Backend — root Dockerfile for Render (builds from backend/)
#  Render Blueprint looks for Dockerfile at the repo root. This one
#  copies the backend/ subdirectory and runs the same steps as
#  backend/Dockerfile.
# ============================================================================
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app

# Install Python deps (layer caching)
COPY backend/requirements.txt .
RUN pip install --upgrade --no-cache-dir pip \
    && pip install --no-cache-dir -r requirements.txt

# Ensure Playwright Chromium is installed
RUN python -m playwright install chromium

# Copy application code
COPY backend/ .

# Runtime config — headless, Docker-optimized Chromium
ENV BROWSER_HEADLESS=true
ENV BROWSER_PERSISTENT=false
ENV BROWSER_CDP_AUTODETECT=false
ENV BROWSER_DOCKER=true
ENV PYTHONUNBUFFERED=1

EXPOSE 8008

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008"]
