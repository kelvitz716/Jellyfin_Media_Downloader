# Jellyfin Media Downloader Bot  
**A Telegram bot that downloads media files you send, organizes them into your Jellyfin library, and tracks download statistics.**

---

## 📝 Features

- **Telegram-driven downloads**  
  Send any media file (video, audio, document), and the bot saves it directly into your Jellyfin folders.

- **Metadata-driven organization**  
  Uses [GuessIt](https://github.com/guessit-io/guessit) and TMDb (if available) to auto-sort files into Movies, TV, Anime, Music, or Other.

- **Interactive fallback**  
  If the guess is low-confidence, use `/organize` to manually classify via inline buttons.

- **Bulk propagation**  
  Organize one episode manually, then auto-apply its logic to remaining files with `/propagate`.

- **Persistent stats**  
  Tracks per-user and global metrics (downloads, speeds, success rate) using TinyDB.

- **Smart `/queue` viewer**  
  Shows rich progress bars, ETA, and paginated queue with cancel buttons.

- **Self-contained Docker setup**  
  Two-stage build, auto-bootstrapped `/data/jellyfin` folders, and user-safe permissions.

---

## ⚙️ Requirements

- **Docker** ≥ 20.10  
- **Docker Compose** ≥ 1.29  
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)  
- Optional TMDb API Key from [themoviedb.org](https://www.themoviedb.org)

---

## 🛠 Installation

1. **Clone the repo**
   ```bash
   git clone https://github.com/youruser/jellyfin-downloader-bot.git
   cd jellyfin-downloader-bot
   ```

2. **Configure the environment**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your Telegram bot credentials and settings:
   ```ini
   API_ID=123456
   API_HASH=abcdef1234567890
   BOT_TOKEN=123456:ABCDEF...
   ADMIN_IDS=111111111,222222222

   TMDB_API_KEY=your_tmdb_key  # optional
   SESSION_NAME=/data/jellyfin/sessions/jellyfin
   ```

3. **Start the bot**
   ```bash
   docker compose up -d --build
   ```

4. **View logs**
   ```bash
   docker compose logs -f jellyfin_bot
   ```

---

## 📂 Directory Layout

All bot data is stored under `./data/jellyfin` and mounted to `/data/jellyfin` inside the container:

```
data/jellyfin/
├── Downloads/         # temporary staging
├── Movies/            # Jellyfin library folders
├── TV/
├── Anime/
├── Music/
├── Other/
├── db.json            # stats, user cache, rename history
├── sessions/          # Telethon auth session
└── logs/              # bot logs (rotated)
```

Optional: use a Docker volume for portability:

```yaml
volumes:
  jellyfin-data:

services:
  jellyfin_bot:
    volumes:
      - jellyfin-data:/data/jellyfin
```

---

## 🤖 Bot Commands

### Users

| Command     | Description                                 |
| ----------- | ------------------------------------------- |
| `/start`    | Show welcome/help message                   |
| `/help`     | Alias for `/start`                          |
| `/stats`    | View personal stats and global totals       |
| `/status`   | Alias for `/stats`                          |
| `/queue`    | View current downloads and queued files     |
| `/queue 2`  | View page 2 of the download queue           |
| *Send file* | Upload a video/audio/document to download   |

### Admins

(IDs must be listed in `ADMIN_IDS`)

| Command      | Description                                             |
| ------------ | ------------------------------------------------------- |
| `/organize`  | Manually classify/rename files via inline UI            |
| `/propagate` | Apply previous organize decision to similar files       |
| `/history`   | Browse all organized files (with details & delete)      |
| `/organized` | List manually organized entries                         |
| `/users`     | Show total unique users                                 |
| `/shutdown`  | Gracefully shut down the bot                            |

---

## 💾 Backup & Restore

### Save Docker image
```bash
docker save jellyfin_bot:latest | gzip > jellyfin-bot.tar.gz
```

### Backup data
```bash
tar czf jellyfin-data.tar.gz -C data jellyfin
```

### Restore on a new machine
```bash
gunzip -c jellyfin-bot.tar.gz | docker load
mkdir -p ./data/jellyfin
tar xzf jellyfin-data.tar.gz -C ./data
docker compose up -d
```

---

## 🐞 Troubleshooting

- **Bot won’t start**: Check `.env` for missing credentials.
- **Readonly DB error**: Ensure `data/jellyfin` and subfolders are owned by UID 1000.
- **Session issues**: Delete `.session` files under `data/jellyfin/sessions/`.
- **TMDb issues**: The bot will fall back to GuessIt-only metadata parsing.

---

## ⚖️ License

MIT © [Your Name or Org]

---

*Built for seamless Jellyfin media management—right from Telegram.* 🚀