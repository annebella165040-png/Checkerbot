import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import json
from html import escape
from urllib.parse import urlencode
from contextlib import closing
from functools import wraps

from flask import Flask, Response, flash, redirect, render_template, request, session, url_for
import httpx
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType, ParseMode
from telegram.error import BadRequest, Forbidden, TimedOut
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, ExtBot, MessageHandler, filters


BOT_NAME = "Annebella Checker Bot"
REPO_CUSTOM_SERVICES_FILE = os.path.join(os.path.dirname(__file__), "config", "custom_services.json")
SERVICES = [
    "Shein", "Flipkart", "Swiggy", "Myntra",
    "Oyo", "Bigbasket", "Blinkit", "Mantrimall",
    "Brevistay", "Ajio", "Amazon", "MyJio",
    "CrownIt", "Meesho", "GoSats", "Telegram",
    "WhatsApp", "HabitYoga", "Plutos", "Starexch",
    "Lenskart",
]
SERVICE_IDS = {
    "MyJio": "jio",
    "HabitYoga": "habuildyoga",
}
API_DIRECTORY = [
    ("eKYCPro WhatsApp Number Checker", "Phone registration checker provider; service_type ws; send phone number"),
    ("eKYCPro WhatsApp Avatar Checker", "Phone registration/avatar checker provider; service_type ws_avatar; send phone number"),
    ("eKYCPro WhatsApp Business Checker", "Phone business registration checker provider; service_type ws_business; send phone number"),
    ("eKYCPro Telegram Number Checker", "Phone registration checker provider; service_type telegram; send phone number"),
    ("eKYCPro Facebook Phone Checker", "Phone registration checker provider; service_type facebook; send phone number"),
    ("eKYCPro Instagram Phone Checker", "Phone registration checker provider; service_type instagram; send phone number"),
    ("eKYCPro Threads Phone Checker", "Phone registration checker provider; service_type threads; send phone number"),
    ("eKYCPro X Twitter Phone Checker", "Phone registration checker provider; service_type twitter; send phone number"),
    ("eKYCPro Apple iMessage Checker", "Phone registration checker provider; service_type apple; send phone number"),
    ("eKYCPro Viber Number Checker", "Phone registration checker provider; service_type viber; send phone number"),
    ("eKYCPro Zalo Number Checker", "Phone registration checker provider; service_type zalo; send phone number"),
    ("eKYCPro Amazon Phone Checker", "Phone registration checker provider; service_type amazon; send phone number"),
    ("eKYCPro Microsoft Phone Checker", "Phone registration checker provider; service_type microsoft; send phone number"),
    ("eKYCPro BAND Phone Checker", "Phone registration checker provider; service_type band; send phone number"),
    ("eKYCPro GoTo Phone Checker", "Phone registration checker provider; service_type goto; send phone number"),
    ("eKYCPro Indiatimes Phone Checker", "Phone registration checker provider; service_type indiatimes; send phone number"),
    ("eKYCPro HeadHunter Phone Checker", "Phone registration checker provider; service_type hh; send phone number"),
    ("eKYCPro Facebook Email Checker", "Email registration checker provider; service_type facebook_email; send email address"),
    ("eKYCPro Instagram Email Checker", "Email registration checker provider; service_type instagram_email; send email address"),
    ("eKYCPro Apple Email Checker", "Email registration checker provider; service_type apple_email; send email address"),
    ("eKYCPro Amazon Email Checker", "Email registration checker provider; service_type amazon_email; send email address"),
    ("eKYCPro Netflix Email Checker", "Email registration checker provider; service_type netflix; send email address"),
    ("eKYCPro Spotify Email Checker", "Email registration checker provider; service_type spotify_email; send email address"),
    ("NumberChecker WhatsApp Checker", "Phone registration checker provider; send phone number"),
    ("NumberChecker Telegram Checker", "Phone registration checker provider; send phone number"),
    ("NumberChecker Amazon Checker", "Phone registration checker provider; send phone number"),
    ("NumberChecker iMessage Checker", "Phone registration checker provider; send phone number"),
    ("NumberChecker Microsoft Checker", "Phone registration checker provider; send phone number"),
    ("NumberChecker LINE Checker", "Phone registration checker provider; send phone number"),
    ("NumberChecker Viber Checker", "Phone registration checker provider; send phone number"),
    ("ProWebLook Flipkart Number Checker", "Phone registration checker provider; send Indian mobile number"),
    ("WAHA WhatsApp Exists Checker", "WhatsApp session-based phone existence checker; send phone number"),
    ("Wawp WhatsApp Number Checker", "WhatsApp session-based phone existence checker; send phone number"),
    ("Whatsscale WhatsApp Number Checker", "WhatsApp session-based phone existence checker; send phone number"),
    ("Ignorant Amazon Checker", "OSINT-style account presence checker; send phone/email only with authorization"),
    ("Ignorant Instagram Checker", "OSINT-style account presence checker; send phone/email only with authorization"),
    ("Ignorant Snapchat Checker", "OSINT-style account presence checker; send phone/email only with authorization"),
    ("GSMA Number Verification", "Consent-based mobile number/SIM verification API; send verified phone session"),
    ("Twilio Lookup", "Phone validity, carrier, line type and intelligence API; send phone number"),
    ("Vonage Number Insight", "Phone validity, carrier, roaming and risk API; send phone number"),
    ("Abstract Phone Validation", "Phone validation and carrier lookup API; send phone number"),
    ("NumVerify", "Phone validation and carrier lookup API; send phone number"),
    ("Neutrino Phone Validate", "Phone validation, location and carrier API; send phone number"),
    ("Loqate Phone Validation", "Phone validation and international formatting API; send phone number"),
    ("IPQualityScore Phone Validation", "Phone risk, fraud score and line intelligence API; send phone number"),
    ("Telesign PhoneID", "Phone type, carrier and risk verification API; send phone number"),
    ("Veriphone", "Phone validation and carrier lookup API; send phone number"),
    ("Instagram", "Social / Meta professional account API"),
    ("Facebook", "Social graph, pages, ads and login API"),
    ("WhatsApp Business", "Business messaging Cloud API"),
    ("Messenger", "Meta messaging and page inbox API"),
    ("Threads", "Meta Threads publishing and profile API"),
    ("X / Twitter", "Posts, users, trends and OAuth API"),
    ("YouTube", "Videos, channels, search and analytics API"),
    ("TikTok", "Login, content and business APIs"),
    ("Reddit", "Posts, comments, subreddit and OAuth API"),
    ("LinkedIn", "Sign-in, profile, share and business APIs"),
    ("Discord", "Bot, OAuth, guild and interaction API"),
    ("Snapchat", "Login Kit, Bitmoji and marketing API"),
    ("Pinterest", "Pins, boards and ads API"),
    ("Tumblr", "Blogging and post API"),
    ("Mastodon", "Open social network API"),
    ("Bluesky", "AT Protocol social API"),
    ("Twitch", "Streams, channels and clips API"),
    ("Spotify", "Music catalog and account OAuth API"),
    ("SoundCloud", "Audio and creator API"),
    ("Vimeo", "Video upload and metadata API"),
    ("Telegram", "Bot API and MTProto platform API"),
    ("LINE", "Messaging and login API"),
    ("Viber", "Bot messaging API"),
    ("WeChat Open Platform", "Login and mini-program APIs"),
    ("KakaoTalk", "Kakao login and messaging API"),
    ("Google Search", "Search/programmable search APIs"),
    ("Gmail", "Mailbox API with user OAuth"),
    ("Google Drive", "File storage API"),
    ("Google Calendar", "Calendar and event API"),
    ("Google Maps", "Maps, routes and geocoding API"),
    ("Google Places", "Places and business discovery API"),
    ("Google Search Console", "Site performance API"),
    ("Google Analytics", "Analytics reporting API"),
    ("Google Ads", "Advertising management API"),
    ("Google Translate", "Translation API"),
    ("Microsoft Graph", "Microsoft 365 unified API"),
    ("Outlook", "Mail and calendar through Graph API"),
    ("OneDrive", "Cloud file storage API"),
    ("Microsoft Teams", "Teams app and collaboration API"),
    ("SharePoint", "Site and document API"),
    ("Azure", "Cloud resource management APIs"),
    ("GitHub", "Repository, issue and action APIs"),
    ("GitLab", "Repository and DevOps API"),
    ("Bitbucket", "Repository and workspace API"),
    ("Slack", "Workspace bot and messaging API"),
    ("Notion", "Workspace database/page API"),
    ("Trello", "Board, card and list API"),
    ("Asana", "Task and project API"),
    ("ClickUp", "Task and workspace API"),
    ("Jira", "Issue and project API"),
    ("Confluence", "Knowledge base API"),
    ("Monday.com", "Work management GraphQL API"),
    ("Airtable", "Table/database API"),
    ("Todoist", "Task management API"),
    ("Dropbox", "Cloud file API"),
    ("Box", "Enterprise file API"),
    ("Canva", "Design and app APIs"),
    ("Figma", "Design file and plugin API"),
    ("Miro", "Whiteboard API"),
    ("Zoom", "Meetings and webinar API"),
    ("Calendly", "Scheduling API"),
    ("DocuSign", "E-signature API"),
    ("Adobe", "Creative/document APIs"),
    ("WordPress", "CMS REST API"),
    ("Shopify", "Storefront and admin APIs"),
    ("WooCommerce", "WordPress commerce API"),
    ("Amazon Selling Partner", "Seller catalog/order API"),
    ("Amazon Ads", "Advertising API"),
    ("eBay", "Marketplace and inventory API"),
    ("Etsy", "Marketplace listing API"),
    ("Walmart", "Marketplace and affiliate APIs"),
    ("Best Buy", "Product catalog API"),
    ("Flipkart Affiliate", "Affiliate product API"),
    ("BigCommerce", "Commerce admin API"),
    ("Adobe Commerce / Magento", "Commerce API"),
    ("Square", "Payments and commerce API"),
    ("Stripe", "Payments and billing API"),
    ("PayPal", "Payments and checkout API"),
    ("Razorpay", "Indian payments API"),
    ("Paytm", "Payments and wallet API"),
    ("Cashfree", "Payments and payout API"),
    ("PhonePe", "Payments API"),
    ("Coinbase", "Crypto exchange/account API"),
    ("Binance", "Crypto exchange API"),
    ("CoinMarketCap", "Crypto market data API"),
    ("CoinGecko", "Crypto market data API"),
    ("Yahoo Finance", "Market data APIs"),
    ("Alpha Vantage", "Stock and forex data API"),
    ("Plaid", "Bank account connectivity API"),
    ("Alpaca", "Trading and market data API"),
    ("Polygon.io", "Market data API"),
    ("Finnhub", "Financial market data API"),
    ("Twelve Data", "Market data API"),
    ("Open Exchange Rates", "FX rates API"),
    ("Fixer", "Currency conversion API"),
    ("Wise", "International transfer API"),
    ("RazorpayX", "Business banking/payout API"),
    ("PayU", "Payment gateway API"),
    ("CCAvenue", "Payment gateway API"),
    ("Instamojo", "Payment links and orders API"),
    ("OpenWeather", "Weather data API"),
    ("WeatherAPI", "Weather forecast API"),
    ("AccuWeather", "Weather forecast API"),
    ("HERE Maps", "Maps and routing API"),
    ("Mapbox", "Maps and geocoding API"),
    ("TomTom", "Maps and traffic API"),
    ("OpenStreetMap / Nominatim", "Open geocoding API"),
    ("Foursquare", "Places and venue API"),
    ("Yelp", "Business search API"),
    ("Tripadvisor", "Travel content API"),
    ("Booking.com", "Partner travel APIs"),
    ("Expedia", "Partner travel APIs"),
    ("Amadeus", "Flights and travel API"),
    ("Skyscanner", "Flight search APIs"),
    ("Aviationstack", "Flight data API"),
    ("Uber", "Rides and delivery APIs"),
    ("Lyft", "Ride API"),
    ("Twilio", "SMS, voice and WhatsApp API"),
    ("Vonage", "SMS and voice API"),
    ("MessageBird / Bird", "Omnichannel messaging API"),
    ("Plivo", "SMS and voice API"),
    ("SendGrid", "Email delivery API"),
    ("Mailchimp", "Email marketing API"),
    ("Mailgun", "Email delivery API"),
    ("Brevo / Sendinblue", "Email and marketing API"),
    ("Postmark", "Transactional email API"),
    ("Klaviyo", "Marketing automation API"),
    ("HubSpot", "CRM and marketing API"),
    ("Salesforce", "CRM platform API"),
    ("Zoho", "Business suite APIs"),
    ("Zendesk", "Support ticket API"),
    ("Freshdesk", "Support desk API"),
    ("Intercom", "Customer messaging API"),
    ("Pipedrive", "Sales CRM API"),
    ("Salesloft", "Sales engagement API"),
    ("Apollo.io", "Sales intelligence API"),
    ("Clearbit", "Company/person enrichment API"),
    ("Hunter.io", "Email discovery API"),
    ("Firebase", "Backend, auth and database APIs"),
    ("Supabase", "Database, auth and storage APIs"),
    ("Cloudflare", "DNS, CDN and security APIs"),
    ("AWS", "Cloud service APIs"),
    ("DigitalOcean", "Cloud hosting API"),
    ("Heroku", "App hosting API"),
    ("Railway", "App deployment API"),
    ("Vercel", "Frontend hosting API"),
    ("Netlify", "Site hosting API"),
    ("Sentry", "Error monitoring API"),
    ("Datadog", "Monitoring and logs API"),
    ("New Relic", "Observability API"),
    ("Grafana", "Dashboard and monitoring API"),
    ("PagerDuty", "Incident response API"),
    ("Statuspage", "Public status page API"),
    ("VirusTotal", "URL/file/domain threat intelligence API"),
    ("urlscan.io", "Website scan and screenshot API"),
    ("Google Safe Browsing", "Unsafe URL lookup API"),
    ("Shodan", "Internet-exposed device search API"),
    ("AbuseIPDB", "IP reputation API"),
    ("Have I Been Pwned", "Breach lookup API"),
    ("IPinfo", "IP geolocation/company API"),
    ("ipapi", "IP geolocation API"),
    ("WhoisXML API", "WHOIS, DNS and domain intelligence API"),
    ("SecurityTrails", "DNS and domain intelligence API"),
    ("BuiltWith", "Website technology lookup API"),
    ("Wappalyzer", "Website technology lookup API"),
]
PHONE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")
RATE_LIMIT_SECONDS = 5
DB_PATH = os.getenv("DATABASE_PATH", "checkerbot.db")
WEB_PORT = int(os.getenv("PORT", "8080"))
PREMIUM_EMOJI_ID = os.getenv("PREMIUM_EMOJI_ID", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "AnneBellaCheckerBot").strip().lstrip("@")
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/annebella").strip()
SIGNUP_CREDITS = int(os.getenv("SIGNUP_CREDITS", "150"))
REFERRAL_CREDITS = int(os.getenv("REFERRAL_CREDITS", "20"))
CHECK_COST = int(os.getenv("CHECK_COST", "5"))
MINI_APP_COST = int(os.getenv("MINI_APP_COST", "1000"))
SERVICE_PAGE_SIZE = int(os.getenv("SERVICE_PAGE_SIZE", "36"))
API_BASE_URL = os.getenv("PUBLIC_API_BASE_URL", os.getenv("MINI_APP_URL", "https://web-production-b80e9.up.railway.app")).strip().rstrip("/")
if API_BASE_URL.endswith("/miniapp"):
    API_BASE_URL = API_BASE_URL[:-8]
API_PLANS = {
    "api_weekly": {"item_type": "api", "plan": "WEEKLY API ACCESS", "duration_days": 7, "price": 100, "currency": "USD"},
    "api_monthly": {"item_type": "api", "plan": "MONTHLY API ACCESS", "duration_days": 30, "price": 250, "currency": "USD"},
    "api_yearly": {"item_type": "api", "plan": "YEARLY API ACCESS", "duration_days": 365, "price": 900, "currency": "USD"},
}
CREDIT_PACKAGES = {
    "buy_100": {"item_type": "credit", "credits": 100, "price": 49, "currency": "INR"},
    "buy_500": {"item_type": "credit", "credits": 500, "price": 199, "currency": "INR"},
    "buy_1000": {"item_type": "credit", "credits": 1000, "price": 349, "currency": "INR"},
    "buy_5000": {"item_type": "credit", "credits": 5000, "price": 999, "currency": "INR"},
}

EMOJI_IDS = {
    "sparkle": "5289722755871162900",
    "profile": "5269531045165816230",
    "search": "5893382531037794941",
    "credits": "5253742260054409879",
    "referral": "5197269100878907942",
    "support": "6026056450223116307",
    "buy": "5445353829304387411",
    "back": "5352759161945867747",
    "check": "6206479140040743133",
    "gift": "5359664288241829619",
    "help": "6206108815075579644",
    "miniapp": "6035152649790164056",
    "home": "6204010762206189094",
    "upi": "6019521004647223512",
    "usdt": "6035152649790164056",
    "payment": "5395358455768837479",
    "name": "5190806721286657692",
    "link": "5339286072876614251",
    "id": "5404561694510833322",
    "joined": "5195033767969839232",
    "lightning": "5224607267797606837",
    "phone": "6206446249181189526",
    "money": "6206378324273403309",
    "history": "6206497372176913599",
    "refresh": "5339233635620899144",
    "star": "6204162490515855272",
    "wave": "5247133031235329609",
    "warn": "6206174450765796040",
    "trophy": "6203750195130274981",
    "rocket": "5372917041193828849",
    "fire": "6206080502651164081",
    "lock": "6206404510689007446",
    "globe": "5372849966689566579",
    "india": "5291933173674957761",
    "key": "5893382531037794941",
}
EMOJI_FALLBACKS = {
    "sparkle": "✨", "profile": "👤", "search": "🔎", "credits": "💎",
    "referral": "👥", "support": "🖥️", "buy": "💳", "back": "📶",
    "check": "✅", "gift": "🎁", "help": "🎵", "miniapp": "🖥️",
    "home": "🏠", "upi": "💸", "usdt": "🖥️",
    "payment": "💳", "name": "📛", "link": "🔗", "id": "🆔",
    "joined": "📅", "lightning": "⚡", "phone": "📱", "money": "💰",
    "history": "📋", "refresh": "🔄", "star": "⭐", "wave": "〰️",
    "warn": "⚠️", "trophy": "🏆",
    "rocket": "🚀", "fire": "🔥", "lock": "🔒", "globe": "🌐", "india": "🇮🇳",
    "key": "🔑",
}

