FROM ghcr.io/astral-sh/uv:0.12.2-python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/api/src \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api apps/api

RUN uv sync --frozen --no-dev --extra embeddings --package companion-ai-api \
    && uv run --no-sync --package companion-ai-api python -c \
      "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')" \
    && useradd --create-home --uid 10001 companion \
    && chown -R companion:companion /app/.cache

USER companion

EXPOSE 8000
STOPSIGNAL SIGTERM

CMD ["sh", "-c", "exec uv run --no-sync --package companion-ai-api uvicorn companion.api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
