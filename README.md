# Annebella Checker Bot

A privacy-conscious Telegram checker interface inspired by the supplied reference. Users select a service, submit a mobile number, and receive a safe validation response. The bot never stores full phone numbers; only the final four digits are retained for aggregate statistics.

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
- Optional Twilio Lookup v2 integration for live carrier/status/risk packages
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

Create a Blueprint from this repository. Set `BOT_TOKEN`, `ADMIN_IDS`, `ADMIN_PASSWORD`, and `SESSION_SECRET` in Render's environment settings. For durable statistics, attach persistent storage and set `DATABASE_PATH` to a path on that disk.

Open `/admin/login` on the deployed domain to manage required channels and ban/unban users. The bot must be an administrator in every force-join channel so Telegram allows membership checks.

Telegram's current Bot API supports `style` and `icon_custom_emoji_id` on buttons. Set `PREMIUM_EMOJI_ID` to enable a custom emoji. Telegram limits custom emoji usage to eligible bots/owners; the normal emoji fallback remains visible otherwise.

## Phone intelligence

Without paid credentials, the bot uses libphonenumber metadata to report whether the number range is possible/valid, its region, number type, original carrier allocation, and timezone. This does not prove that a number is currently assigned or reachable.

Set `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` to enable Twilio Basic Lookup. Set `TWILIO_LOOKUP_FIELDS` only if you have enabled the corresponding paid packages, such as `line_type_intelligence,line_status`. Twilio bills optional data packages per lookup.

No legitimate provider API exposes whether arbitrary phone numbers have accounts at Amazon, Flipkart, WhatsApp, or the other menu services. The project intentionally does not automate login, password-reset, or OTP endpoints for account enumeration.