SC_MAP = {
    "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ꜰ",
    "G": "ɢ", "H": "ʜ", "I": "ɪ", "J": "ᴊ", "K": "ᴋ", "L": "ʟ",
    "M": "ᴍ", "N": "ɴ", "O": "ᴏ", "P": "ᴘ", "Q": "ǫ", "R": "ʀ",
    "S": "ꜱ", "T": "ᴛ", "U": "ᴜ", "V": "ᴠ", "W": "ᴡ", "X": "x",
    "Y": "ʏ", "Z": "ᴢ",
}
SC_REVERSE_MAP = {value: key for key, value in SC_MAP.items()}


def small_caps_text(text: str) -> str:
    return "".join(SC_MAP.get(character.upper(), character) if character.isascii() and character.isalpha() else character for character in text)


def normalize_small_caps(text: str) -> str:
    return "".join(SC_REVERSE_MAP.get(character, character) for character in text)


def small_caps_html(html: str) -> str:
    output = []
    in_tag = False
    literal_tag = None
    index = 0
    while index < len(html):
        lower_rest = html[index:].lower()
        if not in_tag and lower_rest.startswith("<code"):
            literal_tag = "code"
        elif not in_tag and lower_rest.startswith("<pre"):
            literal_tag = "pre"
        elif not in_tag and lower_rest.startswith("</code>"):
            literal_tag = None
        elif not in_tag and lower_rest.startswith("</pre>"):
            literal_tag = None
        character = html[index]
        if character == "<":
            in_tag = True
            output.append(character)
        elif character == ">":
            in_tag = False
            output.append(character)
        elif in_tag or literal_tag:
            output.append(character)
        else:
            output.append(SC_MAP.get(character.upper(), character) if character.isascii() and character.isalpha() else character)
        index += 1
    return "".join(output)


class SmallCapsBot(ExtBot):
    async def send_message(self, chat_id, text, *args, **kwargs):
        return await super().send_message(chat_id, small_caps_html(text), *args, **kwargs)

    async def edit_message_text(self, text, *args, **kwargs):
        return await super().edit_message_text(small_caps_html(text), *args, **kwargs)

DASHBOARD_ACTIONS = {
    "CHECK SERVICES", "PROFILE", "BUY CREDIT", "MINI APP",
    "GIFT CARD", "REFER & EARN", "HOW IT WORKS", "SUPPORT", "BACK",
}

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
# Telegram's HTTP client includes the bot token in request URLs. Keep those
# transport logs below INFO so credentials never land in ordinary host logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

web = Flask(__name__)
web.secret_key = os.getenv("SESSION_SECRET", os.urandom(32))
web.jinja_env.comment_start_string = "{##"
web.jinja_env.comment_end_string = "##}"


def db_connect():
    return sqlite3.connect(DB_PATH)


