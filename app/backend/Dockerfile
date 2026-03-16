# =============================================================================
# STAGE 1: Dependencies Builder (Optimized)
# =============================================================================
FROM python:3.12.3-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    git \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Create virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies with CPU-only torch
COPY ./app/backend/requirements.txt /tmp/requirements.txt

# Install torch CPU-only first (saves ~2GB vs CUDA version)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Clone and install NLPipe (shallow clone to save space)
RUN git clone --depth 1 https://github.com/lcalvobartolome/NLPipe.git /opt/NLPipe && \
    pip install --no-cache-dir -e /opt/NLPipe/ && \
    rm -rf /opt/NLPipe/.git

# Download and prepare Mallet
RUN mkdir -p /opt/Mallet && \
    wget -q -O /tmp/mallet.zip https://mallet.cs.umass.edu/dist/mallet-2.0.8.zip && \
    unzip -q /tmp/mallet.zip -d /tmp && \
    mv /tmp/mallet-2.0.8/* /opt/Mallet/ && \
    rm -rf /tmp/mallet* /opt/Mallet/src /opt/Mallet/docs

# =============================================================================
# STAGE 2: Model Downloader (Cached Independently)
# =============================================================================
FROM python:3.12.3-slim AS model-downloader

# Create minimal virtualenv for model download
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install only what's needed to download models (CPU-only torch)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    sentence-transformers==5.1.0 \
    transformers==4.41.2 \
    sentencepiece==0.2.1 \
    "protobuf>=4.25.8"

# Set model cache location
ENV HF_HOME=/opt/models

# Pre-download models (this layer is cached unless models change)
RUN python3 -c "from sentence_transformers import SentenceTransformer; from transformers import AutoModelForSequenceClassification, AutoTokenizer; SentenceTransformer('BAAI/bge-m3'); AutoTokenizer.from_pretrained('potsawee/deberta-v3-large-mnli'); AutoModelForSequenceClassification.from_pretrained('potsawee/deberta-v3-large-mnli'); print('Models downloaded successfully')"

# =============================================================================
# STAGE 3: Runtime (Slim Production Image)
# =============================================================================
FROM python:3.12.3-slim AS runtime

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /backend

# Copy virtualenv from builder (includes all dependencies)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy pre-downloaded models from model-downloader
COPY --from=model-downloader /opt/models /backend/models
ENV HF_HOME=/backend/models

# Copy external dependencies (Mallet, NLPipe)
COPY --from=builder /opt/Mallet /backend/Mallet
COPY --from=builder /opt/NLPipe /backend/NLPipe

# Re-install NLPipe editable link for runtime location
# (the builder's editable install points to /opt/NLPipe which doesn't exist here)
RUN pip install --no-cache-dir --no-deps -e /backend/NLPipe/

# Copy application code (single layer for better caching)
COPY ./app/backend/ /backend/
COPY ./src/mind /src/mind
COPY ./app/config /src/config
COPY ./config.json /backend/NLPipe/config.json

# Create data directory (will be mounted as volume)
RUN mkdir -p /data

# Set environment
ENV PYTHONPATH="/backend:/src:/backend/NLPipe/src"
ENV PYTHONUNBUFFERED=1

EXPOSE 5001

CMD ["sh", "-c", "python3 init_data.py && python3 main.py"]
