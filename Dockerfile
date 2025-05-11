### 1) Builder: build wheels for all dependencies
FROM python:3.10-slim AS builder
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libmagic1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

### 2) Runtime: install from pre-built wheels and run the bot
FROM python:3.10-slim AS runtime
WORKDIR /app

# 2.1 Install runtime deps + su-exec so we can drop to UID 1000 at runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 gosu \
 && rm -rf /var/lib/apt/lists/*

# 2.2 Copy & install pre-built wheels
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# 2.3 Copy application code and our startup script
COPY . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 2.4 Create the bot user (UID/GID=1000) and a base /data/jellyfin
RUN addgroup --system --gid 1000 bot \
 && adduser  --system --uid 1000 --ingroup bot --disabled-password bot \
 && mkdir -p /data/jellyfin \
 && chown -R bot:bot /data/jellyfin

# 2.5 Use our entrypoint to create subfolders and drop privileges
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD []
