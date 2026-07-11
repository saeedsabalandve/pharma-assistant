# ============================================================================
# Multi-stage Docker build for PharmaAssist microservice
# Stage 1: Builder - Compiles dependencies
# Stage 2: Production - Minimal runtime image
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

# Set build-time environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.7.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="${POETRY_HOME}/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml poetry.lock ./

# Install dependencies (without dev packages)
RUN poetry install --only main --no-root

# ---------------------------------------------------------------------------
# Stage 2: Production Runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS production

# Create non-root user
RUN groupadd --system --gid 1001 pharma \
    && useradd --system --uid 1001 --gid pharma pharma

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libssl3 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    APP_ENV="production"

# Create application directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/
COPY config/ /app/config/
COPY scripts/ /app/scripts/

# Copy entrypoint script
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create directories for logs and data
RUN mkdir -p /var/log/pharma /var/run/pharma \
    && chown -R pharma:pharma /app /var/log/pharma /var/run/pharma

# Switch to non-root user
USER pharma

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose API port
EXPOSE 8000

# Use entrypoint script
ENTRYPOINT ["/entrypoint.sh"]

# Default command (can be overridden)
CMD ["gunicorn", "src.main:app", \
     "--config", "config/gunicorn.conf.py", \
     "--bind", "0.0.0.0:8000"]
