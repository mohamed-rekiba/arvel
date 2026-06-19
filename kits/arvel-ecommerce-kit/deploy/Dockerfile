# syntax=docker/dockerfile:1

# Build from monorepo root:
#   docker build -f kits/arvel-ecommerce-kit/deploy/Dockerfile --target app -t rekiba/ecommerce-app:local .
#   docker build -f kits/arvel-ecommerce-kit/deploy/Dockerfile --target scheduler -t rekiba/ecommerce-scheduler:local .

ARG NODE_VERSION=24.15.0-alpine3.23
ARG PYTHON_VERSION=3.14.5-slim-bookworm
ARG UV_VERSION=0.11.16

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM node:${NODE_VERSION} AS frontend
WORKDIR /src/kits/arvel-ecommerce-kit/frontend
COPY kits/arvel-ecommerce-kit/frontend/package.json kits/arvel-ecommerce-kit/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY kits/arvel-ecommerce-kit/frontend/ ./
RUN npm run build

FROM python:${PYTHON_VERSION} AS python-deps
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY kits/arvel-ecommerce-kit/ kits/arvel-ecommerce-kit/
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --frozen --all-packages --all-extras --no-dev --no-editable

FROM python:${PYTHON_VERSION} AS runtime
WORKDIR /app/kits/arvel-ecommerce-kit/backend
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    UV_PROJECT_ENVIRONMENT=/app/.venv
COPY --from=python-deps /app/.venv /app/.venv
COPY --from=python-deps /app/kits/arvel-ecommerce-kit/backend /app/kits/arvel-ecommerce-kit/backend
COPY --from=frontend /src/kits/arvel-ecommerce-kit/frontend/dist /app/kits/arvel-ecommerce-kit/frontend/dist
RUN groupadd --system arvel && useradd --system --gid arvel --home-dir /app arvel \
    && chown -R arvel:arvel /app
USER arvel
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=2)"

FROM runtime AS app
CMD ["arvel", "serve", "--host", "0.0.0.0", "--port", "8001"]

FROM runtime AS scheduler
CMD ["arvel", "schedule:work", "--sleep", "60"]
