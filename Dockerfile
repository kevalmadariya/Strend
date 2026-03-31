# Stage 1: Build stage
FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

# Set the working directory
WORKDIR /app

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1
# Use copy instead of hardlinks (better for Docker)
ENV UV_LINK_MODE=copy

# Install dependencies first (for better caching)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

# Add the rest of your application code
ADD . /app

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# Stage 2: Final runtime stage
FROM python:3.12-alpine

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app /app

# Set the path to use the virtual environment created by uv
ENV PATH="/app/.venv/bin:$PATH"

# Expose the port FastAPI runs on
EXPOSE 8000

# Start the FastAPI server
# Using '0.0.0.0' is required to allow external access in AWS
CMD ["fastapi", "run", "main.py", "--port", "8000", "--host", "0.0.0.0"]