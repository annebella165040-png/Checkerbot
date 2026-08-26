# Annebella Checker Bot

A Telegram registration checker inspired by the supplied reference. Users select a service, submit a mobile number, and receive the provider's Registered / Not Registered response. The bot never stores full phone numbers; only the final four digits are retained for aggregate statistics.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new)
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/annebella165040-png/Checkerbot)

> Use only with mobile numbers you own or are authorized to check. Never commit bot tokens, provider keys, payment credentials, or production databases.

## Features

- Branded `/start` flow with an inline-only 18-service checker directory
- Search Service directory indexing 165 public/API platforms without crowding the checker buttons
- Persistent premium-ID dashboard keyboard for Profile, Credits, Mini App, Gift Card, Referrals, Guide and Support
- International mobile-number validation
- Per-user rate limiting
- SQLite user and search statistics
- Restricted `/admin` dashboard
- Password-protected web admin panel at `/admin`
- Force-join channel management and membership verification
- TempSMS-style force-join progress, per-channel JOIN/JOINED buttons, refresh verification and support access
- Modern inline checker menu with Bot API button styles
- Optional premium custom emoji for messages and buttons
- Google libphonenumber-based country, type, carrier, and timezone intelligence
- SuperAssets registration-check API integration for all displayed services
- 150 one-time welcome credits and 5-credit determined lookups
- 20-credit deep-link referral rewards with self-referral and duplicate-account protection
- TempSms-style UPI/USDT credit packages, screenshot/reference submissions, and administrator approval
- Telegram admin approval cards with premium approve/decline buttons for payment screenshots and references
- API Access store with weekly, monthly, and yearly plans; approved orders generate a private `X-API-Key`
- Public customer API endpoints at `/api/v1/me` and `/api/v1/check`
- 1000-credit permanent Mini App unlock with signed launch links
- Responsive Mini App for balance, referral, service-directory and recent-activity views
- One-time gift-card generation, administration and redemption
- Professional in-bot profile, support-ticket and payment guidance flows
- Premium custom emoji IDs and blue/green/red button styles
- No hard-coded secrets
- Render worker configuration

Use the checker only for numbers you are authorized to process and comply with provider terms and applicable privacy law.

## Local setup

1. Install Python 3.10 or newer.
2. Run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, or set the variables in your shell/platform.
4. Set `BOT_TOKEN`, `BOT_USERNAME`, `CHECKER_API_KEY`, `PAYMENT_UPI_ID`, and `ADMIN_IDS`.
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

Telegram's current Bot API supports `style` and `icon_custom_emoji_id` on buttons. The dashboard uses dedicated premium IDs from the TempSmsBot design; `PREMIUM_EMOJI_ID` can override message-level branding. Telegram limits custom emoji usage to eligible bots/owners.

## Deploy on Railway

1. Click **Deploy on Railway** above, choose **Deploy from GitHub repo**, and select `annebella165040-png/Checkerbot`.
2. Add every required secret from `.env.example`, especially `BOT_TOKEN`, `CHECKER_API_KEY`, `ADMIN_IDS`, `ADMIN_PASSWORD`, and `SESSION_SECRET`.
3. Generate a public domain in **Settings → Networking**.
4. Set `PUBLIC_APP_URL` to the Railway domain root, for example `https://web-production-b80e9.up.railway.app`.
5. Set `MINI_APP_URL` to the Mini App route, for example `https://web-production-b80e9.up.railway.app/miniapp`.
6. Redeploy, then confirm `https://your-domain/healthz` returns `{"ok": true, ...}`.

For persistent users, credits and history, attach a Railway volume and set `DATABASE_PATH` to a file inside its mount path, for example `/data/checkerbot.db`. Run only one replica because Telegram long polling permits one active consumer for a bot token.

## Deploy on Heroku

1. Click **Deploy to Heroku** above and provide all required Config Vars.
2. After deployment, set `PUBLIC_APP_URL` and `MINI_APP_URL` to `https://your-app.herokuapp.com`.
3. Ensure exactly one `web` dyno is active and verify `/healthz`.

Heroku's filesystem is ephemeral. Use an external/durable database for production records; a local SQLite file can be lost during restart or redeploy.

## Force-join setup

Open `/admin/login`, select **Channels**, and add each required channel's exact `@username` or numeric `-100...` chat ID, title, and public/invite URL. Promote the bot to administrator in every configured channel. Users then see live progress, missing channels, premium-emoji JOIN/JOINED buttons, CHECK JOINED, REFRESH and Support controls before dashboard access is unlocked.

If membership always shows missing, confirm the chat ID and bot administrator status first. A private channel must use a valid invite URL while its membership lookup uses the numeric chat ID.

## Checker API

`CHECKER_API_URL` defaults to `https://superassets.in`. Keep `CHECKER_API_KEY` in the hosting platform's secret environment settings; never commit it. The bot treats missing, malformed, and rate-limited provider responses as undetermined instead of falsely reporting Not Registered.

Indexed services such as Spotify, Netflix, Facebook, Instagram, Threads, Apple, Viber, Zalo, BAND, GoTo, Indiatimes and HeadHunter can be connected through the optional eKYCPro provider bridge. Set `EKYCPRO_API_URL=https://api.ekycpro.com` and `EKYCPRO_API_KEY` in Railway/Heroku config vars. When the provider returns a determined result, the bot shows Registered or Not Registered and deducts the configured lookup cost; missing keys, provider errors and undetermined responses cost zero credits.

## Credits, referrals and payments

New users receive 150 credits. A determined provider lookup costs 5 credits; unavailable or undetermined responses are not charged. A referrer receives 20 credits only when a genuinely new Telegram account starts through `https://t.me/<BOT_USERNAME>?start=ref_<telegram_id>`.

The Buy Credit flow first lets users choose **API Access** or **Credit Balance**. Credit Balance supports 100/500/1000/5000 packages, custom quantities, UPI and USDT destinations, transaction references, and screenshot/document proof. API Access supports weekly, monthly, and yearly plans; approval generates a private API key for the user. An administrator can approve or decline from Telegram inline buttons or from `/admin`. The bot never asks users for an OTP, UPI PIN, password, wallet seed phrase, or card details.

## Customer API

Approved API customers receive an `ABAPI_...` key. Use it with:

- `GET /api/v1/me` with header `X-API-Key: <key>`
- `POST /api/v1/check` with header `X-API-Key: <key>` and JSON body `{"service":"Flipkart","number":"+919876543210"}`

API plan access must be active and the user must have enough checker credits. A determined API lookup deducts the configured `CHECK_COST`.

## Advanced administrator panel

The password-protected panel includes operational statistics, force-join channel management, user suspension/restoration, manual credit adjustments, payment approval/rejection, and a support-ticket queue. Use HTTPS, a strong `ADMIN_PASSWORD`, and a durable `DATABASE_PATH` in production.

## Project files

- `app.py` — Telegram bot, API integration, Mini App and admin routes
- `templates/` — responsive TempSMS-style web interfaces
- `.env.example` — complete environment-variable template
- `railway.json` — Railway build, health check and restart policy
- `app.json` — Heroku one-click deployment manifest
- `render.yaml` — Render Blueprint
- `Procfile` — web process declaration
- `.python-version` — portable Python runtime selection
- `LICENSE` — MIT license

## License

Released under the [MIT License](LICENSE).
