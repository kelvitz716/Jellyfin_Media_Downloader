    Jellyfin Media Downloader Bot
    A Telegram bot that downloads media files you send it, organizes them into your Jellyfin library structure (Movies, TV, Anime, Music, Other), and tracks persistent download statistics.

📝 Features

    Telegram-driven downloads: Send any media file (video, audio, document) to the bot and it will download it to your Jellyfin server’s library folders.

    Metadata-driven organization: Uses GuessIt + TMDb API to automatically rename and sort into Movies, TV, Anime, etc.

    Interactive fallback: When confidence is low, or for manual organizing, use /organize and inline buttons to classify files.

    Bulk propagation: After a manual TV/Anime organize, propagate remaining episodes one-by-one with confirm/skip.

    Persistent stats: Tracks per-user and global download counts, speeds, success rates in TinyDB.

    Docker-friendly: Two-stage Docker build for reproducible dependencies; single volume for all persistent data.

⚙️ Requirements

    Docker ≥ 20.10 & Docker Compose ≥ 1.29

    A free TMDb API key (optional—metadata falls back to filename parsing only)

    A Telegram bot token & API credentials

🛠 Installation

    Clone the repo

git clone https://github.com/youruser/jellyfin-downloader-bot.git
cd jellyfin-downloader-bot

Create your .env
Copy and edit .env.example:

cp .env.example .env

Fill in:

API_ID=123456
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

Build & run with Docker Compose

docker-compose build jellyfin_bot
docker-compose up -d jellyfin_bot

Verify logs

    docker-compose logs -f jellyfin_bot

📂 Directory Structure & Volumes

    The bot stores everything under ./data/jellyfin (bind-mounted to /data/jellyfin in the container):

        Downloads/ – temporary download staging

        Movies/, TV/, Anime/, Music/, Other/ – your Jellyfin library folders

        db.json – TinyDB (users, stats, organized history, error logs, metadata cache)

        bot.log – rotating log file

        sessions/ – Telethon session files

    Tip: If you’d rather use a named volume:

    volumes:
      jellyfin-data:
    services:
      jellyfin_bot:
        volumes:
          - jellyfin-data:/data/jellyfin

🤖 Bot Commands

    User

        /start or /help – show welcome & usage

        /stats – show your download stats & overall bot performance

        /queue – view current downloads & queue

        Send any supported media file to start a download.

    Admin (IDs in ADMIN_IDS)

        /organize – manual categorize & rename files waiting in Downloads/Other

        /propagate – bulk-propagate remaining episodes after a manual TV/Anime organize

        /organized – browse manually organized entries

        /history – browse full organized history (with detail view & delete)

        /users – count of unique users

        /shutdown – gracefully shut down the bot

📦 Exporting & Migrating

    Save Docker image

docker save jellyfin-bot:latest -o jellyfin-bot_image.tar
gzip jellyfin-bot_image.tar   # → .tar.gz

Backup data

tar czf jellyfin-data_backup.tar.gz -C data jellyfin

On new host, restore:

    gunzip -c jellyfin-bot_image.tar.gz | docker load
    tar xzf jellyfin-data_backup.tar.gz -C ./data/jellyfin
    docker-compose up -d

🐞 Troubleshooting

    Bot won’t start: Check .env for missing API_ID/API_HASH/BOT_TOKEN.

    Permission errors: Ensure host folder ./data/jellyfin is owned or writable by UID 1000 (the non-root user in container).

    Session issues: Remove old *.session files in data/jellyfin/sessions.

    TMDb failures: If your key is invalid or rate-limited, the bot will still work with guessit fallback.

⚖️ License

MIT © [Your Name or Org]

    Enjoy seamless Jellyfin media downloads via Telegram! 🚀

You said:
make it look good on a .md
ChatGPT said:

    Jellyfin Media Downloader Bot

    A Telegram bot that downloads media files you send it, organizes them into your Jellyfin library, and tracks download statistics.

📝 Features

    Telegram-driven downloads
    Send any media file (video, audio, document) and the bot saves it straight into your Jellyfin folders.

    Metadata-driven organization
    Uses GuessIt + TMDb API to auto-rename and sort into Movies, TV, Anime, Music, or Other.

    Interactive fallback
    When confidence is low, use /organize with inline buttons to classify files manually.

    Bulk propagation
    After a manual TV/Anime organize, propagate remaining episodes one-by-one with confirm/skip.

    Persistent stats
    Tracks per-user and global download counts, speeds, success rates in TinyDB.

    Docker-friendly
    Two-stage Docker build, single volume for all persistent data.

⚙️ Requirements

    Docker ≥ 20.10 & Docker Compose ≥ 1.29

    Telegram Bot Token & API_ID/API_HASH from my.telegram.org

    TMDb API Key (optional; falls back to filename parsing)

🛠 Installation

    Clone the repo

git clone https://github.com/youruser/jellyfin-downloader-bot.git
cd jellyfin-downloader-bot

Configure environment

cp .env.example .env

Edit .env with your credentials and any overrides:

API_ID=123456
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

Build & start

docker-compose build jellyfin_bot
docker-compose up -d jellyfin_bot

Monitor logs

    docker-compose logs -f jellyfin_bot

📂 Directory & Data

By default, everything lives under ./data/jellyfin (bind-mounted to /data/jellyfin in the container):

data/jellyfin/
├── Downloads/         # staging area for incoming files
├── Movies/            # Jellyfin library folders
├── TV/
├── Anime/
├── Music/
├── Other/
├── db.json            # TinyDB (users, stats, organized history, cache)
├── bot.log            # rotating logs
└── sessions/          # Telethon session files

<details> <summary>Using a named volume instead:</summary>

volumes:
  jellyfin-data:

services:
  jellyfin_bot:
    volumes:
      - jellyfin-data:/data/jellyfin

</details>
🤖 Bot Commands
User
Command	Description
/start	Show welcome & usage
/help	Same as /start
/stats	Your download stats & bot performance
/queue	View current downloads & queue
Send file	Any supported media to start a download
Admin

(IDs set in ADMIN_IDS)
Command	Description
/organize	Manually categorize & rename files in Downloads/Other
/propagate	Bulk-propagate remaining episodes after manual organize
/organized	Browse manually organized entries
/history	Browse full organized history (detail view & delete)
/users	Count of unique users
/shutdown	Gracefully shut down the bot
📦 Exporting & Migrating

    Save Docker image

docker save jellyfin-bot:latest -o jellyfin-bot_image.tar
gzip jellyfin-bot_image.tar

Backup data

tar czf jellyfin-data_backup.tar.gz -C data jellyfin

Restore on new host

    # Load image
    gunzip -c jellyfin-bot_image.tar.gz | docker load

    # Restore data
    mkdir -p ./data/jellyfin
    tar xzf jellyfin-data_backup.tar.gz -C ./data/jellyfin

    # Start
    docker-compose up -d

🐞 Troubleshooting

    Startup errors: Check .env for missing API_ID, API_HASH, or BOT_TOKEN.

    Permissions: Ensure ./data/jellyfin is writable by UID 1000 (the container’s non-root user).

    Session issues: Remove stale *.session files in data/jellyfin/sessions.

    TMDb errors: Bot will still work with GuessIt if your TMDb key is invalid or rate-limited.

⚖️ License

MIT © [Your Name or Org]

Enjoy seamless Jellyfin downloads via Telegram! 🚀