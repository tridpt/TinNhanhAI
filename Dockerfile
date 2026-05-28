FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TINNHANH_PROD=1 \
    DEBUG=0 \
    HOST=0.0.0.0 \
    PORT=5055

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Cache and Telegram state are written at runtime; mount a volume to persist.
RUN mkdir -p /app/.cache /app/state

EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5055/api/health', timeout=5)" || exit 1

CMD ["python", "app.py"]
