# Imagen del bot y de la web (la misma para ambos servicios).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencias primero (capa cacheada mientras no cambie el lock)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY config ./config
RUN uv sync --frozen --no-dev

# Usuario sin privilegios; data/ se monta como volumen
RUN useradd --create-home --uid 1000 btc \
    && mkdir -p /app/data /app/reports \
    && chown -R btc:btc /app/data /app/reports
USER btc

CMD ["btcbot", "paper", "run"]