def load_repo_custom_services() -> list[dict]:
    if not os.path.exists(REPO_CUSTOM_SERVICES_FILE):
        return []
    try:
        with open(REPO_CUSTOM_SERVICES_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        logger.warning("Could not load repo custom services: %s", type(exc).__name__)
        return []
    rows = payload.get("services", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    clean_rows: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        detail = str(row.get("detail", "")).strip()
        api_url = str(row.get("api_url", "")).strip()
        provider_type = re.sub(r"[^a-z0-9_]", "", str(row.get("provider_type", "")).strip().lower())[:50]
        input_type = str(row.get("input_type", "number")).strip().lower()
        if input_type not in {"number", "email", "username", "url", "domain", "ip"}:
            input_type = "number"
        if len(name) < 2 or len(detail) < 5:
            continue
        if api_url and not re.match(r"^https?://", api_url, re.I):
            continue
        clean_rows.append({
            "name": name[:80],
            "detail": detail[:900],
            "provider_type": provider_type or None,
            "api_url": api_url[:700] or None,
            "input_type": input_type,
        })
    return clean_rows


def seed_repo_custom_services(db) -> None:
    now = int(time.time())
    for row in load_repo_custom_services():
        db.execute(
            """
            INSERT INTO custom_services (name, detail, provider_type, api_url, input_type, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(name) DO UPDATE SET
                detail = excluded.detail,
                provider_type = excluded.provider_type,
                api_url = excluded.api_url,
                input_type = excluded.input_type,
                enabled = 1
            """,
            (row["name"], row["detail"], row["provider_type"], row["api_url"], row["input_type"], now),
        )


def is_admin_user(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return str(user_id) in {value.strip() for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip()}


def init_db() -> None:
    with closing(db_connect()) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                banned INTEGER NOT NULL DEFAULT 0,
                credits INTEGER NOT NULL DEFAULT 0,
                referred_by INTEGER,
                referral_count INTEGER NOT NULL DEFAULT 0,
                mini_app_unlocked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                phone_suffix TEXT NOT NULL,
                searched_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                invite_url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                kind TEXT NOT NULL,
                note TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                credits INTEGER NOT NULL,
                amount_inr INTEGER NOT NULL,
                reference TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL,
                reviewed_at INTEGER,
                item_type TEXT NOT NULL DEFAULT 'credit',
                plan_name TEXT,
                amount_label TEXT
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                api_key TEXT NOT NULL UNIQUE,
                plan_name TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gift_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                credits INTEGER NOT NULL,
                used_by INTEGER,
                used_at INTEGER,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS custom_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                detail TEXT NOT NULL,
                provider_type TEXT,
                api_url TEXT,
                input_type TEXT NOT NULL DEFAULT 'number',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );
            """
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        migrations = {
            "banned": "ALTER TABLE users ADD COLUMN banned INTEGER NOT NULL DEFAULT 0",
            "first_name": "ALTER TABLE users ADD COLUMN first_name TEXT",
            "credits": "ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 0",
            "referred_by": "ALTER TABLE users ADD COLUMN referred_by INTEGER",
            "referral_count": "ALTER TABLE users ADD COLUMN referral_count INTEGER NOT NULL DEFAULT 0",
            "mini_app_unlocked": "ALTER TABLE users ADD COLUMN mini_app_unlocked INTEGER NOT NULL DEFAULT 0",
        }
        for column, statement in migrations.items():
            if column not in columns:
                db.execute(statement)
        payment_columns = {row[1] for row in db.execute("PRAGMA table_info(payment_requests)")}
        payment_migrations = {
            "item_type": "ALTER TABLE payment_requests ADD COLUMN item_type TEXT NOT NULL DEFAULT 'credit'",
            "plan_name": "ALTER TABLE payment_requests ADD COLUMN plan_name TEXT",
            "amount_label": "ALTER TABLE payment_requests ADD COLUMN amount_label TEXT",
        }
        for column, statement in payment_migrations.items():
            if column not in payment_columns:
                db.execute(statement)
        custom_columns = {row[1] for row in db.execute("PRAGMA table_info(custom_services)")}
        custom_migrations = {
            "api_url": "ALTER TABLE custom_services ADD COLUMN api_url TEXT",
            "input_type": "ALTER TABLE custom_services ADD COLUMN input_type TEXT NOT NULL DEFAULT 'number'",
        }
        for column, statement in custom_migrations.items():
            if column not in custom_columns:
                db.execute(statement)
        seed_repo_custom_services(db)
        db.commit()


def app_setting(key: str, default: str = "") -> str:
    try:
        with closing(db_connect()) as db:
            row = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:
        return default
    return row[0] if row else default


def payment_value(key: str, fallback: str = "") -> str:
    return app_setting(key, os.getenv(key, fallback).strip())


def custom_service_rows(include_disabled: bool = False):
    try:
        with closing(db_connect()) as db:
            if include_disabled:
                return db.execute("SELECT id, name, detail, provider_type, api_url, input_type, enabled, created_at FROM custom_services ORDER BY name").fetchall()
            return db.execute("SELECT id, name, detail, provider_type, api_url, input_type, enabled, created_at FROM custom_services WHERE enabled = 1 ORDER BY name").fetchall()
    except sqlite3.Error:
        return []


def premium(emoji: str, name: str = "sparkle") -> str:
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(name, "")
    if not emoji_id:
        return emoji
    entity_text = emoji if PREMIUM_EMOJI_ID else EMOJI_FALLBACKS.get(name, emoji)
    return f'<tg-emoji emoji-id="{emoji_id}">{entity_text}</tg-emoji>'


def premium_mark(name: str = "sparkle", mark: str = "◆") -> str:
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(name, "")
    if not emoji_id:
        return mark
    return f'<tg-emoji emoji-id="{emoji_id}">{mark}</tg-emoji>'


def divider() -> str:
    return "〰️" * 10


def styled_button(text: str, data: str, style: str = "primary", emoji: str = "") -> InlineKeyboardButton:
    extras = {"style": style}
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(emoji, "")
    if emoji_id:
        extras["icon_custom_emoji_id"] = emoji_id
    return InlineKeyboardButton(small_caps_text(text), callback_data=data, api_kwargs=extras)


def styled_url_button(text: str, url: str, style: str = "primary", emoji: str = "") -> InlineKeyboardButton:
    extras = {"style": style}
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(emoji, "")
    if emoji_id:
        extras["icon_custom_emoji_id"] = emoji_id
    return InlineKeyboardButton(small_caps_text(text), url=url, api_kwargs=extras)


def copy_button(text: str, value: str, style: str = "primary", emoji: str = "") -> InlineKeyboardButton:
    extras = {"style": style, "copy_text": {"text": value}}
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(emoji, "")
    if emoji_id:
        extras["icon_custom_emoji_id"] = emoji_id
    return InlineKeyboardButton(small_caps_text(text), api_kwargs=extras)


def dashboard_button(text: str, style: str, emoji: str) -> KeyboardButton:
    return KeyboardButton(
        small_caps_text(text),
        api_kwargs={"style": style, "icon_custom_emoji_id": EMOJI_IDS[emoji]},
    )


def dashboard_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [dashboard_button("CHECK SERVICES", "primary", "search"), dashboard_button("PROFILE", "success", "profile")],
            [dashboard_button("SUPPORT", "danger", "support")],
            [dashboard_button("BUY CREDIT", "primary", "buy"), dashboard_button("MINI APP", "success", "miniapp")],
            [dashboard_button("GIFT CARD", "danger", "gift"), dashboard_button("REFER & EARN", "primary", "referral")],
            [dashboard_button("HOW IT WORKS", "success", "help"), dashboard_button("BACK", "danger", "back")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Select an Annebella dashboard service",
    )


def menu() -> InlineKeyboardMarkup:
    style_cycle = ("primary", "success", "danger")
    buttons = [
        styled_button(name, f"service:{name}", style_cycle[((index // 3) + (index % 3)) % 3], "search")
        for index, name in enumerate(SERVICES)
    ]
    rows = [buttons[index:index + 3] for index in range(0, len(buttons), 3)]
    rows.append([styled_button("SEARCH SERVICE", "search_service", "success", "globe")])
    return InlineKeyboardMarkup(rows)


def canonical_api_service_name(name: str) -> str:
    clean = re.sub(r"^(ekycpro|numberchecker|proweblook|waha|wawp|whatsscale|ignorant)\s+", "", name, flags=re.I)
    clean = re.sub(r"\s+(number|phone|email|exists|avatar|business|registration)?\s*checker$", "", clean, flags=re.I).strip()
    lower = clean.lower()
    if "x twitter" in lower or lower == "twitter":
        return "X / Twitter"
    if "imessage" in lower:
        return "Apple iMessage"
    if "whatsapp" in lower:
        return "WhatsApp"
    if lower == "band":
        return "BAND"
    if lower == "hh":
        return "HeadHunter"
    return clean


def api_service_catalog():
    catalog: dict[str, dict] = {}
    for service in SERVICES:
        catalog[service.lower()] = {
            "name": service,
            "detail": f"Live Annebella checker available; send phone number; costs {CHECK_COST} credits on determined result",
            "active": True,
            "variants": [service],
        }
    for name, detail in API_DIRECTORY:
        canonical = canonical_api_service_name(name)
        key = canonical.lower()
        provider_type = indexed_provider_service_type(canonical, detail)
        if key in catalog:
            if provider_type:
                catalog[key]["variants"].append(name)
            if provider_type and not catalog[key]["active"] and len(detail) > len(catalog[key]["detail"]):
                catalog[key]["detail"] = detail
        elif provider_type:
            catalog[key] = {
                "name": canonical,
                "detail": detail,
                "active": False,
                "variants": [name],
            }
    for _service_id, name, detail, provider_type, api_url, input_type, _enabled, _created_at in custom_service_rows(False):
        canonical = canonical_api_service_name(name)
        key = canonical.lower()
        tagged_detail = f"{detail} input_type {input_type or 'number'}"
        if api_url:
            tagged_detail = f"{tagged_detail} api_url {api_url}"
        if provider_type:
            tagged_detail = f"{tagged_detail} service_type {provider_type}"
        if key in catalog:
            catalog[key]["detail"] = tagged_detail
            catalog[key]["variants"].append(name)
        else:
            catalog[key] = {
                "name": canonical,
                "detail": tagged_detail,
                "active": False,
                "variants": [name],
            }
    return list(catalog.values())


def api_service_by_index(index: int):
    catalog = api_service_catalog()
    if 0 <= index < len(catalog):
        return catalog[index]
    return None


def api_service_matches(query: str, limit: int = 25):
    query = normalize_small_caps(query).strip().lower()
    catalog = api_service_catalog()
    if not query:
        return catalog[:limit]
    terms = [term for term in re.split(r"[\s,./|+-]+", query) if term]
    exact_name_matches = [
        item for item in catalog
        if normalize_small_caps(item["name"]).strip().lower() == query
    ]
    if exact_name_matches:
        return exact_name_matches[:limit]
    matches = []
    for item in catalog:
        haystack = f"{item['name']} {item['detail']} {' '.join(item['variants'])}".lower()
        if all(term in haystack for term in terms):
            matches.append(item)
    if not matches:
        for item in catalog:
            haystack = f"{item['name']} {item['detail']} {' '.join(item['variants'])}".lower()
            if any(term in haystack for term in terms):
                matches.append(item)
    return matches[:limit]


def api_service_guidance(name: str, detail: str) -> str:
    haystack = f"{name} {detail}".lower()
    input_match = re.search(r"input_type\s+([a-z0-9_]+)", haystack)
    if input_match and input_match.group(1) in {"number", "phone", "mobile"}:
        return "Send mobile number with country code."
    if input_match and input_match.group(1) == "email":
        return "Send email address."
    if input_match and input_match.group(1) in {"username", "user"}:
        return "Send username or profile ID."
    if input_match and input_match.group(1) in {"url", "domain", "ip"}:
        return "Send URL, domain, or IP address."
    if any(word in haystack for word in {"phone registration checker", "number checker", "phone existence checker", "number verification", "phone validation", "number insight", "phoneid"}):
        return "Send phone number in international format. Real registered/non-registered output needs configured provider API access and authorized use."
    if "email registration checker" in haystack:
        return "Send email address. Real registered/non-registered output needs configured provider API access and authorized use."
    if any(word in haystack for word in {"gmail", "email", "sendgrid", "mailchimp", "mailgun", "brevo", "postmark", "klaviyo"}):
        return "Send authorized email/OAuth access; supports mailbox, message metadata, delivery or campaign lookups."
    if any(word in haystack for word in {"instagram", "facebook", "threads", "linkedin", "snapchat", "x / twitter", "tiktok", "pinterest", "reddit", "tumblr", "mastodon", "bluesky"}):
        return "Send username/profile URL or OAuth-approved account access; public profile/content lookup only."
    if any(word in haystack for word in {"discord", "telegram", "slack", "teams", "line", "viber", "messenger", "whatsapp"}):
        return "Send bot user ID, chat/server/channel ID, or authorized business/OAuth data."
    if any(word in haystack for word in {"website", "url", "domain", "whois", "dns", "safe browsing", "virustotal", "urlscan", "shodan", "abuseipdb", "ipinfo", "ipapi", "securitytrails", "builtwith", "wappalyzer"}):
        return "Send URL, domain or IP; supports status, SSL, technology, reputation or phishing/security checks."
    if any(word in haystack for word in {"payment", "pay", "stripe", "paypal", "razorpay", "paytm", "cashfree", "phonepe", "square"}):
        return "Send order/payment/transaction ID with merchant API credentials for payment status lookup."
    if any(word in haystack for word in {"shop", "amazon", "commerce", "marketplace", "seller", "storefront", "woocommerce", "shopify", "ebay", "etsy", "walmart", "flipkart"}):
        return "Send product URL/SKU/order ID/seller ID with official commerce API access."
    if any(word in haystack for word in {"finance", "stock", "crypto", "coin", "trading", "forex", "market", "exchange"}):
        return "Send symbol, coin, exchange pair or authorized account token for market/account lookup."
    if any(word in haystack for word in {"maps", "places", "weather", "travel", "flight", "booking", "expedia", "uber", "lyft"}):
        return "Send place, address, coordinates, city, route, flight or booking reference."
    if any(word in haystack for word in {"github", "gitlab", "bitbucket", "cloud", "hosting", "firebase", "supabase", "railway", "vercel", "netlify", "aws"}):
        return "Send repo/project/deployment/resource ID with authorized API credentials."
    return "Send ID, username, URL, account token or official API credential depending on service."


def api_service_input_label(name: str, detail: str) -> str:
    haystack = f"{name} {detail}".lower()
    input_match = re.search(r"input_type\s+([a-z0-9_]+)", haystack)
    if input_match and input_match.group(1) in {"number", "phone", "mobile"}:
        return "mobile number with country code"
    if input_match and input_match.group(1) == "email":
        return "email address"
    if input_match and input_match.group(1) in {"username", "user"}:
        return "username or profile ID"
    if input_match and input_match.group(1) in {"url", "domain", "ip"}:
        return "URL, domain, or IP address"
    if any(word in haystack for word in {"phone registration checker", "number checker", "phone existence checker", "number verification", "phone validation", "number insight", "phoneid"}):
        return "phone number with country code, for authorized lookup"
    if "email registration checker" in haystack:
        return "email address, for authorized lookup"
    if any(word in haystack for word in {"gmail", "email", "sendgrid", "mailchimp", "mailgun", "brevo", "postmark", "klaviyo"}):
        return "authorized email address or OAuth/API detail"
    if any(word in haystack for word in {"instagram", "facebook", "threads", "linkedin", "snapchat", "x / twitter", "tiktok", "pinterest", "reddit", "tumblr", "mastodon", "bluesky"}):
        return "username, profile link, post link, or OAuth-approved account detail"
    if any(word in haystack for word in {"discord", "telegram", "slack", "teams", "line", "viber", "messenger", "whatsapp"}):
        return "user ID, chat/channel/server ID, bot token scope, or authorized business detail"
    if any(word in haystack for word in {"website", "url", "domain", "whois", "dns", "safe browsing", "virustotal", "urlscan", "shodan", "abuseipdb", "ipinfo", "ipapi", "securitytrails", "builtwith", "wappalyzer"}):
        return "URL, domain, or IP address"
    if any(word in haystack for word in {"payment", "pay", "stripe", "paypal", "razorpay", "paytm", "cashfree", "phonepe", "square"}):
        return "order ID, payment ID, transaction ID, or merchant API detail"
    if any(word in haystack for word in {"shop", "amazon", "commerce", "marketplace", "seller", "storefront", "woocommerce", "shopify", "ebay", "etsy", "walmart", "flipkart"}):
        return "product URL, SKU, seller ID, or order ID"
    return "ID, username, URL, phone number, email, or official API detail"


def indexed_provider_service_type(name: str, detail: str) -> str | None:
    match = re.search(r"service_type\s+([a-z0-9_]+)", detail.lower())
    if match:
        return match.group(1)
    fallback = {
        "facebook": "facebook",
        "instagram": "instagram",
        "threads": "threads",
        "x / twitter": "twitter",
        "apple imessage": "apple",
        "viber": "viber",
        "zalo": "zalo",
        "band": "band",
        "goto": "goto",
        "indiatimes": "indiatimes",
        "headhunter": "hh",
        "netflix": "netflix",
        "spotify": "spotify_email",
    }
    return fallback.get(name.lower())


def api_service_cost(name: str, detail: str) -> int:
    has_custom_url = bool(re.search(r"api_url\s+https?://\S+", detail.lower()))
    return CHECK_COST if indexed_provider_service_type(name, detail) and (os.getenv("EKYCPRO_API_KEY", "").strip() or has_custom_url) else 0


def api_service_plain_input_label(name: str, detail: str) -> str:
    label = api_service_input_label(name, detail)
    if "email" in label.lower():
        return "email address"
    if "phone" in label.lower() or "number" in label.lower():
        return "mobile number with country code"
    if "url" in label.lower() or "domain" in label.lower() or "ip" in label.lower():
        return "URL, domain or IP"
    return "required lookup detail"


def api_service_select_text(name: str, detail: str) -> str:
    label = api_service_plain_input_label(name, detail)
    example = (
        "\nExample: <code>user48291@example.com</code>" if "email" in label.lower()
        else "\nExample: <code>+919876543210</code>" if "number" in label.lower() or "mobile" in label.lower()
        else ""
    )
    return (
        f"{premium('◆', 'search')} <b>{escape(name.upper())} CHECKER</b>\n{divider()}\n\n"
        f"{premium('◆', 'phone')} <b>SEND YOUR {escape(label.upper())}</b>{example}\n\n"
        f"{premium('◆', 'credits')} <b>LOOKUP CHARGE:</b> {api_service_cost(name, detail)} credits\n"
        f"{premium('◆', 'warn')} <b>NOTE:</b> Live registered/not-registered result is shown only when this service provider is connected."
    )


def api_service_input_result_text(name: str, detail: str, value: str, checker_result=None, checker_error: str | None = None, charged: int = 0) -> str:
    safe_value = escape(value[:120])
    provider_registration = any(word in f"{name} {detail}".lower() for word in {
        "phone registration checker", "email registration checker", "number checker", "phone existence checker", "osint-style account presence",
    })
    registration_blocked = any(word in f"{name} {detail}".lower() for word in {
        "gmail", "instagram", "facebook", "threads", "linkedin", "snapchat", "x / twitter", "discord", "whatsapp", "telegram", "tiktok",
    })
    if checker_error:
        status = checker_error
    elif checker_result is True:
        status = "REGISTERED"
    elif checker_result is False:
        status = "NOT REGISTERED"
    else:
        status = (
            "Provider service indexed. Add a valid provider API key in server config to return live registered/not-registered results."
            if provider_registration else
            "Official API/OAuth access required. Public account-registration checking is not available for this service."
            if registration_blocked
            else "Input accepted. This service can be integrated through its official API or configured provider."
        )
    status_icon = "check" if checker_result is True else "support" if checker_result is False else "warn" if checker_error else "check"
    return (
        f"{premium('◆', 'search')} <b>{escape(name.upper())} CHECKER</b>\n{divider()}\n\n"
        f"{premium('◆', 'profile')} <b>SUBMITTED:</b> <code>{safe_value}</code>\n"
        f"{premium('◆', 'globe')} <b>SERVICE:</b> {escape(name)}\n"
        f"{premium('◆', 'credits')} <b>LOOKUP CHARGE:</b> {charged} credits\n\n"
        f"{premium('◆', status_icon)} <b>CHECKUP STATUS:</b>\n{escape(status)}\n\n"
        f"{premium('◆', 'help')} <b>LOOKUP TYPE:</b>\n{escape(api_service_guidance(name, detail))}"
    )


def api_service_search_text(query: str = "") -> str:
    matches = api_service_matches(query)
    title = "POPULAR API SERVICE DIRECTORY" if not query.strip() else f"API SERVICE SEARCH: {escape(query[:40])}"
    lines = "\n".join(
        f"{index}. <b>{escape(name)}</b> - {escape(detail)}\n"
        f"   <i>Input:</i> {escape(api_service_guidance(name, detail))}"
        for index, (name, detail) in enumerate(matches, 1)
    ) or "No matching service found. Try words like <code>social</code>, <code>payment</code>, <code>website</code>, <code>email</code>, <code>discord</code>, or <code>google</code>."
    return (
        f"{premium('◆', 'globe')} <b>{title}</b>\n{divider()}\n\n"
        f"{premium('◆', 'search')} <b>TOTAL INDEXED:</b> {len(API_DIRECTORY)} public/API platforms\n"
        f"{premium('◆', 'check')} <b>MATCHES SHOWN:</b> {len(matches)}\n\n"
        f"{lines}\n\n"
        f"{divider()}\n"
        f"{premium('◆', 'warn')} <b>NEXT STEP:</b> If one clear service is found, bot will ask for the next input. Active phone checks still work from checker buttons."
    )


def api_service_full_list_texts() -> list[str]:
    active_names = ", ".join(escape(name) for name in SERVICES)
    indexed_lines = [f"{index:03d}. {escape(name)}" for index, (name, _) in enumerate(API_DIRECTORY, 1)]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    max_body_len = 3000
    for line in indexed_lines:
        line_len = len(line) + 1
        if current and current_len + line_len > max_body_len:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))

    messages = []
    total_parts = len(chunks)
    for part, body in enumerate(chunks, 1):
        if part == 1:
            messages.append(
                f"{premium('?', 'globe')} <b>ALL AVAILABLE SERVICES</b>\n{divider()}\n\n"
                f"{premium('?', 'check')} <b>LIVE CHECKERS:</b> {len(SERVICES)}\n"
                f"{active_names}\n\n"
                f"{premium('?', 'search')} <b>INDEXED API SERVICES:</b> {len(API_DIRECTORY)}\n"
                f"{premium('?', 'help')} <b>PART:</b> {part}/{total_parts}\n\n"
                f"{body}\n\n"
                f"{divider()}\n"
                f"{premium('?', 'phone')} Type exact service name or keyword, example: <code>gmail</code>, <code>whatsapp</code>, <code>telegram</code>."
            )
        else:
            messages.append(
                f"{premium('?', 'globe')} <b>ALL AVAILABLE SERVICES</b>\n{divider()}\n\n"
                f"{premium('?', 'help')} <b>PART:</b> {part}/{total_parts}\n\n"
                f"{body}\n\n"
                f"{divider()}\n"
                f"{premium('?', 'search')} Continue by typing any service name."
            )
    return messages


def api_service_search_text(query: str = "") -> str:
    matches = api_service_matches(query)
    title = "POPULAR SERVICE SEARCH" if not query.strip() else f"SERVICE SEARCH: {escape(query[:40])}"
    if not matches:
        lines = "No matching service found. Try <code>whatsapp</code>, <code>gmail</code>, <code>amazon</code>, <code>telegram</code>, or <code>instagram</code>."
    else:
        lines = "\n".join(
            f"{index}. <b>{escape(item['name'])}</b> - {'LIVE CHECKER' if item['active'] else 'API INDEXED'}\n"
            f"   <i>Input:</i> {escape(api_service_guidance(item['name'], item['detail']))}"
            for index, item in enumerate(matches, 1)
        )
    return (
        f"{premium('?', 'globe')} <b>{title}</b>\n{divider()}\n\n"
        f"{premium('?', 'search')} <b>TOTAL AVAILABLE:</b> {len(api_service_catalog())} clean services\n"
        f"{premium('?', 'check')} <b>MATCHES SHOWN:</b> {len(matches)}\n\n"
        f"{lines}\n\n"
        f"{divider()}\n"
        f"{premium('?', 'phone')} Type exact service name or tap the service button below."
    )


def service_page_count() -> int:
    return max(1, (len(api_service_catalog()) + SERVICE_PAGE_SIZE - 1) // SERVICE_PAGE_SIZE)


def api_service_page_text(page: int = 0) -> str:
    catalog = api_service_catalog()
    total_pages = service_page_count()
    page = max(0, min(page, total_pages - 1))
    start = page * SERVICE_PAGE_SIZE
    page_items = catalog[start:start + SERVICE_PAGE_SIZE]
    active_names = ", ".join(escape(name) for name in SERVICES)
    body = "\n".join(
        f"{start + index:03d}. {escape(item['name'])}"
        for index, item in enumerate(page_items, 1)
    )
    live_block = (
        f"{premium('?', 'check')} <b>LIVE CHECKERS:</b> {len(SERVICES)}\n{active_names}\n\n"
        if page == 0 else ""
    )
    return (
        f"{premium('?', 'globe')} <b>ALL AVAILABLE SERVICES</b>\n{divider()}\n\n"
        f"{live_block}"
        f"{premium('?', 'search')} <b>CLEAN SERVICE LIST:</b> {len(catalog)}\n"
        f"{premium('?', 'help')} <b>PAGE:</b> {page + 1}/{total_pages}\n\n"
        f"{body}\n\n"
        f"{divider()}\n"
        f"{premium('?', 'phone')} Type service name/keyword, example: <code>whatsapp</code>, <code>gmail</code>, <code>telegram</code>."
    )


def service_page_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    total_pages = service_page_count()
    page = max(0, min(page, total_pages - 1))
    rows = []
    nav = []
    if page > 0:
        nav.append(styled_button("PREVIOUS", f"services_page:{page - 1}", "primary", "back"))
    if page < total_pages - 1:
        nav.append(styled_button("NEXT", f"services_page:{page + 1}", "success", "search"))
    if nav:
        rows.append(nav)
    rows.append([styled_button("TYPE SERVICE NAME", "search_service", "primary", "search")])
    rows.append([styled_button("BACK TO CHECKERS", "main_menu", "danger", "back")])
    return InlineKeyboardMarkup(rows)


def service_search_result_text(query: str, matches: list[dict]) -> str:
    if not matches:
        return (
            f"{premium('?', 'search')} <b>SERVICE NOT FOUND</b>\n{divider()}\n\n"
            f"No clean service matched <code>{escape(query[:60])}</code>.\n\n"
            f"{premium('?', 'help')} Try a simple keyword like <code>whatsapp</code>, <code>gmail</code>, <code>amazon</code>, or <code>telegram</code>."
        )
    if len(matches) == 1:
        item = matches[0]
        return (
            f"{premium('?', 'check')} <b>SERVICE AVAILABLE</b>\n{divider()}\n\n"
            f"{premium('?', 'globe')} <b>SERVICE:</b> {escape(item['name'])}\n"
            f"{premium('?', 'search')} <b>STATUS:</b> {'LIVE CHECKER READY' if item['active'] else 'API INDEXED'}\n"
            f"{premium('?', 'phone')} <b>NEXT:</b> Tap the button below to continue."
        )
    lines = "\n".join(
        f"{index}. <b>{escape(item['name'])}</b> - {'LIVE' if item['active'] else 'API INDEXED'}"
        for index, item in enumerate(matches[:10], 1)
    )
    return (
        f"{premium('?', 'search')} <b>MULTIPLE SERVICES FOUND</b>\n{divider()}\n\n"
        f"{lines}\n\n"
        f"{premium('?', 'phone')} Tap one button below, or type a more exact service name."
    )


def service_search_result_keyboard(matches: list[dict]) -> InlineKeyboardMarkup:
    catalog = api_service_catalog()
    rows = []
    for item in matches[:10]:
        index = next((idx for idx, candidate in enumerate(catalog) if candidate["name"] == item["name"]), None)
        if index is None:
            continue
        callback = f"service:{item['name']}" if item["active"] and item["name"] in SERVICES else f"api_select:{index}"
        rows.append([styled_button(item["name"], callback, "success" if item["active"] else "primary", "search")])
    rows.append([styled_button("SEARCH AGAIN", "search_service", "success", "search")])
    rows.append([styled_button("BACK TO CHECKERS", "main_menu", "danger", "back")])
    return InlineKeyboardMarkup(rows)


def join_menu(channels, joined: list[bool]) -> InlineKeyboardMarkup:
    styles = ("primary", "success", "danger")
    buttons = [
        styled_url_button(
            f"{'JOINED' if joined[index] else 'JOIN'} — {title}", url,
            styles[index % len(styles)], "check" if joined[index] else "link",
        )
        for index, (_, title, url) in enumerate(channels)
    ]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    all_joined = bool(channels) and all(joined)
    rows.append([
        styled_button("ENTER BOT" if all_joined else "CHECK JOINED", "verify_join", "success" if all_joined else "primary", "rocket" if all_joined else "check"),
        styled_button("REFRESH", "verify_join", "primary", "refresh"),
    ])
    rows.append([styled_url_button("SUPPORT", SUPPORT_URL, "danger", "support")])
    return InlineKeyboardMarkup(rows)


def enabled_channels():
    with closing(db_connect()) as db:
        return db.execute(
            "SELECT chat_id, title, invite_url FROM channels WHERE enabled = 1 ORDER BY id"
        ).fetchall()


async def membership_status(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list[bool]:
    statuses = []
    for chat_id, _, _ in enabled_channels():
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            statuses.append(member.status in {
                ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED,
            })
        except Exception:
            logger.warning("Could not verify required channel %s", chat_id)
            statuses.append(False)
    return statuses


async def membership_ok(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return all(await membership_status(user_id, context))


def force_join_text(channels, joined: list[bool]) -> str:
    joined_count = sum(joined)
    total = len(channels)
    progress = f"{'■' * joined_count}{'□' * max(0, total - joined_count)} {joined_count}/{total}"
    missing = "\n".join(
        f"{index + 1}. {escape(title)}" for index, (_, title, _) in enumerate(channels) if not joined[index]
    ) or "NONE"
    return (
        f"{premium('◆', 'lock')} <b>FORCE JOIN REQUIRED</b>\n{divider()}\n\n"
        f"{premium('◆', 'globe')} <b>JOIN STATUS:</b> {progress}\n"
        f"{premium('◆', 'warn')} <b>MISSING CHANNELS:</b>\n{missing}\n\n"
        f"{premium('◆', 'link')} JOIN ALL REQUIRED CHANNELS TO CONTINUE.\n"
        f"{premium('◆', 'refresh')} AFTER JOINING, TAP <b>CHECK JOINED</b>."
    )


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    with closing(db_connect()) as db:
        row = db.execute("SELECT banned FROM users WHERE telegram_id = ?", (update.effective_user.id,)).fetchone()
    if row and row[0]:
        await update.effective_message.reply_text(f"{premium('◆', 'support')} <b>ACCESS SUSPENDED</b>\n\nContact support if you believe this restriction is incorrect.", parse_mode=ParseMode.HTML)
        return False
    channels = enabled_channels()
    joined = await membership_status(update.effective_user.id, context) if channels else []
    if channels and not all(joined):
        await update.effective_message.reply_text(
            force_join_text(channels, joined),
            parse_mode=ParseMode.HTML,
            reply_markup=join_menu(channels, joined),
        )
        return False
    return True


def remember_user(update: Update, referred_by: int | None = None) -> bool:
    user = update.effective_user
    now = int(time.time())
    with closing(db_connect()) as db:
        existing = db.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (user.id,)).fetchone()
        valid_referrer = None
        if not existing and referred_by and referred_by != user.id:
            valid_referrer = db.execute(
                "SELECT telegram_id FROM users WHERE telegram_id = ? AND banned = 0", (referred_by,)
            ).fetchone()
        db.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, first_seen, last_seen, credits, referred_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen
            """,
            (user.id, user.username, user.first_name, now, now, SIGNUP_CREDITS, referred_by if valid_referrer else None),
        )
        signup_recorded = db.execute(
            "SELECT 1 FROM credit_transactions WHERE telegram_id = ? AND kind = 'signup' LIMIT 1",
            (user.id,),
        ).fetchone()
        bonus_granted = not bool(signup_recorded)
        if bonus_granted:
            if existing:
                db.execute("UPDATE users SET credits = credits + ? WHERE telegram_id = ?", (SIGNUP_CREDITS, user.id))
            db.execute(
                "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'signup', 'Welcome credits', ?)",
                (user.id, SIGNUP_CREDITS, now),
            )
        if not existing:
            if valid_referrer:
                db.execute(
                    "UPDATE users SET credits = credits + ?, referral_count = referral_count + 1 WHERE telegram_id = ?",
                    (REFERRAL_CREDITS, referred_by),
                )
                db.execute(
                    "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'referral', ?, ?)",
                    (referred_by, REFERRAL_CREDITS, f"Referral reward for {user.id}", now),
                )
        db.commit()
    return bonus_granted


def user_summary(user_id: int):
    with closing(db_connect()) as db:
        return db.execute(
            "SELECT first_name, username, credits, referral_count, first_seen, mini_app_unlocked FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()


def mini_app_link(user_id: int) -> str | None:
    base_url = os.getenv(
        "MINI_APP_URL",
        os.getenv("PUBLIC_APP_URL", "https://web-production-b80e9.up.railway.app/miniapp"),
    ).strip().rstrip("/")
    if not base_url:
        return None
    token = URLSafeTimedSerializer(web.secret_key).dumps({"user_id": user_id}, salt="mini-app")
    path = "" if base_url.endswith("/miniapp") else "/miniapp"
    return f"{base_url}{path}?token={token}"


def verify_mini_app_token(token: str) -> int | None:
    try:
        payload = URLSafeTimedSerializer(web.secret_key).loads(token, salt="mini-app", max_age=86400 * 30)
        return int(payload["user_id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None


def describe_phone(number: str):
    parsed = phonenumbers.parse(number, None)
    possible = phonenumbers.is_possible_number(parsed)
    valid = phonenumbers.is_valid_number(parsed)
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    region = geocoder.description_for_number(parsed, "en") or "Unknown"
    original_carrier = carrier.name_for_number(parsed, "en") or "Unknown"
    zones = ", ".join(timezone.time_zones_for_number(parsed)) or "Unknown"
    type_names = {
        phonenumbers.PhoneNumberType.MOBILE: "Mobile",
        phonenumbers.PhoneNumberType.FIXED_LINE: "Landline",
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Landline or mobile",
        phonenumbers.PhoneNumberType.TOLL_FREE: "Toll-free",
        phonenumbers.PhoneNumberType.PREMIUM_RATE: "Premium-rate",
        phonenumbers.PhoneNumberType.VOIP: "VoIP",
        phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "Personal number",
        phonenumbers.PhoneNumberType.PAGER: "Pager",
        phonenumbers.PhoneNumberType.UAN: "UAN",
        phonenumbers.PhoneNumberType.VOICEMAIL: "Voicemail",
    }
    line_type = type_names.get(phonenumbers.number_type(parsed), "Unknown")
    return possible, valid, e164, region, original_carrier, zones, line_type


def profile_text(user_id: int) -> str:
    name, username, credits, referrals, first_seen, unlocked = user_summary(user_id)
    mini_status = "UNLOCKED" if unlocked else f"LOCKED — {max(0, MINI_APP_COST - credits)} MORE CREDITS REQUIRED"
    return (
        f"{premium('◆', 'profile')} <b>MY ANNEBELLA PROFILE</b>\n{divider()}\n\n"
        f"{premium('◆', 'name')} <b>NAME</b> : {name or 'Telegram User'}\n"
        f"{premium('◆', 'link')} <b>USERNAME</b> : {'@' + username if username else 'Not connected'}\n"
        f"{premium('◆', 'id')} <b>TELEGRAM ID</b> : <code>{user_id}</code>\n"
        f"{premium('◆', 'joined')} <b>JOINED ON</b> : {time.strftime('%d %B %Y', time.localtime(first_seen))}\n"
        f"{divider()}\n\n"
        f"{premium('◆', 'lightning')} <b>CHECKER ACCESS</b>\nREADY — {CHECK_COST} credits per determined lookup\n\n"
        f"{premium('◆', 'miniapp')} <b>MINI APP ACCESS</b>\n{mini_status}\n\n"
        f"{premium('◆', 'check')} <b>ACCOUNT STATUS</b>\nACTIVE — FORCE-JOIN VERIFIED\n"
        f"{divider()}\n\n"
        f"{premium('◆', 'referral')} <b>TOTAL REFERRALS</b> : {referrals}\n"
        f"{premium('◆', 'credits')} <b>AVAILABLE CREDITS</b> : {credits}\n\n"
        f"{premium('◆', 'refresh')} Referral rewards, gift cards and approved payments are added automatically."
    )


def referral_text(user_id: int, bot_username: str) -> tuple[str, str]:
    row = user_summary(user_id)
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    text = (
        f"{premium('◆', 'referral')} <b>ANNEBELLA REFER & EARN</b>\n{divider()}\n\n"
        f"{premium('◆', 'credits')} <b>REWARD PER REFERRAL</b> : {REFERRAL_CREDITS} CREDITS\n\n"
        f"{premium('◆', 'trophy')} <b>SUCCESSFUL REFERRALS</b> : {row[3]}\n"
        f"{premium('◆', 'money')} <b>TOTAL EARNINGS</b> : {row[3] * REFERRAL_CREDITS} CREDITS\n"
        f"{divider()}\n\n"
        f"{premium('◆', 'link')} <b>YOUR PERSONAL INVITATION LINK</b>\n<code>{link}</code>\n\n"
        f"{premium('◆', 'history')} Share the link with genuine new users. Their membership must be verified before your reward is released.\n"
        f"{divider()}\n\n"
        f"{premium('◆', 'warn')} <b>FAIR-USE POLICY</b>\nSelf-referrals, duplicate accounts and members who previously started the bot do not qualify. Eligible rewards are credited automatically."
    )
    return text, link


def welcome_text(first_name: str, credits: int) -> str:
    return (
        f"{premium('◆', 'lightning')} <b>ANNEBELLA CHECKER BOT</b> {premium('◆', 'sparkle')}\n"
        f"{divider()}\n\n"
        f"{premium('◆', 'sparkle')} <b>WELCOME, {escape(first_name or 'MEMBER')}!</b>\n\n"
        f"{premium('◆', 'search')} <b>CHECK APP REGISTRATION STATUS</b>\n"
        "<i>Professional multi-service mobile-number intelligence with clear, credit-protected results.</i>\n\n"
        f"{divider()}\n\n"
        f"{premium('◆', 'fire')} <b>WHY ANNEBELLA?</b>\n\n"
        f"{premium('◆', 'globe')} 18 SUPPORTED APPLICATION SERVICES\n"
        f"{premium('◆', 'lightning')} LIVE AUTHORIZED PROVIDER LOOKUPS\n"
        f"{premium('◆', 'check')} REGISTERED / NOT REGISTERED RESULTS\n"
        f"{premium('◆', 'lock')} MASKED NUMBERS AND SECURE HISTORY\n"
        f"{premium('◆', 'gift')} START FREE — NO CARD REQUIRED\n\n"
        f"{divider()}\n\n"
        f"{premium('◆', 'credits')} <b>WELCOME CREDIT BALANCE</b>\n"
        f"{credits} CREDITS AVAILABLE IN YOUR ACCOUNT.\n\n"
        f"{premium('◆', 'money')} <b>CREDITS PLAN</b>\n"
        f"{premium('◆', 'search')} DETERMINED CHECK → <b>{CHECK_COST} CREDITS</b>\n"
        f"{premium('◆', 'referral')} REFER A FRIEND → <b>{REFERRAL_CREDITS} CREDITS</b>\n"
        f"{premium('◆', 'miniapp')} MINI APP UNLOCK → <b>{MINI_APP_COST} CREDITS</b>\n\n"
        f"{divider()}\n\n"
        f"{premium('◆', 'rocket')} <i>CHOOSE AN OPTION FROM THE DASHBOARD BELOW.</i>"
    )


def verified_text() -> str:
    return (
        f"{premium('◆', 'check')} <b>FORCE JOIN VERIFIED</b>\n{divider()}\n\n"
        f"{premium('◆', 'rocket')} ALL REQUIRED CHANNELS JOINED.\n"
        f"{premium('◆', 'lightning')} YOUR ANNEBELLA BOT ACCESS IS NOW UNLOCKED."
    )


async def pin_private_welcome(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pin the welcome card in a private chat without blocking the start flow."""
    if not message or not message.chat or message.chat.type != ChatType.PRIVATE:
        return
    try:
        await context.bot.pin_chat_message(
            chat_id=message.chat_id,
            message_id=message.message_id,
            disable_notification=True,
        )
    except Exception as exc:
        logger.warning("Could not pin private welcome for chat %s: %s", message.chat_id, type(exc).__name__)


async def cleanup_pin_service_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove Telegram's automatic 'pinned a message' notice in private chats."""
    message = update.effective_message
    if not message or not message.pinned_message or message.chat.type != ChatType.PRIVATE:
        return
    try:
        await context.bot.delete_message(chat_id=message.chat_id, message_id=message.message_id)
    except Exception as exc:
        logger.info("Could not delete private pin notice for chat %s: %s", message.chat_id, type(exc).__name__)


def buy_packages_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [styled_button("100 CREDITS", "buy_100", "success", "credits"), styled_button("500 CREDITS", "buy_500", "primary", "credits")],
        [styled_button("1000 CREDITS", "buy_1000", "success", "buy"), styled_button("5000 CREDITS", "buy_5000", "primary", "buy")],
        [styled_button("CUSTOM PACKAGE", "buy_custom", "danger", "buy")],
        [styled_button("BACK", "buy", "danger", "back")],
    ])


def buy_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [styled_button("API ACCESS", "buy_api_menu", "success", "globe"), styled_button("CREDIT BALANCE", "buy_credit_menu", "primary", "credits")],
        [styled_button("SUPPORT", "support", "danger", "support")],
    ])


def api_packages_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [styled_button("WEEKLY API - $100", "api_weekly", "success", "globe")],
        [styled_button("MONTHLY API - $250", "api_monthly", "primary", "globe")],
        [styled_button("YEARLY API - $900", "api_yearly", "danger", "globe")],
        [styled_button("BACK", "buy", "danger", "back")],
    ])


