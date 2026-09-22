FROM python:3.13-slim

ARG APP_UID=1000
ARG APP_GID=1000

LABEL org.opencontainers.image.source="https://github.com/Z-Han-Z/apple-music-playlists"
LABEL org.opencontainers.image.description="Apple Music playlist MCP stdio server"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    XDG_CONFIG_HOME=/home/app/.config \
    XDG_CACHE_HOME=/home/app/.cache

RUN groupadd --gid "${APP_GID}" app \
    && useradd --create-home --uid "${APP_UID}" --gid "${APP_GID}" app \
    && mkdir -p /home/app/.config/am-playlist /home/app/.cache/am-playlist \
    && chown -R app:app /home/app/.config /home/app/.cache
WORKDIR /app

COPY --chown=app:app *.py LICENSE README.md ./

USER app
VOLUME ["/home/app/.config/am-playlist", "/home/app/.cache/am-playlist"]

ENTRYPOINT ["python", "/app/am_mcp_server.py"]
