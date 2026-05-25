FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    WEB_HOST=0.0.0.0 \
    WORKSPACE_DIR=/var/data/workspace \
    ENVIRONMENT=production

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

RUN mkdir -p /var/data/workspace

CMD ["python", "-m", "agent", "web"]
