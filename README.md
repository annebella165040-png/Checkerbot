# Annebella Checker Bot

A Telegram registration checker inspired by the supplied reference. Users select a service, submit a mobile number, and receive the provider's Registered / Not Registered response. The bot never stores full phone numbers; only the final four digits are retained for aggregate statistics.

## Features

- Branded `/start` flow with an 18-service reply keyboard
- International mobile-number validation
- Per-user rate limiting
- SQLite user and search statistics
- Restricted `/admin` dashboard
- Password-protected web admin panel at `/admin`
- Force-join channel management and membership verification
- Modern inline checker menu with Bot API button styles
- Optional premium custom emoji for messages and buttons
- Google libphonenumber-based country, type, carrier, and timezone intelligence
- SuperAssets registration-check API integration for all displayed services
- No hard-coded secrets
- Render worker configuration

Use the checker only for numbers you are authorized to process and comply with provider terms and applicable privacy law.

## Local setup

1. Install Python 3.10 or newer.
2. Run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, or set the variables in your shell/platform.
4. Set `BOT_TOKEN`, `CHECKER_API_KEY`, and `ADMIN_IDS` to comma-separated Telegram numeric user IDs.
5. Run `python app.py`.

PowerShell example:

```powershell
$env:BOT_TOKEN = "your-token"
$env:ADMIN_IDS = "123456789"
python app.py
```

## Deploy on Render

Create a Blueprint from this repository. Set `BOT_TOKEN`, `CHECKER_API_KEY`, `ADMIN_IDS`, `ADMIN_PASSWORD`, and `SESSION_SECRET` in Render's environment settings. For durable statistics, attach persistent storage and set `DATABASE_PATH` to a path on that disk.

Open `/admin/login` on the deployed domain to manage required channels and ban/unban users. The bot must be an administrator in every force-join channel so Telegram allows membership checks.

Telegram's current Bot API supports `style` and `icon_custom_emoji_id` on buttons. Set `PREMIUM_EMOJI_ID` to enable a custom emoji. Telegram limits custom emoji usage to eligible bots/owners; the normal emoji fallback remains visible otherwise.

## Checker API

`CHECKER_API_URL` defaults to `https://superassets.in`. Keep `CHECKER_API_KEY` in the hosting platform's secret environment settings; never commit it. The bot treats missing, malformed, and rate-limited provider responses as undetermined instead of falsely reporting Not Registered.