def payment_qr_url(credits: int, price: int | None) -> str:
    note = f"Annebella {credits} Credits" if credits else "Annebella API Access"
    params = {"pa": payment_value("PAYMENT_UPI_ID", "gauravpayout@fam"), "pn": "Annebella", "cu": "INR", "tn": note}
    if price is not None:
        params["am"] = str(price)
    payment_uri = "upi://pay?" + urlencode(params)
    return "https://api.qrserver.com/v1/create-qr-code/?" + urlencode({"size": "320x320", "data": payment_uri})


def package_title(package: dict) -> str:
    if package.get("item_type") == "api":
        return package["plan"]
    return f"{package['credits']} CREDITS"


def package_price_text(package: dict) -> str:
    price = package.get("price")
    if price is None:
        return "Manually confirmed amount"
    if package.get("currency") == "USD":
        return f"${price}"
    return f"₹{price}"


def package_amount_inr(package: dict) -> int:
    return int(package.get("price") or 0) if package.get("currency") == "INR" else 0


def package_amount_label(package: dict) -> str:
    return package_price_text(package)


def payment_review_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        styled_button("APPROVE", f"adminpay:approve:{payment_id}", "success", "check"),
        styled_button("DECLINE", f"adminpay:reject:{payment_id}", "danger", "warn"),
    ]])


def buy_choice_text() -> str:
    return (
        f"{premium('◆', 'buy')} <b>ANNEBELLA STORE</b>\n{divider()}\n\n"
        f"{premium('◆', 'globe')} <b>API ACCESS</b>\n"
        "Buy weekly, monthly, or yearly API access for your own tools/projects.\n\n"
        f"{premium('◆', 'credits')} <b>CREDIT BALANCE</b>\n"
        "Buy normal checker credits for Telegram and Mini App lookups.\n\n"
        f"{premium('◆', 'warn')} <b>SECURITY:</b> Never share OTP, UPI PIN, wallet seed phrase, or account password."
    )


def credit_store_text() -> str:
    return (
        f"{premium('◆', 'credits')} <b>ANNEBELLA CREDIT STORE</b>\n{divider()}\n\n"
        f"{premium('◆', 'credits')} 100 credits - ₹49\n"
        f"{premium('◆', 'credits')} 500 credits - ₹199\n"
        f"{premium('◆', 'credits')} 1000 credits - ₹349\n"
        f"{premium('◆', 'credits')} 5000 credits - ₹999\n\n"
        f"{premium('◆', 'upi')} Select UPI for a scannable payment QR.\n"
        f"{premium('◆', 'usdt')} Select USDT for copy-ready Binance and network addresses.\n\n"
        f"{premium('◆', 'check')} After payment, send transaction reference or screenshot. Admin approval adds credits."
    )


def api_store_text() -> str:
    return (
        f"{premium('◆', 'globe')} <b>ANNEBELLA CHECKER API ACCESS</b>\n{divider()}\n\n"
        f"{premium('◆', 'lightning')} <b>WEEKLY:</b> $100 - 7 days access\n"
        f"{premium('◆', 'star')} <b>MONTHLY:</b> $250 - 30 days access\n"
        f"{premium('◆', 'trophy')} <b>YEARLY:</b> $900 - 365 days access\n\n"
        f"{premium('◆', 'check')} After approval, the bot generates your personal API key automatically.\n"
        f"{premium('◆', 'credits')} Determined API lookups still use your checker credits at <b>{CHECK_COST} credits/check</b>.\n\n"
        f"{premium('◆', 'link')} <b>ENDPOINTS:</b>\n"
        f"<code>{API_BASE_URL}/api/v1/me</code>\n"
        f"<code>{API_BASE_URL}/api/v1/check</code>"
    )


def usdt_payment_keyboard() -> InlineKeyboardMarkup:
    binance_id = payment_value("USDT_BINANCE_ID", "1114491025")
    bep20 = payment_value("USDT_BEP20_ADDRESS", "0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f")
    trc20 = payment_value("USDT_TRC20_ADDRESS", "TDfzW7sn7Hut3uQr6Gnk6TyVN2aG6UoUEn")
    erc20 = payment_value("USDT_ERC20_ADDRESS", "0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f")
    return InlineKeyboardMarkup([
        [copy_button("COPY BINANCE ID", binance_id, "success", "usdt"), copy_button("COPY TRC20", trc20, "primary", "usdt")],
        [copy_button("COPY BEP20", bep20, "success", "usdt"), copy_button("COPY ERC20", erc20, "danger", "usdt")],
    ])


async def send_payment_methods(message, package: dict) -> None:
    await message.reply_text(
        f"{premium('◆', 'payment')} <b>SELECT PAYMENT METHOD</b>\n{divider()}\n\n"
        f"{premium('◆', 'credits')} <b>PACKAGE:</b> {escape(package_title(package))}\n"
        f"{premium('◆', 'money')} <b>PAYABLE AMOUNT:</b> {escape(package_price_text(package))}\n\n"
        f"{premium('◆', 'upi')} Choose UPI for a payment QR.\n"
        f"{premium('◆', 'usdt')} Choose USDT for copy-ready wallet details.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            styled_button("UPI PAYMENT", "paymethod_upi", "success", "upi"),
            styled_button("USDT PAYMENT", "paymethod_usdt", "primary", "usdt"),
        ]]),
    )


