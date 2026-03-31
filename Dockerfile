# Stage 1: Build stage
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install system build dependencies + TA-Lib C library
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    build-essential \
    && wget -q https://github.com/TA-Lib/ta-lib/releases/download/v0.6.4/ta-lib_0.6.4_amd64.deb \
    && dpkg -i ta-lib_0.6.4_amd64.deb \
    && rm ta-lib_0.6.4_amd64.deb \
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

# Install TA-Lib runtime + Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    # Playwright needs these for browser dependencies later
    libnss3 \
    libnspr4 \
    libgbm1 \
    libasound2 \
    && wget -q https://github.com/TA-Lib/ta-lib/releases/download/v0.6.4/ta-lib_0.6.4_amd64.deb \
    && dpkg -i ta-lib_0.6.4_amd64.deb \
    && rm ta-lib_0.6.4_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Copy the full app (including venv) from the builder
COPY --from=builder /app /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
# Ensure Python can find the TA-Lib C library if it's in a non-standard path
ENV LD_LIBRARY_PATH="/usr/local/lib"
# Install Playwright browsers (and their system deps)
# We use the venv's playwright version
RUN playwright install chromium --with-deps

EXPOSE 8000

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
# # Stage 1: Build stage
# FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# # Set the working directory
# WORKDIR /app

# # Enable bytecode compilation for faster startup
# ENV UV_COMPILE_BYTECODE=1
# # Use copy instead of hardlinks (better for Docker)
# ENV UV_LINK_MODE=copy

# # Install ta-lib C library from pre-built .deb (needed for pip ta-lib package)
# RUN apt-get update && apt-get install -y --no-install-recommends wget \
#     && wget -q https://github.com/TA-Lib/ta-lib/releases/download/v0.6.4/ta-lib_0.6.4_amd64.deb \
#     && dpkg -i ta-lib_0.6.4_amd64.deb \
#     && rm ta-lib_0.6.4_amd64.deb \
#     && rm -rf /var/lib/apt/lists/*

# # Install dependencies first (for better caching)
# RUN --mount=type=cache,target=/root/.cache/uv \
#     --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
#     --mount=type=bind,source=uv.lock,target=uv.lock \
#     --mount=type=bind,source=.python-version,target=.python-version \
#     uv sync --frozen --no-install-project --no-dev

# # Add the rest of your application code
# ADD . /app

# # Sync the project
# RUN --mount=type=cache,target=/root/.cache/uv \
#     uv sync --frozen --no-dev


# # Stage 2: Final runtime stage
# FROM python:3.13-slim-bookworm

# WORKDIR /app

# # Install ta-lib runtime library + system deps
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     wget \
#     gnupg \
#     && wget -q https://github.com/TA-Lib/ta-lib/releases/download/v0.6.4/ta-lib_0.6.4_amd64.deb \
#     && dpkg -i ta-lib_0.6.4_amd64.deb \
#     && rm ta-lib_0.6.4_amd64.deb \
#     && rm -rf /var/lib/apt/lists/*

# # Copy the full app (including venv) from the builder
# COPY --from=builder /app /app

# # Set the path to use the virtual environment created by uv
# ENV PATH="/app/.venv/bin:$PATH"

# # Install Playwright browsers
# RUN playwright install chromium --with-deps

# # Expose the port FastAPI runs on
# EXPOSE 8000

# # Make start script executable
# RUN chmod +x /app/start.sh

# # Start the wrapper script
# CMD ["/app/start.sh"]