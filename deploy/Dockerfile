FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://gitee.com/xinghetech/yike-ai2026" \
      org.opencontainers.image.revision="$VCS_REF"

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN python -m pip install --no-cache-dir uv==0.8.15
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin yike

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY pilot ./pilot
COPY migrations ./migrations
RUN mkdir -p /tmp/uv-cache && chown -R yike:yike /app /tmp/uv-cache

ENV YIKE_PILOT_HOST=0.0.0.0 \
    YIKE_PILOT_PORT=8787 \
    HOME=/home/yike \
    UV_CACHE_DIR=/tmp/uv-cache
USER yike
EXPOSE 8787

CMD ["/app/.venv/bin/python", "-c", "from pilot.cli import web; web()"]
