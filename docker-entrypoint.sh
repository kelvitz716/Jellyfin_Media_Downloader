#!/usr/bin/env sh
set -e

# Re-create any missing data dirs under /data/jellyfin
for d in sessions logs Downloads Movies TV Music Other Anime; do
  mkdir -p "/data/jellyfin/$d"
done

# Ensure the bot user (UID 1000) owns everything under /data/jellyfin
chown -R 1000:1000 /data/jellyfin

# Drop privileges and exec the bot
exec gosu 1000:1000 python main.py