# Jellyfin Media Downloader Bot

**A Telegram bot that downloads media files you send, organizes them into your Jellyfin library, and tracks download statistics.**

---

## 📝 Features

- **Telegram-driven downloads** – Send any media file and the bot saves it to your Jellyfin folders
- **Metadata-driven organization** – Uses [GuessIt](https://github.com/guessit-io/guessit) and TMDb to auto-sort into Movies, TV, Anime, Music, or Other
- **Interactive fallback** – Use `/organize` to manually classify via inline buttons
- **Bulk propagation** – Organize one episode, then auto-apply logic to remaining files with `/propagate`
- **Persistent stats** – Tracks per-user and global metrics using TinyDB
- **Smart queue viewer** – Progress bars, ETA, and paginated queue with cancel buttons
- **Docker-ready** – Two-stage build with auto-bootstrapped folders

---

## ⚙️ Requirements

- **Python** ≥ 3.10 (or Docker)
- **Docker** ≥ 20.10 & **Docker Compose** ≥ 1.29 (for containerized deployment)
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- Optional: TMDb API Key from [themoviedb.org](https://www.themoviedb.org)

---

## 🛠 Installation

### Docker (Recommended)

```bash
git clone https://github.com/youruser/jellyfin-downloader-bot.git
cd jellyfin-downloader-bot
cp .env.example .env
# Edit .env with your credentials
docker compose up -d --build
```

### Local Development

```bash
git clone https://github.com/youruser/jellyfin-downloader-bot.git
cd jellyfin-downloader-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials and BASE_DIR
python main.py
```

---

## 🔧 Configuration

Edit `.env` with your settings:

```ini
# Required
API_ID=123456
API_HASH=abcdef1234567890
BOT_TOKEN=123456:ABCDEF...
ADMIN_IDS=111111111,222222222

# Optional
TMDB_API_KEY=your_tmdb_key
BASE_DIR=/data/jellyfin  # or ~/jellyfin_test for local dev
```

---

## 📂 Project Structure

```
jellyfin-downloader-bot/
├── main.py                    # Slim entry point (~150 lines)
├── src/
│   ├── handlers/              # Modular command handlers
│   │   ├── user.py            # /start, /stats, /queue
│   │   ├── admin.py           # /propagate, /history, /shutdown
│   │   ├── organize.py        # /organize FSM flow
│   │   └── media.py           # Media file handling
│   └── services/              # Reusable services
│       ├── session_manager.py # TTL-based session management
│       ├── rate_limiter.py    # Command rate limiting
│       └── logger.py          # Structured JSON logging
├── config.py                  # Environment configuration
├── config_validated.py        # Pydantic-validated config
├── database.py                # TinyDB operations
├── downloader.py              # Download queue management
├── media_processor.py         # GuessIt + TMDb processing
├── organizer.py               # File organization logic
├── stats.py                   # Statistics tracking
├── utils.py                   # Utility functions
├── tests/                     # Test suite (157 tests)
├── Dockerfile                 # Multi-stage Docker build
└── docker-compose.yml         # Container orchestration
```

---

## 🤖 Bot Commands

### Users

| Command | Description |
|---------|-------------|
| `/start`, `/help` | Welcome message |
| `/stats`, `/status` | View download statistics |
| `/queue` | View current download queue |
| *Send file* | Upload media to download |

### Admins

| Command | Description |
|---------|-------------|
| `/organize` | Manually classify files via inline UI |
| `/propagate` | Apply previous organize to similar files |
| `/history` | Browse organized files with details |
| `/users` | Show total unique users |
| `/shutdown` | Gracefully shut down the bot |

---

## 🧪 Testing

```bash
# Run all tests
python run_tests.py tests/

# Run specific test file
python -m pytest tests/test_stats.py -v

# Skip slow benchmarks
python -m pytest tests/ --benchmark-skip

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

**Test coverage:** 157 tests covering all modules

---

## 🔒 Rate Limiting

Commands are rate-limited to prevent abuse:

| Limiter | Limit | Window |
|---------|-------|--------|
| `command_limiter` | 10 calls | 1 minute |
| `download_limiter` | 5 calls | 1 minute |
| `organize_limiter` | 20 calls | 5 minutes |

---

## 📊 Logging

Structured JSON logging is available:

```python
from src.services.logger import get_logger, setup_structured_logging

setup_structured_logging(json_output=True)
logger = get_logger(__name__)
logger.info("download_complete", filename="movie.mkv", size=1024000)
```

Output:
```json
{"timestamp":"2024-01-15T10:30:00","level":"INFO","message":"download_complete","filename":"movie.mkv","size":1024000}
```

---

## 💾 Backup & Restore

```bash
# Save Docker image
docker save jellyfin_bot:latest | gzip > jellyfin-bot.tar.gz

# Backup data
tar czf jellyfin-data.tar.gz -C data jellyfin

# Restore on new machine
gunzip -c jellyfin-bot.tar.gz | docker load
tar xzf jellyfin-data.tar.gz -C ./data
docker compose up -d
```

---

## 🐞 Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot won't start | Check `.env` for missing credentials |
| Readonly DB error | Ensure `data/jellyfin` is owned by UID 1000 |
| Session issues | Delete `.session` files in `sessions/` |
| TMDb issues | Bot falls back to GuessIt-only parsing |

---

## 📜 License

MIT © Your Name

---

*Built for seamless Jellyfin media management—right from Telegram.* 🚀