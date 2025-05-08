# 1) Builder: build wheels for all dependencies
FROM python:3.10-slim AS builder
WORKDIR /app
# Install build tools and libmagic for python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Build wheels for requirements including dependencies
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# 2) Runtime: install from pre-built wheels
FROM python:3.10-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy all wheels
COPY --from=builder /wheels /wheels
COPY requirements.txt .
# Install using wheels, no network access
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# Copy application code
COPY . .

# Prepare data directory and run as non-root
RUN mkdir -p /data/jellyfin && chown -R 1000:1000 /data/jellyfin
USER 1000

# Launch the bot
CMD ["python", "main.py"]