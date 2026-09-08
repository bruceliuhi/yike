FROM ghcr.io/astral-sh/uv:0.8.15-python3.12-bookworm-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY pilot ./pilot
COPY migrations ./migrations

ENV YIKE_PILOT_HOST=0.0.0.0 \
    YIKE_PILOT_PORT=8787
EXPOSE 8787

CMD ["uv", "run", "--frozen", "yike-pilot-web"]
