FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TASKS_DB_PATH=/data/tasks.db \
    COOKIE_SECURE=false

WORKDIR /app

COPY requirements-runtime.txt .
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements-runtime.txt \
    && mkdir -p /data \
    && chown 10001:10001 /data

COPY app ./app

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
