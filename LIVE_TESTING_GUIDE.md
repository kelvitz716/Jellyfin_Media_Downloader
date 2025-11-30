# Live Bot Performance Testing - Setup Guide

## 🚀 Quick Setup

### Step 1: Get Your Bot Username

You need to find your bot's username. You can do this by:

**Option A: Check with BotFather**
1. Open Telegram
2. Search for `@BotFather`
3. Send `/mybots`
4. Click on your bot
5. Look for the username (starts with @)

**Option B: Check your bot's profile**
1. Open your bot in Telegram
2. Click on the bot name at the top
3. Look for the username under the name

### Step 2: Add Bot Username to .env

Add this line to your `.env` file:
```env
BOT_USERNAME=your_bot_username_here
```

**Example:**
```env
BOT_USERNAME=JellyfinDownloaderBot
```

**Note:** Don't include the @ symbol, just the username!

---

## 🎯 Running the Live Test

### Prerequisites:
✅ Bot is running in one terminal
✅ BOT_USERNAME added to .env
✅ You have API_ID and API_HASH (already in .env)

### Steps:

**Terminal 1 - Start the bot:**
```bash
cd "c:\Users\GG\Documents\coding in antigravity\Jellyfin_Media_Downloader"
.\venv\Scripts\python.exe main.py
```

**Terminal 2 - Run live tests:**
```bash
cd "c:\Users\GG\Documents\coding in antigravity\Jellyfin_Media_Downloader"
.\venv\Scripts\python.exe test_live_bot_performance.py
```

---

## 📊 What the Test Does

The live tester will:
1. Connect to Telegram using YOUR user account
2. Send these commands to your bot:
   - `/start` - Welcome message
   - `/help` - Help text
   - `/stats` - Bot statistics
   - `/queue` - Download queue
   - `/users` - Active users (admin only)
   - `/test` - System test

3. Measure for each command:
   - **Send time**: How long to send message to Telegram
   - **Response time**: How long bot takes to process
   - **Total time**: End-to-end latency

4. Generate report with:
   - Average response time
   - Fastest/slowest commands
   - Detailed breakdown
   - JSON file with all data

---

## 🔍 Expected Output

```
🔌 Connecting to Telegram as user...
🤖 Finding bot: @YourBotUsername
✅ Connected! Bot ID: 1234567890

📤 Testing: /start
   Description: Welcome message
   ✅ Response received!
   ⏱️  Send time: 45.2ms
   ⏱️  Response time: 123.4ms
   ⏱️  Total time: 168.6ms
   📝 Response: Welcome to Jellyfin Media Downloader Bot!

📤 Testing: /stats
   Description: Bot statistics
   ✅ Response received!
   ⏱️  Send time: 42.1ms
   ⏱️  Response time: 234.5ms
   ⏱️  Total time: 276.6ms
   📝 Response: 📊 DOWNLOAD STATISTICS...

📊 LIVE BOT PERFORMANCE REPORT
================================================================================
📈 Statistics:
   Commands tested: 6
   Successful: 6
   Failed: 0

⏱️  Response Times:
   Average: 187.3ms
   Fastest: 98.1ms
   Slowest: 2456.7ms
   Avg bot processing: 145.2ms

📋 Detailed Results:
   Command         Total Time   Status
   --------------- ------------ ----------
   /start          168.6ms      ✅
   /help           112.3ms      ✅
   /stats          276.6ms      ✅
   /queue          145.2ms      ✅
   /users          198.7ms      ✅
   /test           2456.7ms     ✅

📁 Results saved to: live_bot_performance.json
```

---

## ⚠️ Troubleshooting

### "Bot not found"
- Make sure BOT_USERNAME is correct (no @ symbol)
- Make sure you've started a conversation with the bot at least once
- Try searching for the bot in Telegram first

### "Connection failed"
- Check your internet connection
- Make sure API_ID and API_HASH are correct
- Try restarting the test

### "No response"
- Make sure the bot is actually running
- Check bot logs for errors
- Verify the bot is responding to manual messages

### "Permission denied"
- Some commands (like /users) are admin-only
- Make sure your Telegram ID is in ADMIN_IDS in .env

---

## 📁 Output Files

After running, you'll get:
- `live_bot_performance.json` - Detailed results with all metrics
- `test_session.session` - Telegram session (can be reused)

---

## 🎯 What to Look For

### Good Performance ✅
- Command response < 500ms
- Consistent response times
- No timeouts

### Needs Investigation ⚠️
- Command response > 1000ms
- Highly variable response times
- Frequent timeouts

### Critical Issues ❌
- Commands timing out
- Error responses
- Bot not responding

---

## 🔄 Next Steps After Testing

1. Review `live_bot_performance.json`
2. Identify slowest commands
3. Compare with automated test results
4. Implement optimizations
5. Re-test to measure improvement

---

## 💡 Tips

- Run the test multiple times for consistency
- Test during different times of day
- Compare before/after optimization
- Save results with timestamps for tracking
