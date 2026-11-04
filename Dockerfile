# materials-triage images.
#   web: builds the React app (web/dist).
#   api: the Python service, which also serves web/dist; the offline demo data (recorded
#        cassettes, snapshots, bundles) is in the image, so it runs with no keys and no database.
# Build:  docker build --target api -t materials-triage:api .
# Run:    docker run --rm -p 8000:8000 --env-file .env materials-triage:api

FROM node:20-bookworm-slim AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS api
# uv, pinned; the lock file is the only source of versions.
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1
RUN groupadd --system triage && useradd --system --gid triage --home /app --shell /usr/sbin/nologin triage
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
COPY config/ ./config/
COPY fixtures/ ./fixtures/
COPY scripts/ ./scripts/
COPY docs/SCIENTIST_GUIDE.md docs/ADMIN_GUIDE.md ./docs/
COPY alembic.ini ./
COPY --from=web /build/web/dist ./web/dist
RUN uv sync --frozen --no-dev && mkdir -p /app/.data-cache && chown -R triage:triage /app
USER triage
ENV DATA_CACHE_DIR=/app/.data-cache AUTH_MODE=none LLM_PROVIDER=none FETCH_MODE=replay
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["materials-triage", "serve", "--host", "0.0.0.0", "--port", "8000"]

# Optional split front: nginx serving web/dist, proxying /api to the api service.
FROM nginx:1.27-alpine AS web-nginx
COPY deploy/nginx/web.conf /etc/nginx/conf.d/default.conf
COPY --from=web /build/web/dist /usr/share/nginx/html
EXPOSE 80
