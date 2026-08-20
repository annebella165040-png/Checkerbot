# Annebella Checker Bot

A privacy-conscious Telegram checker interface inspired by the supplied reference. Users select a service, submit a mobile number, and receive a safe validation response. The bot never stores full phone numbers; only the final four digits are retained for aggregate statistics.

## Features

- Branded `/start` flow with an 18-service reply keyboard
- International mobile-number validation
- Per-user rate limiting
- SQLite user and search statistics
- Restricted `/admin` dashboard
- No hard-coded secrets
- Render worker configuration

The base implementation does **not** enumerate whether a phone number is registered with third-party services. Add only official, authorized provider integrations and comply with their terms and applicable privacy law.

## Local setup

1. Install Python 3.10 or newer.
2. Run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, or set the variables in your shell/platform.
4. Set `BOT_TOKEN` to the BotFather token and `ADMIN_IDS` to comma-separated Telegram numeric user IDs.
5. Run `python app.py`.

PowerShell example:

```powershell
$env:BOT_TOKEN = "your-token"
$env:ADMIN_IDS = "123456789"
python app.py
```

## Deploy on Render

Create a Blueprint from this repository or create a Background Worker manually. Set `BOT_TOKEN` and `ADMIN_IDS` in Render's environment settings. For durable statistics, attach persistent storage and set `DATABASE_PATH` to a path on that disk.
