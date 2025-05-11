Jellyfin Media Downloader BotA Telegram bot that downloads media files you send it, organizes them into your Jellyfin library, and tracks download statistics.📝 FeaturesTelegram-driven downloadsSend any media file (video, audio, document) and the bot saves it straight into your Jellyfin folders.Metadata-driven organizationUses GuessIt + TMDb API to auto-rename and sort into Movies, TV, Anime, Music, or Other.Interactive fallbackWhen confidence is low, use /organize with inline buttons to classify files manually.Bulk propagationAfter a manual TV/Anime organize, propagate remaining episodes one-by-one with confirm/skip.Persistent statsTracks per-user and global download counts, speeds, success rates in TinyDB.Docker-friendlyTwo-stage Docker build, single volume for all persistent data.⚙️ RequirementsDocker ≥ 20.10 & Docker Compose ≥ 1.29Telegram Bot Token & API_ID/API_HASH from my.telegram.orgTMDb API Key (optional; falls back to filename parsing)🛠 InstallationClone the repogit clone https://github.com/youruser/jellyfin-downloader-bot.git
cd jellyfin-downloader-bot
Configure environmentcp .env.example .env
Edit .env with your credentials and any overrides:API_ID=123456
API_HASH=abcdef1234567890
BOT_TOKEN=123456:ABCDEFGHIJKLMNOPQRSTU
ADMIN_IDS=111111111,222222222

# Optional TMDb
TMDB_API_KEY=your_tmdb_key

# Tuning
LOW_CONFIDENCE=0.6
HIGH_CONFIDENCE=0.8
MAX_DOWNLOAD_DURATION=7200

SESSION_NAME=bot_session
Build & startdocker-compose build jellyfin_bot
docker-compose up -d jellyfin_bot
Monitor logsdocker-compose logs -f jellyfin_bot
📂 Directory & DataBy default, everything lives under ./data/jellyfin (bind-mounted to /data/jellyfin in the container):data/jellyfin/
├── Downloads/         # staging area for incoming files
├── Movies/            # Jellyfin library folders
├── TV/
├── Anime/
├── Music/
├── Other/
├── db.json            # TinyDB (users, stats, organized history, cache)
├── bot.log            # rotating logs
└── sessions/          # Telethon session files
```yaml
volumes:
  jellyfin-data:

services:
  jellyfin_bot:
    volumes:
      - jellyfin-data:/data/jellyfin
🤖 Bot CommandsUserCommandDescription/startShow welcome & usage/helpSame as /start/statsYour download stats & bot performance/queueView current downloads & queueSend fileAny supported media to start a downloadAdmin(IDs set in ADMIN_IDS)CommandDescription/organizeManually categorize & rename files in Downloads/Other/propagateBulk-propagate remaining episodes after manual organize/organizedBrowse manually organized entries/historyBrowse full organized history (detail view & delete)/usersCount of unique users/shutdownGracefully shut down the bot📦 Exporting & MigratingSave Docker imagedocker save jellyfin-bot:latest -o jellyfin-bot_image.tar
gzip jellyfin-bot_image.tar
Backup datatar czf jellyfin-data_backup.tar.gz -C data jellyfin
Restore on new host# Load image
gunzip -c jellyfin-bot_image.tar.gz | docker load

# Restore data
mkdir -p ./data/jellyfin
tar xzf jellyfin-data_backup.tar.gz -C ./data/jellyfin

# Start
docker-compose up -d
🐞 TroubleshootingStartup errors: Check .env for missing API_ID, API_HASH, or BOT_TOKEN.Permissions: Ensure ./data/jellyfin is writable by UID 1000 (the container’s non-root user).Session issues: Remove stale *.session files in data/jellyfin/sessions.TMDb errors: Bot will still work with GuessIt if your TMDb key is invalid or rate-limited.⚖️ LicenseMIT © [Your Name or Org]Enjoy seamless Jellyfin downloads via Telegram! 🚀