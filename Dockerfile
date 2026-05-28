FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    BARSUKAS_PERSONA=hosted \
    STORAGE_BACKEND=jsonl \
    JSONL_DATA_DIR=/app/data/release

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .

EXPOSE 5555

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"5555\")}/healthz', timeout=3).read()"

CMD ["sh", "-c", "python src/barsukas/unified_app.py --host 0.0.0.0 --port ${PORT:-5555} --persona hosted"]
