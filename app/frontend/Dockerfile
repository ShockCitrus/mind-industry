# =============================================================================
# STAGE 1: Dependencies Builder
# =============================================================================
FROM python:3.12.3-slim AS builder

# Install build dependencies for packages that need compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY ./app/frontend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# =============================================================================
# STAGE 2: Runtime (Slim Production Image)
# =============================================================================
FROM python:3.12.3-slim AS runtime

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /frontend

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY ./app/frontend/ .

# Set environment
ENV PYTHONPATH=/frontend
ENV PYTHONUNBUFFERED=1

EXPOSE 5050

CMD ["python3", "main.py"]
