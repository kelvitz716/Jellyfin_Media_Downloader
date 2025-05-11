````markdown
# Jellyfin Media Downloader Bot  
**A Telegram bot that downloads media files you send it, organizes them into your Jellyfin library, and tracks download statistics.**

---

## 📝 Features

- **Telegram-driven downloads**  
  Send any media file (video, audio, document) and the bot saves it straight into your Jellyfin folders.  
- **Metadata-driven organization**  
  Uses [GuessIt](https://github.com/guessit-io/guessit) + TMDb API to auto-rename and sort into Movies, TV, Anime, Music, or Other.  
- **Interactive fallback**  
  When confidence is low, use `/organize` with inline buttons to classify files manually.  
- **Bulk propagation**  
  After a manual TV/Anime organize, propagate remaining episodes one-by-one with confirm/skip.  
- **Persistent stats**  
  Tracks per-user and global download counts, speeds, success rates in TinyDB.  
- **Docker-friendly**  
  Two-stage Docker build, single volume for all persistent data.

---

## ⚙️ Requirements

- **Docker** ≥ 20.10 & **Docker Compose** ≥ 1.29  
- **Telegram Bot Token** & **API_ID/API_HASH** from [my.telegram.org](https://my.telegram.org/)  
- **TMDb API Key** (optional; falls back to filename parsing)

---

## 🛠 Installation

1. **Clone the repo**  
   ```bash
   git clone https://github.com/youruser/jellyfin-downloader-bot.git
   cd jellyfin-downloader-bot
````

2. **Configure environment**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your credentials and any overrides:

   ```ini
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
   ```

3. **Build & start**

   ```bash
   docker-compose build jellyfin_bot
   docker-compose up -d jellyfin_bot
   ```

4. **Monitor logs**

   ```bash
   docker-compose logs -f jellyfin_bot
   ```

---

## 📂 Directory & Data

By default, everything lives under `./data/jellyfin` (bind-mounted to `/data/jellyfin` in the container):

```
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
```

<details>
<summary>Using a named volume instead:</summary>

```yaml
volumes:
  jellyfin-data:

services:
  jellyfin_bot:
    volumes:
      - jellyfin-data:/data/jellyfin
```

</details>

---

## 🤖 Bot Commands

### User

| Command     | Description                             |
| ----------- | --------------------------------------- |
| `/start`    | Show welcome & usage                    |
| `/help`     | Same as `/start`                        |
| `/stats`    | Your download stats & bot performance   |
| `/queue`    | View current downloads & queue          |
| *Send file* | Any supported media to start a download |

### Admin

(IDs set in `ADMIN_IDS`)

| Command      | Description                                             |
| ------------ | ------------------------------------------------------- |
| `/organize`  | Manually categorize & rename files in Downloads/Other   |
| `/propagate` | Bulk-propagate remaining episodes after manual organize |
| `/organized` | Browse manually organized entries                       |
| `/history`   | Browse full organized history (detail view & delete)    |
| `/users`     | Count of unique users                                   |
| `/shutdown`  | Gracefully shut down the bot                            |

---

## 📦 Exporting & Migrating

1. **Save Docker image**

   ```bash
   docker save jellyfin-bot:latest -o jellyfin-bot_image.tar
   gzip jellyfin-bot_image.tar
   ```

2. **Backup data**

   ```bash
   tar czf jellyfin-data_backup.tar.gz -C data jellyfin
   ```

3. **Restore on new host**

   ```bash
   # Load image
   gunzip -c jellyfin-bot_image.tar.gz | docker load

   # Restore data
   mkdir -p ./data/jellyfin
   tar xzf jellyfin-data_backup.tar.gz -C ./data/jellyfin

   # Start
   docker-compose up -d
   ```

---

## 🐞 Troubleshooting

* **Startup errors**: Check `.env` for missing `API_ID`, `API_HASH`, or `BOT_TOKEN`.
* **Permissions**: Ensure `./data/jellyfin` is writable by UID 1000 (the container’s non-root user).
* **Session issues**: Remove stale `*.session` files in `data/jellyfin/sessions`.
* **TMDb errors**: Bot will still work with GuessIt if your TMDb key is invalid or rate-limited.

---

## ⚖️ License

MIT © \[Your Name or Org]

---

*Enjoy seamless Jellyfin downloads via Telegram!* 🚀

```
```
