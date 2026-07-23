FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TINNHANH_PROD=1 \
    DEBUG=0 \
    HOST=0.0.0.0 \
    PORT=8080 \
    DATA_DIR=/app/data \
    CACHE_DIR=/app/data/.cache \
    STATE_DIR=/app/data/state

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Cache, history DB, and Telegram state are all written under /app/data so a
# single mounted volume persists everything across machine replacements.
RUN mkdir -p /app/data/.cache /app/data/state

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=5)" || exit 1

CMD ["python", "app.py"]
