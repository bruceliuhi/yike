FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN python -m pip install --no-cache-dir uv==0.8.15

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY pilot ./pilot
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

ENV YIKE_PILOT_HOST=0.0.0.0 \
    YIKE_PILOT_PORT=8787
EXPOSE 8787

CMD ["uv", "run", "--frozen", "yike-pilot-web"]
