FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY docker/certs/ /usr/local/share/ca-certificates/
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN update-ca-certificates \
    && PIP_CERT=/etc/ssl/certs/ca-certificates.crt python -m pip install --upgrade pip \
    && PIP_CERT=/etc/ssl/certs/ca-certificates.crt python -m pip install -r /tmp/backend-requirements.txt

RUN useradd --create-home --uid 10001 copilot \
    && mkdir -p /var/lib/copilot \
    && chown -R copilot:copilot /var/lib/copilot

COPY --chown=copilot:copilot backend /app/backend

USER copilot

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=6 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
