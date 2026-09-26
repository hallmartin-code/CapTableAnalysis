# Railway builds this image. Secrets (ANTHROPIC_API_KEY, APP_PASSWORD) are NOT baked in:
# they arrive as Railway variables at runtime.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY captable_app ./captable_app
COPY templates ./templates
COPY assets ./assets
COPY public ./public

RUN useradd --create-home --uid 10001 appuser && mkdir -p /tmp/captable-jobs && chown appuser /tmp/captable-jobs
USER appuser

EXPOSE 8000
ENV PORT=8000 JOBS_DIR=/tmp/captable-jobs
# One worker: jobs live in this process's memory.
CMD ["sh", "-c", "uvicorn captable_app.web:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]
