# Multi-stage build for TWS Orders API
FROM python:3.11-slim as builder

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-install-project

# Production stage
FROM python:3.11-slim

# Install uv in production image
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY pyproject.toml uv.lock ./
COPY app/ ./app/

# Copy emergency breaker file if it exists
COPY emergency_breaker.json* ./

# Install the project itself
RUN uv sync --frozen

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD uv run python -c "import httpx; r = httpx.get('http://localhost:8001/health'); exit(0 if r.status_code == 200 else 1)"

# Run the application (without uvloop to avoid nest_asyncio conflict)
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--loop", "asyncio"]