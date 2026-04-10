FROM python:3.14.3-slim-trixie AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 1000 arvel && \
    useradd --uid 1000 --gid arvel --shell /bin/bash --create-home arvel

FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-project

COPY src/ src/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"

USER arvel

EXPOSE 8000

CMD ["uvicorn", "arvel.http.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