def insert_payment_request(user_id: int, package: dict, reference: str) -> int:
    with closing(db_connect()) as db:
        cursor = db.execute(
            """
            INSERT INTO payment_requests
                (telegram_id, credits, amount_inr, reference, created_at, item_type, plan_name, amount_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                int(package.get("credits", 0)),
                package_amount_inr(package),
                reference,
                int(time.time()),
                package.get("item_type", "credit"),
                package.get("plan"),
                package_amount_label(package),
            ),
        )
        request_id = cursor.lastrowid
        db.commit()
        return int(request_id)


def telegram_user_label(user) -> str:
    if not user:
        return "Telegram User"
    username = f"@{user.username}" if getattr(user, "username", None) else "No username"
    first_name = getattr(user, "first_name", None) or "Telegram User"
    return f"{first_name} ({username})"


def payment_request_text(payment_id: int, user_id: int, package: dict, reference: str, user_label: str = "Telegram User") -> str:
    return (
        f"{premium('◆', 'payment')} <b>NEW PAYMENT REQUEST #{payment_id}</b>\n{divider()}\n\n"
        f"{premium('◆', 'profile')} <b>USER:</b> {escape(user_label)}\n"
        f"{premium('◆', 'id')} <b>TELEGRAM ID:</b> <code>{user_id}</code>\n"
        f"{premium('◆', 'buy')} <b>TYPE:</b> {escape(package.get('item_type', 'credit').upper())}\n"
        f"{premium('◆', 'credits')} <b>PACKAGE:</b> {escape(package_title(package))}\n"
        f"{premium('◆', 'money')} <b>AMOUNT:</b> {escape(package_price_text(package))}\n"
        f"{premium('◆', 'history')} <b>REFERENCE:</b> <code>{escape(reference[:900])}</code>\n\n"
        f"{premium('◆', 'warn')} Review proof carefully before approving."
    )


async def notify_admin_payment_request(context: ContextTypes.DEFAULT_TYPE, payment_id: int, user_id: int, package: dict, reference: str, user_label: str = "Telegram User") -> None:
    for admin_id in {value.strip() for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip().isdigit()}:
        try:
            await context.bot.send_message(
                int(admin_id),
                payment_request_text(payment_id, user_id, package, reference, user_label),
                parse_mode=ParseMode.HTML,
                reply_markup=payment_review_keyboard(payment_id),
            )
        except Exception:
            logger.info("Could not deliver payment approval card to admin %s", admin_id)


def issue_api_key(db, user_id: int, plan_name: str | None) -> tuple[str, int]:
    plan = next((value for value in API_PLANS.values() if value["plan"] == plan_name), API_PLANS["api_monthly"])
    now = int(time.time())
    api_key = "ABAPI_" + secrets.token_urlsafe(24)
    expires_at = now + int(plan["duration_days"]) * 86400
    db.execute("UPDATE api_keys SET active = 0 WHERE telegram_id = ?", (user_id,))
    db.execute(
        "INSERT INTO api_keys (telegram_id, api_key, plan_name, expires_at, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
        (user_id, api_key, plan["plan"], expires_at, now),
    )
    return api_key, expires_at


def review_payment_record(payment_id: int, action: str):
    if action not in {"approve", "reject"}:
        return None
    with closing(db_connect()) as db:
        payment = db.execute(
            "SELECT telegram_id, credits, status, item_type, plan_name, amount_label FROM payment_requests WHERE id = ?",
            (payment_id,),
        ).fetchone()
        if not payment or payment[2] != "pending":
            return None
        user_id, credits, _status, item_type, plan_name, amount_label = payment
        status = "approved" if action == "approve" else "rejected"
        db.execute("UPDATE payment_requests SET status = ?, reviewed_at = ? WHERE id = ?", (status, int(time.time()), payment_id))
        api_key = None
        expires_at = None
        if action == "approve":
            if item_type == "api":
                api_key, expires_at = issue_api_key(db, user_id, plan_name)
            else:
                db.execute("UPDATE users SET credits = credits + ? WHERE telegram_id = ?", (credits, user_id))
                db.execute(
                    "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'purchase', ?, ?)",
                    (user_id, credits, f"Approved payment #{payment_id}", int(time.time())),
                )
        db.commit()
    return {
        "user_id": user_id,
        "credits": credits,
        "status": status,
        "item_type": item_type,
        "plan_name": plan_name,
        "amount_label": amount_label,
        "api_key": api_key,
        "expires_at": expires_at,
    }


def review_user_message(payment_id: int, result: dict, approved: bool) -> str:
    if approved and result["item_type"] == "api":
        expires = time.strftime("%d %b %Y", time.localtime(result["expires_at"]))
        return (
            f"{premium('◆', 'check')} <b>API ACCESS APPROVED</b>\n{divider()}\n\n"
            f"{premium('◆', 'globe')} <b>PLAN:</b> {escape(result['plan_name'] or 'API ACCESS')}\n"
            f"{premium('◆', 'history')} <b>VALID UNTIL:</b> {expires}\n\n"
            f"{premium('◆', 'key')} <b>YOUR API KEY:</b>\n<code>{escape(result['api_key'])}</code>\n\n"
            f"{premium('◆', 'link')} <b>BASE URL:</b> <code>{escape(API_BASE_URL)}</code>\n"
            f"{premium('◆', 'search')} <b>CHECK ENDPOINT:</b> <code>POST /api/v1/check</code>\n\n"
            f"{premium('◆', 'warn')} Keep this key private. Determined checks deduct <b>{CHECK_COST} credits</b> from your bot balance."
        )
    if approved:
        return (
            f"{premium('◆', 'check')} <b>PAYMENT APPROVED</b>\n{divider()}\n\n"
            f"{premium('◆', 'credits')} <b>{result['credits']} credits</b> were added to your Annebella Checker account.\n"
            f"{premium('◆', 'profile')} Open Profile to view the latest balance."
        )
    return (
        f"{premium('◆', 'warn')} <b>PAYMENT NOT APPROVED</b>\n{divider()}\n\n"
        f"Request <b>#{payment_id}</b> could not be verified. Please contact support with the correct transaction reference or clear payment screenshot."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    referred_by = None
    if context.args and context.args[0].startswith("ref_"):
        value = context.args[0][4:]
        referred_by = int(value) if value.isdigit() else None
    context.user_data["pending_referrer"] = referred_by
    if not await gate(update, context):
        return
    is_new = remember_user(update, context.user_data.pop("pending_referrer", None))
    if is_new and referred_by and referred_by != update.effective_user.id:
        try:
            await context.bot.send_message(
                referred_by,
                f"{premium('◆', 'referral')} <b>REFERRAL REWARD CREDITED</b>\n{divider()}\n\n"
                f"A new user joined through your link.\n\n"
                f"{premium('◆', 'credits')} <b>{REFERRAL_CREDITS} credits</b> have been added to your Annebella account.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.info("Could not deliver referral notification to %s", referred_by)
    context.user_data.pop("service", None)
    credits = user_summary(update.effective_user.id)[2]
    welcome_message = await update.message.reply_text(
        welcome_text(update.effective_user.first_name, credits),
        parse_mode=ParseMode.HTML,
        reply_markup=dashboard_keyboard(),
    )
    await pin_private_welcome(welcome_message, context)
    await update.message.reply_text(
        verified_text(),
        parse_mode=ParseMode.HTML,
    )
    await update.message.reply_text(
        f"{premium('◆', 'lightning')} <b>BOT READY! USE THE DASHBOARD BUTTONS BELOW.</b>",
        parse_mode=ParseMode.HTML,
    )
    launch_action = context.args[0] if context.args and context.args[0] in {"check", "buy_credit", "support"} else None
    if launch_action == "check":
        await update.message.reply_text(
            f"{premium('◆', 'search')} <b>CHECKER SERVICE DIRECTORY</b>\n{divider()}\n\nSelect an application below. Each determined lookup costs <b>{CHECK_COST} credits</b>.",
            parse_mode=ParseMode.HTML, reply_markup=menu(),
        )
    elif launch_action == "buy_credit":
        await update.message.reply_text(
            buy_choice_text(),
            parse_mode=ParseMode.HTML, reply_markup=buy_type_keyboard(),
        )
    elif launch_action == "support":
        context.user_data["flow"] = "support"
        await update.message.reply_text(
            f"{premium('◆', 'support')} <b>ANNEBELLA PRIORITY SUPPORT</b>\n{divider()}\n\nSend one complete message describing the affected service, approximate time and displayed error.",
            parse_mode=ParseMode.HTML,
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await gate(update, context):
        return
    await update.message.reply_text(
        f"{premium('◆', 'help')} <b>HOW TO USE</b>\n\n"
        "<b>1.</b> Send /start\n<b>2.</b> Choose CHECK SERVICES\n<b>3.</b> Select an inline application\n<b>4.</b> Send a number with country code\n"
        "Example: <code>+919876543210</code>\n\n"
        "This bot validates input and reports only data available through configured, "
        "authorized integrations. It does not bypass OTPs or expose private account data.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[styled_button("MAIN MENU", "main_menu", "primary", "home")]]),
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    configured = {value.strip() for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip()}
    if str(update.effective_user.id) not in configured:
        await update.message.reply_text(f"{premium('◆', 'support')} <b>ADMINISTRATOR ACCESS REQUIRED</b>", parse_mode=ParseMode.HTML)
        return

    with closing(db_connect()) as db:
        users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        searches = db.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    await update.message.reply_text(
        f"ANNEBELLA BOT STATISTICS\n\nActive Users: {users}\nTotal Searches: {searches}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await gate(update, context):
        return
    remember_user(update)
    text = update.message.text.strip()
    dashboard_action = normalize_small_caps(text).upper()

    if dashboard_action in DASHBOARD_ACTIONS:
        text = dashboard_action
        context.user_data.pop("flow", None)
        context.user_data.pop("service", None)
        if text == "CHECK SERVICES":
            await update.message.reply_text(
                f"{premium('◆', 'search')} <b>CHECKER SERVICE DIRECTORY</b>\n\n"
                f"Select an application below. Each determined lookup costs <b>{CHECK_COST} credits</b>.\n\n"
                f"{premium('◆', 'globe')} Need another platform? Tap <b>SEARCH SERVICE</b> to explore {len(api_service_catalog())} supported services.",
                parse_mode=ParseMode.HTML, reply_markup=menu(),
            )
        elif text == "PROFILE":
            await update.message.reply_text(profile_text(update.effective_user.id), parse_mode=ParseMode.HTML, reply_markup=dashboard_keyboard())
        elif text == "REFER & EARN":
            username = BOT_USERNAME or (await context.bot.get_me()).username
            referral_message, link = referral_text(update.effective_user.id, username)
            await update.message.reply_text(
                referral_message, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[styled_url_button("SHARE PERSONAL LINK", f"https://t.me/share/url?url={link}", "success", "referral")]]),
            )
        elif text == "BUY CREDIT":
            await update.message.reply_text(
                buy_choice_text(),
                parse_mode=ParseMode.HTML, reply_markup=buy_type_keyboard(),
            )
        elif text == "MINI APP":
            row = user_summary(update.effective_user.id)
            if row[5]:
                link = mini_app_link(update.effective_user.id)
                markup = InlineKeyboardMarkup([[styled_url_button("OPEN ANNEBELLA MINI APP", link, "success", "miniapp")]]) if link else None
                message = "Mini App access is active. Use the secure launch button below." if link else "Mini App access is active, but MINI_APP_URL is not configured on the host."
            else:
                markup = InlineKeyboardMarkup([[styled_button(f"UNLOCK FOR {MINI_APP_COST} CREDITS", "mini_unlock", "success", "miniapp")]])
                message = f"Permanent Mini App access requires <b>{MINI_APP_COST} credits</b>. Your current balance is <b>{row[2]}</b>. Unlocking deducts the credits once."
            await update.message.reply_text(
                f"{premium('◆', 'miniapp')} <b>ANNEBELLA CHECKER MINI APP</b>\n\n{message}\n\n"
                "The Mini App provides a mobile web dashboard with account balance, checker directory, referral status, and access information.",
                parse_mode=ParseMode.HTML, reply_markup=markup,
            )
        elif text == "BACK":
            await update.message.reply_text(
                f"{premium('◆', 'back')} <b>ANNEBELLA MAIN DASHBOARD</b>\n\nSelect an account action below or open Check Services to start a lookup.",
                parse_mode=ParseMode.HTML,
                reply_markup=dashboard_keyboard(),
            )
        elif text == "GIFT CARD":
            context.user_data["flow"] = "gift_card"
            await update.message.reply_text(
                f"{premium('◆', 'gift')} <b>REDEEM ANNEBELLA GIFT CARD</b>\n\n"
                "Send your gift-card code exactly as issued. Every card can be redeemed once and its credit value is added immediately after validation.\n\n"
                "Example: <code>ANNE-AB12-CD34</code>", parse_mode=ParseMode.HTML,
            )
        elif text == "HOW IT WORKS":
            await update.message.reply_text(
                f"{premium('◆', 'help')} <b>HOW ANNEBELLA CHECKER WORKS</b>\n{divider()}\n\n"
                f"{premium('◆', 'lightning')} <b>1 — ACTIVATE YOUR ACCOUNT</b>\nJoin every required channel and verify membership. New members receive <b>{SIGNUP_CREDITS} welcome credits</b> automatically.\n\n"
                f"{premium('◆', 'search')} <b>2 — SELECT A CHECKER</b>\nOpen Check Services and choose the required application from the inline checker directory.\n\n"
                f"{premium('◆', 'phone')} <b>3 — SUBMIT THE NUMBER</b>\nSend an authorized mobile number with country code, for example <code>+919876543210</code>.\n\n"
                f"{premium('◆', 'check')} <b>4 — RECEIVE THE RESULT</b>\nThe provider returns Registered or Not Registered. Only a determined result costs <b>{CHECK_COST} credits</b>; provider errors cost zero.\n"
                f"{divider()}\n\n"
                f"{premium('◆', 'referral')} <b>REFER & EARN</b>\nReceive <b>{REFERRAL_CREDITS} credits</b> for each genuine new member who joins through your personal referral link.\n\n"
                f"{premium('◆', 'gift')} <b>GIFT CARDS & PAYMENTS</b>\nRedeem administrator-issued cards or purchase a verified UPI/USDT credit package.\n\n"
                f"{premium('◆', 'miniapp')} <b>MINI APP ACCESS</b>\nUnlock permanent Mini App access once your balance reaches <b>{MINI_APP_COST} credits</b>.\n"
                f"{divider()}\n\n"
                f"{premium('◆', 'support')} <b>RESPONSIBLE USE</b>\nCheck only numbers you own or are explicitly authorized to verify.",
                parse_mode=ParseMode.HTML,
            )
        elif text == "SUPPORT":
            context.user_data["flow"] = "support"
            await update.message.reply_text(
                f"{premium('◆', 'support')} <b>ANNEBELLA PRIORITY SUPPORT</b>\n{divider()}\n\n"
                "Send one complete message containing the affected checker, approximate time, expected result, and displayed error. "
                "For payment assistance include only the transaction reference—never send an OTP, PIN, password, or wallet recovery phrase.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[styled_url_button("CONTACT DEVELOPER", SUPPORT_URL, "danger", "support")]]),
            )
        return

    flow = context.user_data.get("flow")
    if flow == "gift_card":
        code = text.upper().strip()
        with closing(db_connect()) as db:
            card = db.execute("SELECT id, credits, used_by FROM gift_cards WHERE code = ?", (code,)).fetchone()
            if not card:
                await update.message.reply_text(f"{premium('◆', 'gift')} <b>GIFT CARD NOT RECOGNIZED</b>\n\nConfirm the code and try again.", parse_mode=ParseMode.HTML)
                return
            if card[2] is not None:
                await update.message.reply_text(f"{premium('◆', 'gift')} <b>GIFT CARD ALREADY REDEEMED</b>\n\nEach card is valid for one account only.", parse_mode=ParseMode.HTML)
                return
            now = int(time.time())
            claimed = db.execute("UPDATE gift_cards SET used_by = ?, used_at = ? WHERE id = ? AND used_by IS NULL", (update.effective_user.id, now, card[0]))
            if claimed.rowcount != 1:
                db.rollback()
                await update.message.reply_text(f"{premium('◆', 'gift')} <b>GIFT CARD ALREADY REDEEMED</b>", parse_mode=ParseMode.HTML)
                return
            db.execute("UPDATE users SET credits = credits + ? WHERE telegram_id = ?", (card[1], update.effective_user.id))
            db.execute("INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'gift_card', ?, ?)", (update.effective_user.id, card[1], code, now))
            db.commit()
        context.user_data.pop("flow", None)
        await update.message.reply_text(f"{premium('◆', 'check')} <b>GIFT CARD REDEEMED</b>\n\n<b>{card[1]} credits</b> were added successfully.", parse_mode=ParseMode.HTML, reply_markup=dashboard_keyboard())
        return
    if flow == "service_search":
        matches = api_service_matches(text)
        if len(matches) == 1:
            await update.message.reply_text(
                service_search_result_text(text, matches),
                parse_mode=ParseMode.HTML,
                reply_markup=service_search_result_keyboard(matches),
            )
            return
        await update.message.reply_text(
            service_search_result_text(text, matches),
            parse_mode=ParseMode.HTML,
            reply_markup=service_search_result_keyboard(matches),
        )
        return
    if flow == "api_service_input":
        selected = context.user_data.get("api_service") or {}
        name, detail = selected.get("name"), selected.get("detail")
        if not name or not detail:
            context.user_data["flow"] = "service_search"
            await update.message.reply_text(
                f"{premium('◆', 'search')} <b>SEARCH SERVICE</b>\n\nSend the application/service name again.",
                parse_mode=ParseMode.HTML,
            )
            return
        cost = api_service_cost(name, detail)
        if cost:
            with closing(db_connect()) as db:
                credits = db.execute("SELECT credits FROM users WHERE telegram_id = ?", (update.effective_user.id,)).fetchone()[0]
            if credits < cost:
                await update.message.reply_text(
                    f"{premium('◆', 'credits')} <b>INSUFFICIENT CREDITS</b>\n\nThis lookup requires {cost} credits. Purchase credits or invite friends to continue.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[styled_button("BUY CREDITS", "buy", "success", "buy"), styled_button("REFER & EARN", "referral", "primary", "referral")]]),
                )
                return
        checker_result, checker_error = await indexed_provider_lookup(name, detail, text)
        charged = 0
        if cost and checker_error is None and checker_result is not None:
            with closing(db_connect()) as db:
                debited = db.execute(
                    "UPDATE users SET credits = credits - ? WHERE telegram_id = ? AND credits >= ?",
                    (cost, update.effective_user.id, cost),
                )
                if debited.rowcount == 1:
                    db.execute(
                        "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'lookup', ?, ?)",
                        (update.effective_user.id, -cost, name, int(time.time())),
                    )
                    db.commit()
                    charged = cost
                else:
                    db.rollback()
                    checker_result, checker_error = None, "Account balance changed; please try again"
        context.user_data.pop("flow", None)
        context.user_data.pop("api_service", None)
        await update.message.reply_text(
            api_service_input_result_text(name, detail, text, checker_result, checker_error, charged),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [styled_button("SEARCH ANOTHER SERVICE", "search_service", "success", "search")],
                [styled_button("CHECKER DIRECTORY", "main_menu", "primary", "search")],
            ]),
        )
        return
    if flow == "custom_credit":
        digits = re.sub(r"\D", "", text)
        if not digits or int(digits) < 10:
            await update.message.reply_text("Enter a custom package of at least 10 credits.")
            return
        context.user_data["payment"] = {"item_type": "credit", "credits": int(digits), "price": None, "currency": "INR"}
        context.user_data["flow"] = "payment_method"
        await send_payment_methods(update.effective_message, context.user_data["payment"])
        return
    if flow == "payment_reference":
        package = context.user_data.get("payment")
        if not package or len(text) < 4 or len(text) > 120:
            await update.message.reply_text(
                f"{premium('◆', 'buy')} <b>INVALID PAYMENT SUBMISSION</b>\n\nSend the transaction reference shown by your payment application, or upload the payment screenshot.",
                parse_mode=ParseMode.HTML
            )
            return
        reference = f"{package.get('method', 'manual').upper()}: {text.strip()}"
        request_id = insert_payment_request(update.effective_user.id, package, reference)
        await notify_admin_payment_request(
            context,
            request_id,
            update.effective_user.id,
            package,
            reference,
            telegram_user_label(update.effective_user),
        )
        context.user_data.pop("flow", None)
        context.user_data.pop("payment", None)
        await update.message.reply_text(
            f"{premium('◆', 'check')} <b>PAYMENT REQUEST RECEIVED</b>\n\n"
            f"Request: <b>#{request_id}</b>\nPackage: <b>{escape(package_title(package))}</b>\nReference: <code>{escape(reference)}</code>\n\n"
            "An administrator will verify the payment. Your order activates only after approval.",
            parse_mode=ParseMode.HTML, reply_markup=menu(),
        )
        return
    if flow == "support":
        if len(text) < 5:
            await update.message.reply_text("Please describe the issue in at least five characters.")
            return
        with closing(db_connect()) as db:
            db.execute(
                "INSERT INTO support_tickets (telegram_id, message, created_at) VALUES (?, ?, ?)",
                (update.effective_user.id, text[:2000], int(time.time())),
            )
            db.commit()
        context.user_data.pop("flow", None)
        for admin_id in {value.strip() for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip().isdigit()}:
            try:
                await context.bot.send_message(
                    int(admin_id),
                    f"{premium('◆', 'support')} <b>NEW SUPPORT TICKET</b>\n\nUser: <code>{update.effective_user.id}</code>\nMessage:\n{text[:1500]}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                logger.info("Could not deliver support alert to admin %s", admin_id)
        await update.message.reply_text(
            f"{premium('◆', 'check')} <b>SUPPORT REQUEST SUBMITTED</b>\n\n"
            "Your ticket has been recorded for administrator review. For urgent assistance, use the Support button.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_url_button("Open Developer Support", SUPPORT_URL, "danger", "support")], [styled_button("Back to Menu", "main_menu", "primary", "back")]]),
        )
        return

    service = context.user_data.get("service")
    if not service:
        await update.message.reply_text("Please select a checker first.", reply_markup=menu())
        return

    normalized = re.sub(r"[\s()-]", "", text)
    if not PHONE_RE.fullmatch(normalized):
        await update.message.reply_text(
            f"{premium('◆', 'support')} <b>INVALID MOBILE NUMBER</b>\n\nSend 8–15 digits, optionally starting with +.", parse_mode=ParseMode.HTML
        )
        return

    now = time.monotonic()
    previous = context.user_data.get("last_search", 0.0)
    if now - previous < RATE_LIMIT_SECONDS:
        await update.message.reply_text("Please wait a moment before another search.")
        return
    context.user_data["last_search"] = now

    with closing(db_connect()) as db:
        credits = db.execute("SELECT credits FROM users WHERE telegram_id = ?", (update.effective_user.id,)).fetchone()[0]
    if credits < CHECK_COST:
        await update.message.reply_text(
            f"{premium('◆', 'credits')} <b>INSUFFICIENT CREDITS</b>\n\nThis lookup requires {CHECK_COST} credits. "
            "Purchase credits or invite friends to continue.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("Buy Credits", "buy", "success", "buy"), styled_button("Refer & Earn", "referral", "primary", "referral")]]),
        )
        return

    try:
        possible, valid, e164, region, original_carrier, zones, line_type = describe_phone(normalized)
    except phonenumbers.NumberParseException:
        await update.message.reply_text(f"{premium('◆', 'support')} <b>NUMBER PARSING FAILED</b>", parse_mode=ParseMode.HTML)
        return

    checker_result, checker_error = await registration_lookup(service, e164)

    suffix = normalized[-4:]
    with closing(db_connect()) as db:
        db.execute(
            "INSERT INTO searches (telegram_id, service, phone_suffix, searched_at) VALUES (?, ?, ?, ?)",
            (update.effective_user.id, service, suffix, int(time.time())),
        )
        if checker_error is None:
            db.execute("UPDATE users SET credits = credits - ? WHERE telegram_id = ?", (CHECK_COST, update.effective_user.id))
            db.execute(
                "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'lookup', ?, ?)",
                (update.effective_user.id, -CHECK_COST, service, int(time.time())),
            )
        db.commit()

    if checker_error:
        status_line = f"{premium('◆', 'support')} <b>Status:</b> {checker_error}"
    elif checker_result is True:
        status_line = f"{premium('◆', 'check')} <b>REGISTERED</b>"
    else:
        status_line = f"{premium('◆', 'support')} <b>NOT REGISTERED</b>"
    details = [
        f"{premium('◆', 'search')} <b>{service.upper()} CHECKER</b>\n"
        f"{premium('◆', 'profile')} <b>Number:</b> <code>••••••{suffix}</code>\n\n"
        f"{status_line}\n"
        f"{premium('◆', 'credits')} <b>Lookup charge:</b> {CHECK_COST if checker_error is None else 0} credits\n\n"
        f"{premium('◆', 'home')} <b>Region:</b> {region}\n"
        f"{premium('◆', 'profile')} <b>Number type:</b> {line_type}\n"
        f"{premium('◆', 'sparkle')} <b>Original carrier:</b> {original_carrier}\n"
        f"{premium('◆', 'help')} <b>Timezone:</b> {zones}"
    ]
    await update.message.reply_text(
        "".join(details),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[styled_button("CHECK ANOTHER NUMBER", f"service:{service}", "success", "check")]]),
    )


async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_message is None:
        return
    if not await gate(update, context):
        return
    remember_user(update)
    if context.user_data.get("flow") != "payment_reference" or not context.user_data.get("payment"):
        await update.effective_message.reply_text(
            "Open BUY CREDIT from the dashboard and select a package before submitting payment proof.",
            reply_markup=dashboard_keyboard(),
        )
        return
    package = context.user_data["payment"]
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        proof_type = "PHOTO"
    else:
        file_id = update.message.document.file_id
        proof_type = "DOCUMENT"
    reference = f"{package.get('method', 'manual').upper()} {proof_type}: {file_id}"
    request_id = insert_payment_request(update.effective_user.id, package, reference)
    caption = payment_request_text(request_id, update.effective_user.id, package, reference, telegram_user_label(update.effective_user))
    for admin_id in {value.strip() for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip().isdigit()}:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    int(admin_id),
                    photo=file_id,
                    caption=small_caps_html(caption),
                    parse_mode=ParseMode.HTML,
                    reply_markup=payment_review_keyboard(request_id),
                )
            else:
                await context.bot.send_document(
                    int(admin_id),
                    document=file_id,
                    caption=small_caps_html(caption),
                    parse_mode=ParseMode.HTML,
                    reply_markup=payment_review_keyboard(request_id),
                )
        except Exception:
            logger.info("Could not deliver payment proof to admin %s", admin_id)
    context.user_data.pop("flow", None)
    context.user_data.pop("payment", None)
    await update.message.reply_text(
        f"{premium('◆', 'check')} <b>PAYMENT PROOF RECEIVED</b>\n{divider()}\n\n"
        f"Request <b>#{request_id}</b> is awaiting administrator verification.\n"
        f"Package: <b>{escape(package_title(package))}</b>\n\n"
        "Your order activates only after approval.",
        parse_mode=ParseMode.HTML, reply_markup=dashboard_keyboard(),
    )


def parse_registration_payload(payload):
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None, "Provider returned an undetermined result"
    registered = data.get("is_registered", data.get("registered", data.get("exists")))
    if isinstance(registered, bool):
        return registered, None
    if isinstance(registered, str) and registered.lower() in {"true", "false"}:
        return registered.lower() == "true", None
    status = str(data.get("status", data.get("result", data.get("state", "")))).strip().lower()
    if status in {"registered", "found", "active", "true", "yes", "exists"}:
        return True, None
    if status in {"not_registered", "not registered", "not-found", "not_found", "false", "no", "missing", "not_exists"}:
        return False, None
    return None, "Provider returned an undetermined result"


async def indexed_provider_lookup(name: str, detail: str, identifier: str):
    service_type = indexed_provider_service_type(name, detail)
    if not service_type:
        return None, "Provider API is not connected for this service yet"
    custom_url_match = re.search(r"api_url\s+(https?://\S+)", detail, re.I)
    custom_url = custom_url_match.group(1).strip().rstrip("/") if custom_url_match else ""
    api_key = os.getenv("EKYCPRO_API_KEY", "").strip()
    if not api_key and not custom_url:
        return None, "Provider API key is not configured for this service yet"
    api_url = custom_url or os.getenv("EKYCPRO_API_URL", "https://api.ekycpro.com").strip().rstrip("/")
    endpoint = api_url if custom_url and re.search(r"/check/?$", api_url, re.I) else f"{api_url}/v1/check"
    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=18) as client:
            response = await client.post(
                endpoint,
                json={"service_type": service_type, "identifier": identifier.strip()},
                headers=headers,
            )
            if response.status_code in {401, 403}:
                return None, "Provider API key is invalid or revoked"
            if response.status_code == 429:
                return None, "Provider rate limit reached; try again shortly"
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Indexed provider lookup unavailable: %s", type(exc).__name__)
        return None, "Provider checker temporarily unavailable"
    return parse_registration_payload(payload)


async def registration_lookup(service: str, number: str):
    api_url = os.getenv("CHECKER_API_URL", "https://superassets.in").strip().rstrip("/")
    api_key = os.getenv("CHECKER_API_KEY", "").strip()
    if not api_key:
        return None, "Checker API is not configured"
    service_id = SERVICE_IDS.get(service, service.lower())
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                f"{api_url}/api/v1/check",
                json={"service": service_id, "number": number.lstrip("+")},
                headers={"X-API-Key": api_key},
            )
            if response.status_code in {401, 403}:
                return None, "Checker API key is invalid or revoked"
            if response.status_code == 429:
                return None, "Rate limit reached; try again shortly"
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Registration lookup unavailable: %s", type(exc).__name__)
        return None, "Checker service temporarily unavailable"

    return parse_registration_payload(payload)


def registration_lookup_sync(service: str, number: str):
    api_url = os.getenv("CHECKER_API_URL", "https://superassets.in").strip().rstrip("/")
    api_key = os.getenv("CHECKER_API_KEY", "").strip()
    if not api_key:
        return None, "Checker API is not configured"
    service_id = SERVICE_IDS.get(service, service.lower())
    try:
        response = httpx.post(
            f"{api_url}/api/v1/check",
            json={"service": service_id, "number": number.lstrip("+")},
            headers={"X-API-Key": api_key},
            timeout=12,
        )
        if response.status_code in {401, 403}:
            return None, "Checker API key is invalid or revoked"
        if response.status_code == 429:
            return None, "Rate limit reached; try again shortly"
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Mini App registration lookup unavailable: %s", type(exc).__name__)
        return None, "Checker service temporarily unavailable"

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    registered = data.get("is_registered", data.get("registered"))
    if isinstance(registered, bool):
        return registered, None
    if isinstance(registered, str) and registered.lower() in {"true", "false"}:
        return registered.lower() == "true", None
    status = str(data.get("status", data.get("result", ""))).strip().lower()
    if status in {"registered", "found", "active", "true", "yes"}:
        return True, None
    if status in {"not_registered", "not registered", "not-found", "not_found", "false", "no"}:
        return False, None
    return None, "Provider returned an undetermined result"


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == "verify_join":
        channels = enabled_channels()
        joined = await membership_status(update.effective_user.id, context) if channels else []
        if channels and not all(joined):
            try:
                await query.answer(f"Joined {sum(joined)}/{len(channels)} — complete the missing channels.", show_alert=True)
            except BadRequest:
                return
            try:
                await query.edit_message_text(force_join_text(channels, joined), parse_mode=ParseMode.HTML, reply_markup=join_menu(channels, joined))
            except BadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
            return
        try:
            await query.answer("Membership verified.")
        except BadRequest:
            return
        remember_user(update, context.user_data.pop("pending_referrer", None))
        credits = user_summary(update.effective_user.id)[2]
        welcome_message = await query.edit_message_text(welcome_text(update.effective_user.first_name, credits), parse_mode=ParseMode.HTML)
        await pin_private_welcome(welcome_message, context)
        await query.message.reply_text(verified_text(), parse_mode=ParseMode.HTML, reply_markup=dashboard_keyboard())
        await query.message.reply_text(f"{premium('◆', 'lightning')} <b>BOT READY! USE THE DASHBOARD BUTTONS BELOW.</b>", parse_mode=ParseMode.HTML)
        return
    try:
        await query.answer()
    except BadRequest as exc:
        message = str(exc).lower()
        if "query is too old" in message or "query id is invalid" in message:
            logger.info("Ignored an expired callback query from user %s", update.effective_user.id)
            return
        raise
    if query.data.startswith("adminpay:"):
        if not is_admin_user(update.effective_user.id):
            await query.answer("Administrator access required.", show_alert=True)
            return
        _prefix, action, raw_id = query.data.split(":", 2)
        if not raw_id.isdigit():
            await query.answer("Invalid payment request.", show_alert=True)
            return
        result = review_payment_record(int(raw_id), action)
        if not result:
            await query.answer("Already reviewed or missing.", show_alert=True)
            return
        approved = action == "approve"
        await query.edit_message_text(
            f"{premium('◆', 'check' if approved else 'warn')} <b>PAYMENT #{raw_id} {'APPROVED' if approved else 'DECLINED'}</b>\n{divider()}\n\n"
            f"User: <code>{result['user_id']}</code>\n"
            f"Type: <b>{escape(result['item_type'].upper())}</b>\n"
            f"Package: <b>{escape(result['plan_name'] or str(result['credits']) + ' credits')}</b>\n"
            f"Status: <b>{escape(result['status'].upper())}</b>",
            parse_mode=ParseMode.HTML,
        )
        try:
            await context.bot.send_message(
                int(result["user_id"]),
                review_user_message(int(raw_id), result, approved),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.info("Could not notify user %s about payment review", result["user_id"])
        return
    if not await gate(update, context):
        return
    remember_user(update)
    if query.data in {"buy_100", "buy_500", "buy_1000", "buy_5000", "buy_custom"}:
        if query.data == "buy_custom":
            context.user_data["flow"] = "custom_credit"
            await query.edit_message_text(
                f"{premium('◆', 'credits')} <b>CUSTOM CREDIT PACKAGE</b>\n\nSend the number of credits required. Minimum custom quantity: <b>10 credits</b>.",
                parse_mode=ParseMode.HTML,
            )
        else:
            context.user_data["payment"] = CREDIT_PACKAGES[query.data].copy()
            context.user_data["flow"] = "payment_method"
            await send_payment_methods(query.message, context.user_data["payment"])
            try:
                await query.delete_message()
            except Exception:
                pass
        return
    if query.data in API_PLANS:
        context.user_data["payment"] = API_PLANS[query.data].copy()
        context.user_data["flow"] = "payment_method"
        await send_payment_methods(query.message, context.user_data["payment"])
        try:
            await query.delete_message()
        except Exception:
            pass
        return
    if query.data == "buy_credit_menu":
        await query.edit_message_text(credit_store_text(), parse_mode=ParseMode.HTML, reply_markup=buy_packages_keyboard())
        return
    if query.data == "buy_api_menu":
        await query.edit_message_text(api_store_text(), parse_mode=ParseMode.HTML, reply_markup=api_packages_keyboard())
        return
    if query.data in {"paymethod_upi", "paymethod_usdt"}:
        package = context.user_data.get("payment")
        if not package:
            await query.answer("Payment session expired", show_alert=True)
            return
        method = "upi" if query.data == "paymethod_upi" else "usdt"
        package["method"] = method
        context.user_data["flow"] = "payment_reference"
        if method == "upi":
            destination = payment_value("PAYMENT_UPI_ID", "gauravpayout@fam")
            qr_amount = package.get("price") if package.get("currency") == "INR" else None
            caption = (
                f"{premium('◆', 'payment')} <b>ANNEBELLA PAYMENT QR</b>\n{divider()}\n\n"
                f"{premium('◆', 'credits')} <b>PACKAGE:</b> {escape(package_title(package))}\n"
                f"{premium('◆', 'money')} <b>AMOUNT:</b> {escape(package_price_text(package))}\n"
                f"{premium('◆', 'upi')} <b>UPI:</b> <code>{destination}</code>\n\n"
                f"{premium('◆', 'history')} Scan the QR or copy the UPI ID, complete payment, then send the successful screenshot here for administrator approval."
            )
            await query.message.reply_photo(
                photo=payment_qr_url(int(package.get("credits", 0)), qr_amount),
                caption=small_caps_html(caption),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[copy_button("COPY UPI ID", destination, "success", "upi")]]),
            )
            return
        else:
            binance_id = payment_value("USDT_BINANCE_ID", "1114491025")
            bep20 = payment_value("USDT_BEP20_ADDRESS", "0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f")
            trc20 = payment_value("USDT_TRC20_ADDRESS", "TDfzW7sn7Hut3uQr6Gnk6TyVN2aG6UoUEn")
            erc20 = payment_value("USDT_ERC20_ADDRESS", "0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f")
            instructions = (
                f"{premium('◆', 'usdt')} <b>BINANCE ID</b>\n<code>{binance_id}</code>\n\n"
                f"{premium('◆', 'star')} <b>BSC / BNB — BEP20</b>\n<code>{bep20}</code>\n\n"
                f"{premium('◆', 'star')} <b>TRX / TRON — TRC20</b>\n<code>{trc20}</code>\n\n"
                f"{premium('◆', 'star')} <b>ETH / ETHEREUM — ERC20</b>\n<code>{erc20}</code>"
            )
        await query.edit_message_text(
            f"{premium('◆', 'usdt')} <b>USDT PAYMENT</b>\n{divider()}\n\n"
            f"{premium('◆', 'credits')} <b>PACKAGE:</b> {escape(package_title(package))}\n"
            f"{premium('◆', 'money')} <b>AMOUNT:</b> {escape(package_price_text(package))}\n\n"
            f"{instructions}\n\n{premium('◆', 'history')} Select the exact sender network, use a copy button below, complete payment, then send the successful screenshot here for approval.",
            parse_mode=ParseMode.HTML,
            reply_markup=usdt_payment_keyboard(),
        )
        return
    if query.data == "mini_unlock":
        with closing(db_connect()) as db:
            row = db.execute("SELECT credits, mini_app_unlocked FROM users WHERE telegram_id = ?", (update.effective_user.id,)).fetchone()
            if row[1]:
                unlocked = True
            elif row[0] < MINI_APP_COST:
                shortfall = MINI_APP_COST - row[0]
                await query.edit_message_text(
                    f"{premium('◆', 'lock')} <b>MINI APP ACCESS LOCKED</b>\n{divider()}\n\n"
                    f"{premium('◆', 'credits')} <b>REQUIRED:</b> {MINI_APP_COST} credits\n"
                    f"{premium('◆', 'profile')} <b>YOUR BALANCE:</b> {row[0]} credits\n"
                    f"{premium('◆', 'warn')} <b>SHORTFALL:</b> {shortfall} credits\n\n"
                    f"{premium('◆', 'buy')} Buy credits or invite friends to unlock permanent Mini App access.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [styled_button("BUY CREDIT", "buy", "success", "buy"), styled_button("REFER & EARN", "referral", "primary", "referral")],
                        [styled_button("BACK TO DASHBOARD", "main_menu", "danger", "back")],
                    ]),
                )
                return
            else:
                now = int(time.time())
                activated = db.execute(
                    "UPDATE users SET credits = credits - ?, mini_app_unlocked = 1 WHERE telegram_id = ? AND mini_app_unlocked = 0 AND credits >= ?",
                    (MINI_APP_COST, update.effective_user.id, MINI_APP_COST),
                )
                if activated.rowcount != 1:
                    db.rollback()
                    await query.answer("Account balance changed; please try again", show_alert=True)
                    return
                db.execute("INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'mini_app', 'Permanent Mini App unlock', ?)", (update.effective_user.id, -MINI_APP_COST, now))
                db.commit()
                unlocked = True
        link = mini_app_link(update.effective_user.id)
        markup = InlineKeyboardMarkup([[styled_url_button("OPEN ANNEBELLA MINI APP", link, "success", "miniapp")]]) if link else None
        await query.edit_message_text(
            f"{premium('◆', 'miniapp')} <b>MINI APP ACCESS ACTIVATED</b>\n\n"
            "Permanent access is now linked to your Telegram account. " + ("Use the secure launch button below." if link else "Configure MINI_APP_URL on the host to display the launch button."),
            parse_mode=ParseMode.HTML, reply_markup=markup,
        )
        return
    if query.data == "help":
        await query.edit_message_text(
            f"{premium('◆', 'help')} <b>HOW ANNEBELLA CHECKER WORKS</b>\n\n"
            "<b>1.</b> Select the required service from the checker directory.\n"
            "<b>2.</b> Submit a mobile number in international format, for example <code>+919876543210</code>.\n"
            "<b>3.</b> The bot validates the number and requests an authorized provider lookup.\n"
            "<b>4.</b> A successful determined lookup costs the displayed credit amount. Failed or undetermined provider responses are not charged.\n\n"
            "Use this service only for numbers you are authorized to process.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("CHECKER DIRECTORY", "main_menu", "primary", "search")]]),
        )
    elif query.data == "main_menu":
        context.user_data.pop("service", None)
        context.user_data.pop("flow", None)
        await query.edit_message_text(
            f"{premium('◆', 'search')} <b>ANNEBELLA CHECKER DIRECTORY</b>\n\n"
            f"Select an active checker below, or tap <b>SEARCH SERVICE</b> to browse {len(api_service_catalog())} supported services.",
            parse_mode=ParseMode.HTML,
            reply_markup=menu(),
        )
    elif query.data == "profile":
        await query.edit_message_text(
            profile_text(update.effective_user.id),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("BUY CREDIT", "buy", "success", "buy"), styled_button("CHECKERS", "main_menu", "primary", "search")]]),
        )
    elif query.data == "referral":
        username = BOT_USERNAME or (await context.bot.get_me()).username
        message, link = referral_text(update.effective_user.id, username)
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_url_button("SHARE PERSONAL LINK", f"https://t.me/share/url?url={link}", "success", "referral")]]),
        )
    elif query.data == "buy":
        await query.edit_message_text(
            buy_choice_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=buy_type_keyboard(),
        )
    elif query.data == "support":
        context.user_data["flow"] = "support"
        context.user_data.pop("service", None)
        await query.edit_message_text(
            f"{premium('◆', 'support')} <b>ANNEBELLA PRIORITY SUPPORT</b>\n\n"
            "Describe the issue in one detailed message. Include the checker, approximate time, and displayed error. Never include private authentication information.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_url_button("CONTACT DEVELOPER", SUPPORT_URL, "danger", "support")]]),
        )
    elif query.data == "search_service":
        context.user_data["flow"] = "service_search"
        context.user_data.pop("service", None)
        context.user_data.pop("api_service", None)
        await query.edit_message_text(
            api_service_page_text(0),
            parse_mode=ParseMode.HTML,
            reply_markup=service_page_keyboard(0),
        )
    elif query.data.startswith("services_page:"):
        context.user_data["flow"] = "service_search"
        raw_page = query.data.split(":", 1)[1]
        try:
            page = int(raw_page)
        except ValueError:
            page = 0
        await query.edit_message_text(
            api_service_page_text(page),
            parse_mode=ParseMode.HTML,
            reply_markup=service_page_keyboard(page),
        )
    elif query.data.startswith("api_select:"):
        raw_index = query.data.split(":", 1)[1]
        try:
            item = api_service_by_index(int(raw_index))
        except ValueError:
            item = None
        if not item:
            await query.answer("Service not found. Search again.", show_alert=True)
            return
        if item["active"] and item["name"] in SERVICES:
            context.user_data["service"] = item["name"]
            context.user_data.pop("flow", None)
            await query.edit_message_text(
                f"{premium('?', 'search')} <b>{item['name'].upper()} CHECKER</b>\n\nSend the authorized mobile number with country code. Example: <code>+919876543210</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[styled_button("BACK TO CHECKERS", "main_menu", "danger", "back")]]),
            )
            return
        context.user_data["flow"] = "api_service_input"
        context.user_data["api_service"] = {"name": item["name"], "detail": item["detail"]}
        await query.edit_message_text(
            api_service_select_text(item["name"], item["detail"]),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [styled_button("SEARCH AGAIN", "search_service", "primary", "search")],
                [styled_button("BACK TO CHECKERS", "main_menu", "danger", "back")],
            ]),
        )
    elif query.data.startswith("service:"):
        service = query.data.split(":", 1)[1]
        if service not in SERVICES:
            return
        context.user_data["service"] = service
        context.user_data.pop("flow", None)
        context.user_data.pop("api_service", None)
        await query.edit_message_text(
            f"{premium('◆', 'search')} <b>{service.upper()} CHECKER</b>\n\nSend the authorized mobile number with country code. Example: <code>+919876543210</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("BACK TO CHECKERS", "main_menu", "danger", "back")]]),
        )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


@web.route("/healthz")
def healthz():
    return {"ok": True, "service": BOT_NAME}


@web.route("/miniapp")
def miniapp():
    token = request.args.get("token", "")

    def locked_miniapp(message: str, status: int = 403):
        guest = ("Guest", None, 0, 0, 0, int(time.time()))
        return render_template(
            "miniapp.html", bot_name=BOT_NAME, error=message, user_id="LOCKED", user=guest,
            searches=0, recent=[], services=SERVICES, check_cost=CHECK_COST,
            referral_credits=REFERRAL_CREDITS, mini_app_cost=MINI_APP_COST,
            bot_username=BOT_USERNAME, token="",
        ), status

    user_id = verify_mini_app_token(token)
    if user_id is None:
        return locked_miniapp("Open Mini App from the Telegram bot after unlocking access.")
    with closing(db_connect()) as db:
        user = db.execute(
            "SELECT first_name, username, credits, referral_count, mini_app_unlocked, first_seen FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        searches = db.execute("SELECT COUNT(*) FROM searches WHERE telegram_id = ?", (user_id,)).fetchone()[0]
        recent = db.execute(
            "SELECT service, phone_suffix, searched_at FROM searches WHERE telegram_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,),
        ).fetchall()
    if not user or not user[4]:
        return locked_miniapp("Mini App access is not active for this Telegram account.")
    return render_template(
        "miniapp.html", bot_name=BOT_NAME, error=None, user_id=user_id, user=user,
        searches=searches, recent=recent, services=SERVICES,
        check_cost=CHECK_COST, referral_credits=REFERRAL_CREDITS, mini_app_cost=MINI_APP_COST,
        bot_username=BOT_USERNAME, token=token,
    )


@web.post("/miniapp/api/check")
def miniapp_check():
    data = request.get_json(silent=True) or {}
    token = str(data.get("token", ""))
    user_id = verify_mini_app_token(token)
    if user_id is None:
        return {"ok": False, "error": "Mini App session expired. Open a fresh link from Telegram."}, 403

    service = str(data.get("service", "")).strip()
    normalized = re.sub(r"[\s()-]", "", str(data.get("number", "")))
    if service not in SERVICES:
        return {"ok": False, "error": "Select a valid checker service."}, 400
    if not PHONE_RE.fullmatch(normalized):
        return {"ok": False, "error": "Enter 8-15 digits, optionally starting with +."}, 400

    with closing(db_connect()) as db:
        user = db.execute(
            "SELECT credits, banned, mini_app_unlocked FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        if not user or user[1]:
            return {"ok": False, "error": "Account is not active."}, 403
        if not user[2]:
            return {"ok": False, "error": "Mini App access is locked for this account."}, 403
        if user[0] < CHECK_COST:
            return {"ok": False, "error": f"Insufficient credits. This check requires {CHECK_COST} credits."}, 402

    try:
        _possible, _valid, e164, region, original_carrier, zones, line_type = describe_phone(normalized)
    except phonenumbers.NumberParseException:
        return {"ok": False, "error": "Number parsing failed."}, 400

    checker_result, checker_error = registration_lookup_sync(service, e164)
    charged = checker_error is None
    suffix = normalized[-4:]
    now = int(time.time())
    with closing(db_connect()) as db:
        db.execute(
            "INSERT INTO searches (telegram_id, service, phone_suffix, searched_at) VALUES (?, ?, ?, ?)",
            (user_id, service, suffix, now),
        )
        if charged:
            db.execute("UPDATE users SET credits = credits - ?, last_seen = ? WHERE telegram_id = ?", (CHECK_COST, now, user_id))
            db.execute(
                "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'lookup', ?, ?)",
                (user_id, -CHECK_COST, f"Mini App {service}", now),
            )
        else:
            db.execute("UPDATE users SET last_seen = ? WHERE telegram_id = ?", (now, user_id))
        credits = db.execute("SELECT credits FROM users WHERE telegram_id = ?", (user_id,)).fetchone()[0]
        recent = db.execute(
            "SELECT service, phone_suffix, searched_at FROM searches WHERE telegram_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,),
        ).fetchall()
        db.commit()

    status = "temporarily_unavailable" if checker_error else ("registered" if checker_result else "not_registered")
    return {
        "ok": True,
        "service": service,
        "numberSuffix": suffix,
        "status": status,
        "statusText": checker_error or ("REGISTERED" if checker_result else "NOT REGISTERED"),
        "charged": CHECK_COST if charged else 0,
        "credits": credits,
        "region": region,
        "numberType": line_type,
        "carrier": original_carrier,
        "timezone": zones,
        "recent": [{"service": row[0], "suffix": row[1], "at": row[2]} for row in recent],
    }


def current_api_user():
    api_key = request.headers.get("X-API-Key", "").strip() or request.args.get("api_key", "").strip()
    if not api_key:
        return None, {"ok": False, "error": "Missing X-API-Key header."}, 401
    now = int(time.time())
    with closing(db_connect()) as db:
        row = db.execute(
            """
            SELECT k.telegram_id, k.plan_name, k.expires_at, u.credits, u.banned
            FROM api_keys k
            JOIN users u ON u.telegram_id = k.telegram_id
            WHERE k.api_key = ? AND k.active = 1
            """,
            (api_key,),
        ).fetchone()
    if not row:
        return None, {"ok": False, "error": "Invalid API key."}, 403
    if row[4]:
        return None, {"ok": False, "error": "Account is suspended."}, 403
    if row[2] < now:
        return None, {"ok": False, "error": "API plan expired. Renew access from the bot."}, 403
    return row, None, None


@web.get("/api/v1/me")
def public_api_me():
    row, error, status = current_api_user()
    if error:
        return error, status
    return {
        "ok": True,
        "telegram_id": row[0],
        "plan": row[1],
        "expires_at": row[2],
        "credits": row[3],
        "check_cost": CHECK_COST,
        "services": SERVICES,
    }


@web.post("/api/v1/check")
def public_api_check():
    row, error, status = current_api_user()
    if error:
        return error, status
    user_id, _plan, _expires_at, credits, _banned = row
    data = request.get_json(silent=True) or {}
    service = str(data.get("service", "")).strip()
    normalized = re.sub(r"[\s()-]", "", str(data.get("number", "")))
    if service not in SERVICES:
        return {"ok": False, "error": "Select a valid checker service.", "services": SERVICES}, 400
    if not PHONE_RE.fullmatch(normalized):
        return {"ok": False, "error": "Enter 8-15 digits, optionally starting with +."}, 400
    if credits < CHECK_COST:
        return {"ok": False, "error": f"Insufficient credits. This check requires {CHECK_COST} credits."}, 402
    try:
        _possible, _valid, e164, region, original_carrier, zones, line_type = describe_phone(normalized)
    except phonenumbers.NumberParseException:
        return {"ok": False, "error": "Number parsing failed."}, 400

    checker_result, checker_error = registration_lookup_sync(service, e164)
    charged = checker_error is None
    suffix = normalized[-4:]
    now = int(time.time())
    with closing(db_connect()) as db:
        db.execute(
            "INSERT INTO searches (telegram_id, service, phone_suffix, searched_at) VALUES (?, ?, ?, ?)",
            (user_id, service, suffix, now),
        )
        if charged:
            db.execute("UPDATE users SET credits = credits - ?, last_seen = ? WHERE telegram_id = ?", (CHECK_COST, now, user_id))
            db.execute(
                "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'api_lookup', ?, ?)",
                (user_id, -CHECK_COST, f"API {service}", now),
            )
        else:
            db.execute("UPDATE users SET last_seen = ? WHERE telegram_id = ?", (now, user_id))
        latest_credits = db.execute("SELECT credits FROM users WHERE telegram_id = ?", (user_id,)).fetchone()[0]
        db.commit()
    return {
        "ok": True,
        "service": service,
        "number_suffix": suffix,
        "status": "temporarily_unavailable" if checker_error else ("registered" if checker_result else "not_registered"),
        "registered": checker_result if checker_error is None else None,
        "message": checker_error or ("REGISTERED" if checker_result else "NOT REGISTERED"),
        "charged": CHECK_COST if charged else 0,
        "credits": latest_credits,
        "region": region,
        "number_type": line_type,
        "carrier": original_carrier,
        "timezone": zones,
    }


@web.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        expected = os.getenv("ADMIN_PASSWORD", "")
        if expected and request.form.get("password") == expected:
            session["admin"] = True
            return redirect(url_for("admin_panel"))
        flash("Invalid password")
    return render_template("login.html", bot_name=BOT_NAME)


@web.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@web.route("/", methods=["GET"])
@web.route("/admin", methods=["GET"])
@admin_required
def admin_panel():
    with closing(db_connect()) as db:
        users = db.execute("SELECT telegram_id, username, first_name, credits, referral_count, last_seen, banned FROM users ORDER BY last_seen DESC LIMIT 100").fetchall()
        channels = db.execute("SELECT id, chat_id, title, invite_url, enabled FROM channels ORDER BY id").fetchall()
        user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        search_count = db.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
        total_credits = db.execute("SELECT COALESCE(SUM(credits), 0) FROM users").fetchone()[0]
        pending_count = db.execute("SELECT COUNT(*) FROM payment_requests WHERE status = 'pending'").fetchone()[0]
        active_today = db.execute("SELECT COUNT(*) FROM users WHERE last_seen >= ?", (int(time.time()) - 86400,)).fetchone()[0]
        banned_count = db.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]
        open_tickets = db.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'open'").fetchone()[0]
        unlocked_count = db.execute("SELECT COUNT(*) FROM users WHERE mini_app_unlocked = 1").fetchone()[0]
        enabled_channel_count = db.execute("SELECT COUNT(*) FROM channels WHERE enabled = 1").fetchone()[0]
        approved_revenue = db.execute("SELECT COALESCE(SUM(amount_inr), 0) FROM payment_requests WHERE status = 'approved'").fetchone()[0]
        payments = db.execute("SELECT id, telegram_id, credits, amount_inr, reference, status, created_at, item_type, plan_name, amount_label FROM payment_requests ORDER BY id DESC LIMIT 50").fetchall()
        tickets = db.execute("SELECT id, telegram_id, message, status, created_at FROM support_tickets ORDER BY id DESC LIMIT 50").fetchall()
        gift_cards = db.execute("SELECT id, code, credits, used_by, used_at, created_at FROM gift_cards ORDER BY id DESC LIMIT 100").fetchall()
        recent_searches = db.execute("SELECT telegram_id, service, phone_suffix, searched_at FROM searches ORDER BY id DESC LIMIT 20").fetchall()
        transactions = db.execute("SELECT telegram_id, amount, kind, note, created_at FROM credit_transactions ORDER BY id DESC LIMIT 25").fetchall()
        api_keys = db.execute(
            """
            SELECT k.id, k.telegram_id, u.username, u.first_name, k.api_key, k.plan_name, k.expires_at, k.active, k.created_at
            FROM api_keys k
            LEFT JOIN users u ON u.telegram_id = k.telegram_id
            ORDER BY k.id DESC LIMIT 75
            """
        ).fetchall()
        mini_users = db.execute(
            "SELECT telegram_id, username, first_name, credits, last_seen FROM users WHERE mini_app_unlocked = 1 ORDER BY last_seen DESC LIMIT 75"
        ).fetchall()
        custom_services = db.execute(
            "SELECT id, name, detail, provider_type, api_url, input_type, enabled, created_at FROM custom_services ORDER BY name"
        ).fetchall()
    supported_services = api_service_catalog()
    payment_settings = {
        "PAYMENT_UPI_ID": payment_value("PAYMENT_UPI_ID", "gauravpayout@fam"),
        "USDT_BINANCE_ID": payment_value("USDT_BINANCE_ID", "1114491025"),
        "USDT_BEP20_ADDRESS": payment_value("USDT_BEP20_ADDRESS", "0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f"),
        "USDT_TRC20_ADDRESS": payment_value("USDT_TRC20_ADDRESS", "TDfzW7sn7Hut3uQr6Gnk6TyVN2aG6UoUEn"),
        "USDT_ERC20_ADDRESS": payment_value("USDT_ERC20_ADDRESS", "0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f"),
    }
    return render_template(
        "admin.html", bot_name=BOT_NAME, users=users, channels=channels, user_count=user_count,
        search_count=search_count, total_credits=total_credits, pending_count=pending_count,
        payments=payments, tickets=tickets, gift_cards=gift_cards, active_today=active_today,
        banned_count=banned_count, open_tickets=open_tickets, unlocked_count=unlocked_count,
        approved_revenue=approved_revenue, recent_searches=recent_searches, transactions=transactions,
        enabled_channel_count=enabled_channel_count, services=SERVICES, check_cost=CHECK_COST,
        api_keys=api_keys, mini_users=mini_users, custom_services=custom_services,
        supported_services=supported_services, payment_settings=payment_settings,
        ekyc_enabled=bool(os.getenv("EKYCPRO_API_KEY", "").strip()),
        checker_enabled=bool(os.getenv("CHECKER_API_KEY", "").strip()),
        mini_app_cost=MINI_APP_COST,
    )


@web.route("/admin/shortcut")
@admin_required
def download_admin_shortcut():
    admin_url = url_for("admin_panel", _external=True)
    icon_url = url_for("static", filename="logo.svg", _external=True)
    body = (
        "[InternetShortcut]\r\n"
        f"URL={admin_url}\r\n"
        "IDList=\r\n"
        f"IconFile={icon_url}\r\n"
        "IconIndex=0\r\n"
        "HotKey=0\r\n"
    )
    return Response(
        body,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="AnneBella-Checker-Admin.url"'},
    )


@web.post("/admin/channels")
@admin_required
def add_channel():
    chat_id = request.form.get("chat_id", "").strip()
    title = request.form.get("title", "").strip()
    invite_url = request.form.get("invite_url", "").strip()
    if chat_id and title and invite_url.startswith("https://"):
        with closing(db_connect()) as db:
            db.execute("INSERT OR REPLACE INTO channels (chat_id, title, invite_url, enabled) VALUES (?, ?, ?, 1)", (chat_id, title, invite_url))
            db.commit()
        flash("Channel saved")
    else:
        flash("Enter a valid chat ID, title and HTTPS invite URL")
    return redirect(url_for("admin_panel"))


@web.post("/admin/channels/<int:channel_id>/toggle")
@admin_required
def toggle_channel(channel_id):
    with closing(db_connect()) as db:
        db.execute("UPDATE channels SET enabled = 1 - enabled WHERE id = ?", (channel_id,))
        db.commit()
    return redirect(url_for("admin_panel"))


@web.post("/admin/users/<int:user_id>/ban")
@admin_required
def toggle_ban(user_id):
    with closing(db_connect()) as db:
        db.execute("UPDATE users SET banned = 1 - banned WHERE telegram_id = ?", (user_id,))
        db.commit()
    return redirect(url_for("admin_panel"))


@web.post("/admin/users/<int:user_id>/credits")
@admin_required
def adjust_credits(user_id):
    try:
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        amount = 0
    if amount:
        now = int(time.time())
        with closing(db_connect()) as db:
            db.execute("UPDATE users SET credits = MAX(0, credits + ?) WHERE telegram_id = ?", (amount, user_id))
            db.execute(
                "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'admin', 'Manual adjustment', ?)",
                (user_id, amount, now),
            )
            db.commit()
        flash(f"Credit balance adjusted by {amount:+d}")
        notify_user(
            user_id,
            f"{premium('◆', 'credits')} <b>CREDIT BALANCE UPDATED</b>\n{divider()}\n\n"
            f"{premium('◆', 'profile')} Administrator adjustment: <b>{amount:+d} credits</b>.\n"
            f"{premium('◆', 'refresh')} Open your profile to view the latest balance.",
        )
    return redirect(url_for("admin_panel"))


@web.post("/admin/payments/<int:payment_id>/<action>")
@admin_required
def review_payment(payment_id, action):
    if action not in {"approve", "reject"}:
        return redirect(url_for("admin_panel"))
    result = review_payment_record(payment_id, action)
    if result:
        approved = action == "approve"
        flash(f"Payment #{payment_id} {result['status']}")
        notify_user(result["user_id"], review_user_message(payment_id, result, approved))
    else:
        flash(f"Payment #{payment_id} is already reviewed or missing")
    return redirect(url_for("admin_panel"))


@web.post("/admin/tickets/<int:ticket_id>/close")
@admin_required
def close_ticket(ticket_id):
    with closing(db_connect()) as db:
        db.execute("UPDATE support_tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
        db.commit()
    flash(f"Support ticket #{ticket_id} closed")
    return redirect(url_for("admin_panel"))


@web.post("/admin/gift-cards")
@admin_required
def create_gift_card():
    try:
        credits = int(request.form.get("credits", "0"))
    except ValueError:
        credits = 0
    requested = request.form.get("code", "").upper().strip()
    code = requested or "ANNE-" + "-".join(
        "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4)) for _ in range(2)
    )
    if credits <= 0 or not re.fullmatch(r"[A-Z0-9-]{6,40}", code):
        flash("Enter a positive credit value and a valid gift-card code")
        return redirect(url_for("admin_panel"))
    try:
        with closing(db_connect()) as db:
            db.execute("INSERT INTO gift_cards (code, credits, created_at) VALUES (?, ?, ?)", (code, credits, int(time.time())))
            db.commit()
        flash(f"Gift card created: {code} ({credits} credits)")
    except sqlite3.IntegrityError:
        flash("That gift-card code already exists")
    return redirect(url_for("admin_panel"))


@web.post("/admin/users/<int:user_id>/mini")
@admin_required
def toggle_mini_access(user_id):
    with closing(db_connect()) as db:
        row = db.execute("SELECT mini_app_unlocked FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        if not row:
            flash("User not found")
            return redirect(url_for("admin_panel"))
        new_value = 0 if row[0] else 1
        db.execute("UPDATE users SET mini_app_unlocked = ? WHERE telegram_id = ?", (new_value, user_id))
        db.execute(
            "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, 0, 'mini_app', ?, ?)",
            (user_id, "Admin mini app unlock" if new_value else "Admin mini app lock", int(time.time())),
        )
        db.commit()
    flash("Mini App access updated")
    notify_user(
        user_id,
        f"{premium('◆', 'miniapp')} <b>MINI APP ACCESS {'UNLOCKED' if new_value else 'LOCKED'}</b>\n{divider()}\n\n"
        f"{premium('◆', 'profile')} Administrator updated your Mini App access status.",
    )
    return redirect(url_for("admin_panel"))


@web.post("/admin/api-keys")
@admin_required
def create_admin_api_key():
    try:
        user_id = int(request.form.get("telegram_id", "0"))
        duration_days = int(request.form.get("duration_days", "30"))
    except ValueError:
        flash("Enter a valid Telegram ID and duration")
        return redirect(url_for("admin_panel"))
    plan_name = request.form.get("plan_name", "ADMIN API ACCESS").strip()[:80] or "ADMIN API ACCESS"
    if user_id <= 0 or duration_days <= 0:
        flash("Enter a valid Telegram ID and positive duration")
        return redirect(url_for("admin_panel"))
    with closing(db_connect()) as db:
        user = db.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        if not user:
            flash("User not found")
            return redirect(url_for("admin_panel"))
        api_key = create_api_key(db, user_id, plan_name, duration_days)
        db.commit()
    flash(f"API key created for {user_id}")
    notify_user(
        user_id,
        f"{premium('◆', 'key')} <b>API ACCESS ACTIVATED</b>\n{divider()}\n\n"
        f"{premium('◆', 'star')} <b>PLAN:</b> {escape(plan_name)}\n"
        f"{premium('◆', 'history')} <b>DURATION:</b> {duration_days} days\n"
        f"{premium('◆', 'key')} <b>API KEY:</b> <code>{api_key}</code>",
    )
    return redirect(url_for("admin_panel"))


@web.post("/admin/api-keys/<int:key_id>/toggle")
@admin_required
def toggle_api_key(key_id):
    with closing(db_connect()) as db:
        db.execute("UPDATE api_keys SET active = 1 - active WHERE id = ?", (key_id,))
        db.commit()
    flash("API key status updated")
    return redirect(url_for("admin_panel"))


@web.post("/admin/payment-settings")
@admin_required
def update_payment_settings():
    allowed = {
        "PAYMENT_UPI_ID",
        "USDT_BINANCE_ID",
        "USDT_BEP20_ADDRESS",
        "USDT_TRC20_ADDRESS",
        "USDT_ERC20_ADDRESS",
    }
    now = int(time.time())
    with closing(db_connect()) as db:
        for key in allowed:
            value = request.form.get(key, "").strip()[:500]
            db.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, value, now),
            )
        db.commit()
    flash("Payment information updated")
    return redirect(url_for("admin_panel"))


def notify_new_service_added(name: str, detail: str) -> int:
    with closing(db_connect()) as db:
        rows = db.execute("SELECT telegram_id FROM users WHERE banned = 0").fetchall()
    body = (
        f"{premium('◆', 'rocket')} <b>NEW SERVICE ADDED</b>\n{divider()}\n\n"
        f"{premium('◆', 'search')} <b>SERVICE:</b> {escape(name)}\n"
        f"{premium('◆', 'globe')} <b>STATUS:</b> Available in AnneBella service directory\n\n"
        f"{premium('◆', 'star')} {escape(detail[:600])}\n\n"
        f"{premium('◆', 'check')} Open <b>CHECK SERVICES</b>, tap <b>SEARCH SERVICE</b>, then type the service name."
    )
    sent = 0
    for (user_id,) in rows:
        notify_user(user_id, body)
        sent += 1
        time.sleep(0.04)
    return sent


@web.post("/admin/services")
@admin_required
def add_custom_service():
    name = request.form.get("name", "").strip()
    detail = request.form.get("detail", "").strip()
    provider_type = request.form.get("provider_type", "").strip().lower()
    api_url = request.form.get("api_url", "").strip()
    input_type = request.form.get("input_type", "number").strip().lower()
    should_notify = request.form.get("notify_users") == "1"
    if len(name) < 2 or len(detail) < 5:
        flash("Enter a valid service name and description")
        return redirect(url_for("admin_panel"))
    provider_type = re.sub(r"[^a-z0-9_]", "", provider_type)[:50]
    if api_url and not re.match(r"^https?://", api_url, re.I):
        flash("API URL must start with http:// or https://")
        return redirect(url_for("admin_panel"))
    if input_type not in {"number", "email", "username", "url", "domain", "ip"}:
        input_type = "number"
    now = int(time.time())
    with closing(db_connect()) as db:
        db.execute(
            """
            INSERT INTO custom_services (name, detail, provider_type, api_url, input_type, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(name) DO UPDATE SET
                detail = excluded.detail,
                provider_type = excluded.provider_type,
                api_url = excluded.api_url,
                input_type = excluded.input_type,
                enabled = 1
            """,
            (name[:80], detail[:900], provider_type or None, api_url[:700] or None, input_type, now),
        )
        db.commit()
    notice_detail = f"{detail[:700]}\nInput: {input_type.title()}"
    sent = notify_new_service_added(name[:80], notice_detail) if should_notify else 0
    flash(f"Service saved" + (f" and notified {sent} users" if should_notify else ""))
    return redirect(url_for("admin_panel"))


@web.post("/admin/services/<int:service_id>/toggle")
@admin_required
def toggle_custom_service(service_id):
    with closing(db_connect()) as db:
        db.execute("UPDATE custom_services SET enabled = 1 - enabled WHERE id = ?", (service_id,))
        db.commit()
    flash("Service status updated")
    return redirect(url_for("admin_panel"))


@web.post("/admin/broadcast")
@admin_required
def send_broadcast():
    message = request.form.get("message", "").strip()
    target = request.form.get("target", "all")
    if len(message) < 3:
        flash("Broadcast message is too short")
        return redirect(url_for("admin_panel"))
    with closing(db_connect()) as db:
        if target == "mini":
            rows = db.execute("SELECT telegram_id FROM users WHERE banned = 0 AND mini_app_unlocked = 1").fetchall()
        elif target == "active":
            rows = db.execute("SELECT telegram_id FROM users WHERE banned = 0 AND last_seen >= ?", (int(time.time()) - 86400 * 7,)).fetchall()
        else:
            rows = db.execute("SELECT telegram_id FROM users WHERE banned = 0").fetchall()
    sent = 0
    body = f"{premium('◆', 'rocket')} <b>ANNEBELLA BROADCAST</b>\n{divider()}\n\n{escape(message[:3500])}"
    for (user_id,) in rows:
        notify_user(user_id, body)
        sent += 1
        time.sleep(0.04)
    flash(f"Broadcast queued to {sent} users")
    return redirect(url_for("admin_panel"))


def notify_user(user_id: int, html: str) -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": user_id, "text": small_caps_html(html), "parse_mode": "HTML"},
            timeout=8,
        ).raise_for_status()
    except httpx.HTTPError:
        logger.info("Could not deliver administrative notification to %s", user_id)


def run_web() -> None:
    web.run(host="0.0.0.0", port=WEB_PORT, debug=False, use_reloader=False)


async def telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, BadRequest) and "message is not modified" in str(error).lower():
        return
    if isinstance(error, (Forbidden, TimedOut)):
        logger.info("Ignored Telegram delivery/network error: %s", error)
        return
    if isinstance(error, BadRequest) and "message to be replied not found" in str(error).lower():
        logger.info("Ignored stale Telegram reply target")
        return
    logger.error("Unhandled Telegram update error: %s", error, exc_info=error)


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")
    init_db()
    application = Application.builder().bot(SmallCapsBot(token=token)).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(callbacks))
    application.add_handler(MessageHandler(filters.StatusUpdate.PINNED_MESSAGE, cleanup_pin_service_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_payment_proof))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(telegram_error_handler)
    threading.Thread(target=run_web, daemon=True).start()
    logger.info("Starting %s", BOT_NAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
