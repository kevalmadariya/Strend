# Stage 1: Build stage
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --frozen --no-install-project --no-dev

# Add the rest of your application code
ADD . /app

# Final sync
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# Stage 2: Final runtime stage
FROM python:3.13-slim-bookworm

WORKDIR /app

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright needs these for browser dependencies
    libnss3 \
    libnspr4 \
    libgbm1 \
    libasound2 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Copy the full app (including venv) from the builder
COPY --from=builder /app /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"

# Install Playwright browsers (and their system deps)
RUN playwright install chromium --with-deps

EXPOSE 8000

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]