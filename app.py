import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlencode
from contextlib import closing
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
import httpx
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, ExtBot, MessageHandler, filters


BOT_NAME = "Annebella Checker Bot"
SERVICES = [
    "Shein", "Flipkart", "Swiggy", "Myntra",
    "Oyo", "Bigbasket", "Blinkit", "Mantrimall",
    "Brevistay", "Ajio", "Amazon", "MyJio",
    "CrownIt", "Meesho", "GoSats", "Telegram",
    "WhatsApp", "HabitYoga",
]
SERVICE_IDS = {
    "MyJio": "jio",
    "HabitYoga": "habuildyoga",
}
PHONE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")
RATE_LIMIT_SECONDS = 5
DB_PATH = os.getenv("DATABASE_PATH", "checkerbot.db")
WEB_PORT = int(os.getenv("PORT", "8080"))
PREMIUM_EMOJI_ID = os.getenv("PREMIUM_EMOJI_ID", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/annebella").strip()
SIGNUP_CREDITS = int(os.getenv("SIGNUP_CREDITS", "150"))
REFERRAL_CREDITS = int(os.getenv("REFERRAL_CREDITS", "20"))
CHECK_COST = int(os.getenv("CHECK_COST", "5"))
MINI_APP_COST = int(os.getenv("MINI_APP_COST", "1000"))

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
}
EMOJI_FALLBACKS = {
    "sparkle": "✨", "profile": "👤", "search": "🔎", "credits": "💎",
    "referral": "👥", "support": "🖥️", "buy": "💳", "back": "📶",
    "check": "✅", "gift": "🎁", "help": "🎵", "miniapp": "🖥️",
    "home": "🏠", "upi": "💸", "usdt": "🖥️",
    "payment": "💳", "name": "📛", "link": "🔗", "id": "🆔",
    "joined": "📅", "lightning": "⚡", "phone": "📱", "money": "💰",
    "history": "📋", "refresh": "🔄", "star": "⭐", "wave": "〰️",
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


def db_connect():
    return sqlite3.connect(DB_PATH)


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
                reviewed_at INTEGER
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
        db.commit()


def premium(emoji: str, name: str = "sparkle") -> str:
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(name, "")
    if not emoji_id:
        return emoji
    entity_text = emoji if PREMIUM_EMOJI_ID else EMOJI_FALLBACKS.get(name, emoji)
    return f'<tg-emoji emoji-id="{emoji_id}">{entity_text}</tg-emoji>'


def divider() -> str:
    return premium("〰️", "wave") * 10


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
    buttons = [styled_button(name, f"service:{name}", "primary", "search") for name in SERVICES]
    rows = [buttons[index:index + 3] for index in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)


def join_menu(channels) -> InlineKeyboardMarkup:
    buttons = [styled_url_button(f"JOIN {title}", url, "primary", "sparkle") for _, title, url in channels]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    rows.append([styled_button("VERIFY MEMBERSHIP", "verify_join", "success", "check")])
    return InlineKeyboardMarkup(rows)


def enabled_channels():
    with closing(db_connect()) as db:
        return db.execute(
            "SELECT chat_id, title, invite_url FROM channels WHERE enabled = 1 ORDER BY id"
        ).fetchall()


async def membership_ok(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    for chat_id, _, _ in enabled_channels():
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in {
                ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED,
            }:
                return False
        except Exception:
            logger.warning("Could not verify required channel %s", chat_id)
            return False
    return True


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    with closing(db_connect()) as db:
        row = db.execute("SELECT banned FROM users WHERE telegram_id = ?", (update.effective_user.id,)).fetchone()
    if row and row[0]:
        await update.effective_message.reply_text(f"{premium('◆', 'support')} <b>ACCESS SUSPENDED</b>\n\nContact support if you believe this restriction is incorrect.", parse_mode=ParseMode.HTML)
        return False
    channels = enabled_channels()
    if channels and not await membership_ok(update.effective_user.id, context):
        await update.effective_message.reply_text(
            f"{premium('🔐')} <b>Join Required</b>\n\nJoin all channels below, then tap verify.",
            parse_mode=ParseMode.HTML,
            reply_markup=join_menu(channels),
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
    base_url = os.getenv("MINI_APP_URL", os.getenv("PUBLIC_APP_URL", "")).strip().rstrip("/")
    if not base_url:
        return None
    token = URLSafeTimedSerializer(web.secret_key).dumps({"user_id": user_id}, salt="mini-app")
    return f"{base_url}/miniapp?token={token}"


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
        f"{premium('◆', 'referral')} <b>ANNEBELLA REFER & EARN</b>\n\n"
        f"Earn <b>{REFERRAL_CREDITS} credits</b> whenever a genuine new member starts the bot through your personal link.\n\n"
        f"<b>SUCCESSFUL REFERRALS</b>\n{row[3]}\n\n"
        f"<b>TOTAL REFERRAL EARNINGS</b>\n{row[3] * REFERRAL_CREDITS} credits\n\n"
        f"<b>PERSONAL INVITATION LINK</b>\n<code>{link}</code>\n\n"
        "Self-referrals, duplicate accounts, and users who previously started the bot do not qualify. Rewards are credited automatically."
    )
    return text, link


def buy_packages_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [styled_button("100 CREDITS", "buy_100", "success", "credits"), styled_button("500 CREDITS", "buy_500", "primary", "credits")],
        [styled_button("1000 CREDITS", "buy_1000", "success", "buy"), styled_button("5000 CREDITS", "buy_5000", "primary", "buy")],
        [styled_button("CUSTOM PACKAGE", "buy_custom", "danger", "buy")],
    ])


def payment_qr_url(credits: int, price: int | None) -> str:
    params = {"pa": os.getenv("PAYMENT_UPI_ID", "gauravpayout@fam").strip(), "pn": "Annebella", "cu": "INR", "tn": f"Annebella {credits} Credits"}
    if price is not None:
        params["am"] = str(price)
    payment_uri = "upi://pay?" + urlencode(params)
    return "https://api.qrserver.com/v1/create-qr-code/?" + urlencode({"size": "320x320", "data": payment_uri})


def usdt_payment_keyboard() -> InlineKeyboardMarkup:
    binance_id = os.getenv("USDT_BINANCE_ID", "1114491025")
    bep20 = os.getenv("USDT_BEP20_ADDRESS", "0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f")
    trc20 = os.getenv("USDT_TRC20_ADDRESS", "TDfzW7sn7Hut3uQr6Gnk6TyVN2aG6UoUEn")
    erc20 = os.getenv("USDT_ERC20_ADDRESS", "0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f")
    return InlineKeyboardMarkup([
        [copy_button("COPY BINANCE ID", binance_id, "success", "usdt"), copy_button("COPY TRC20", trc20, "primary", "usdt")],
        [copy_button("COPY BEP20", bep20, "success", "usdt"), copy_button("COPY ERC20", erc20, "danger", "usdt")],
    ])


async def send_payment_methods(message, package: dict) -> None:
    amount = f"₹{package['price']}" if package.get("price") is not None else "Manually confirmed amount"
    await message.reply_text(
        f"{premium('◆', 'payment')} <b>SELECT PAYMENT METHOD</b>\n{divider()}\n\n"
        f"{premium('◆', 'credits')} <b>PACKAGE:</b> {package['credits']} CREDITS\n"
        f"{premium('◆', 'money')} <b>PAYABLE AMOUNT:</b> {amount}\n\n"
        f"{premium('◆', 'upi')} Choose UPI for a payment QR.\n{premium('◆', 'usdt')} Choose USDT for copy-ready wallet details.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            styled_button("UPI PAYMENT", "paymethod_upi", "success", "upi"),
            styled_button("USDT PAYMENT", "paymethod_usdt", "primary", "usdt"),
        ]]),
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
                f"{premium('◆', 'referral')} <b>REFERRAL REWARD CREDITED</b>\n\nA new user joined through your link. "
                f"<b>{REFERRAL_CREDITS} credits</b> have been added to your Annebella account.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.info("Could not deliver referral notification to %s", referred_by)
    context.user_data.pop("service", None)
    signup_note = f"\n\n{premium('◆', 'gift')} <b>Welcome bonus:</b> {SIGNUP_CREDITS} credits added." if is_new else ""
    await update.message.reply_text(
        f"{premium('✨')} <b>Welcome to {BOT_NAME}</b>\n\n"
        "Professional multi-service registration intelligence in one secure interface. "
        "Use the persistent dashboard below for your profile, credits, Mini App, gift cards, referrals, guidance, and support."
        f"\n\n{premium('◆', 'credits')} <b>Per determined lookup:</b> {CHECK_COST} credits"
        f"\n{premium('◆', 'referral')} <b>Referral reward:</b> {REFERRAL_CREDITS} credits"
        f"{signup_note}",
        parse_mode=ParseMode.HTML,
        reply_markup=dashboard_keyboard(),
    )
    await update.message.reply_text(
        f"{premium('◆', 'search')} <b>Checker Service Directory</b>\n\n"
        "Select the application you want to check. Application choices remain inline for a clean, focused workflow.",
        parse_mode=ParseMode.HTML,
        reply_markup=menu(),
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
                f"{premium('◆', 'search')} <b>CHECKER SERVICE DIRECTORY</b>\n\nSelect an application below. Each determined lookup costs <b>{CHECK_COST} credits</b>.",
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
                f"{premium('◆', 'buy')} <b>ANNEBELLA CREDIT STORE</b>\n{divider()}\n\n"
                "<b>AVAILABLE PACKAGES</b>\n"
                f"{premium('◆', 'credits')} 100 credits — ₹49\n{premium('◆', 'credits')} 500 credits — ₹199\n"
                f"{premium('◆', 'credits')} 1000 credits — ₹349\n{premium('◆', 'credits')} 5000 credits — ₹999\n\n"
                f"{premium('◆', 'upi')} Select UPI for a scannable payment QR.\n"
                f"{premium('◆', 'usdt')} Select USDT for copy-ready Binance and network addresses.\n\n"
                f"{premium('◆', 'check')} <b>PAYMENT VERIFICATION</b>\nAfter payment, send the transaction reference or screenshot here. Credits are released only after administrator approval.\n\n"
                f"{premium('◆', 'support')} <b>SECURITY NOTICE</b>\nThe bot will never request your UPI PIN, OTP, wallet seed phrase, card PIN, or account password.",
                parse_mode=ParseMode.HTML, reply_markup=buy_packages_keyboard(),
            )
        elif text == "MINI APP":
            row = user_summary(update.effective_user.id)
            if row[5]:
                link = mini_app_link(update.effective_user.id)
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("OPEN ANNEBELLA MINI APP", web_app=WebAppInfo(url=link))]]) if link else None
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
    if flow == "custom_credit":
        digits = re.sub(r"\D", "", text)
        if not digits or int(digits) < 10:
            await update.message.reply_text("Enter a custom package of at least 10 credits.")
            return
        context.user_data["payment"] = {"credits": int(digits), "price": None}
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
        credits, reference = package["credits"], f"{package.get('method', 'manual').upper()}: {text.strip()}"
        amount = package.get("price") or 0
        with closing(db_connect()) as db:
            db.execute(
                "INSERT INTO payment_requests (telegram_id, credits, amount_inr, reference, created_at) VALUES (?, ?, ?, ?, ?)",
                (update.effective_user.id, credits, amount, reference, int(time.time())),
            )
            db.commit()
        context.user_data.pop("flow", None)
        context.user_data.pop("payment", None)
        await update.message.reply_text(
            f"{premium('◆', 'check')} <b>PAYMENT REQUEST RECEIVED</b>\n\n"
            f"Credits requested: <b>{credits}</b>\nReference: <code>{reference}</code>\n\n"
            "An administrator will verify the payment. Credits are added only after approval.",
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
        parsed = phonenumbers.parse(normalized, None)
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
    with closing(db_connect()) as db:
        cursor = db.execute(
            "INSERT INTO payment_requests (telegram_id, credits, amount_inr, reference, created_at) VALUES (?, ?, ?, ?, ?)",
            (update.effective_user.id, package["credits"], package.get("price") or 0, reference, int(time.time())),
        )
        request_id = cursor.lastrowid
        db.commit()
    for admin_id in {value.strip() for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip().isdigit()}:
        try:
            await context.bot.forward_message(int(admin_id), update.effective_chat.id, update.message.message_id)
            await context.bot.send_message(
                int(admin_id),
                f"{premium('◆', 'buy')} <b>PAYMENT PROOF #{request_id}</b>\n\n"
                f"User: <code>{update.effective_user.id}</code>\nPackage: <b>{package['credits']} credits</b>\n"
                f"Method: <b>{package.get('method', 'manual').upper()}</b>\nReview it in the web admin panel.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.info("Could not forward payment proof to admin %s", admin_id)
    context.user_data.pop("flow", None)
    context.user_data.pop("payment", None)
    await update.message.reply_text(
        f"{premium('◆', 'check')} <b>PAYMENT PROOF RECEIVED</b>\n\nRequest <b>#{request_id}</b> is awaiting administrator verification. Credits are added only after approval.",
        parse_mode=ParseMode.HTML, reply_markup=dashboard_keyboard(),
    )


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
    try:
        await query.answer()
    except BadRequest as exc:
        message = str(exc).lower()
        if "query is too old" in message or "query id is invalid" in message:
            logger.info("Ignored an expired callback query from user %s", update.effective_user.id)
            return
        raise
    if query.data == "verify_join":
        if not await membership_ok(update.effective_user.id, context):
            await query.answer("Join all required channels first.", show_alert=True)
            return
        is_new = remember_user(update, context.user_data.pop("pending_referrer", None))
        await query.edit_message_text(
            f"{premium('◆', 'check')} <b>MEMBERSHIP VERIFIED</b>\n\nSelect an application checker below.",
            parse_mode=ParseMode.HTML,
            reply_markup=menu(),
        )
        if is_new:
            await query.message.reply_text(
                f"{premium('◆', 'gift')} <b>WELCOME CREDITS ACTIVATED</b>\n\n{SIGNUP_CREDITS} credits were added to your account. The persistent account dashboard is now available below.",
                parse_mode=ParseMode.HTML, reply_markup=dashboard_keyboard(),
            )
        return
    if not await gate(update, context):
        return
    remember_user(update)
    if query.data in {"buy_100", "buy_500", "buy_1000", "buy_5000", "buy_custom"}:
        packages = {
            "buy_100": {"credits": 100, "price": 49},
            "buy_500": {"credits": 500, "price": 199},
            "buy_1000": {"credits": 1000, "price": 349},
            "buy_5000": {"credits": 5000, "price": 999},
        }
        if query.data == "buy_custom":
            context.user_data["flow"] = "custom_credit"
            await query.edit_message_text(
                f"{premium('◆', 'credits')} <b>CUSTOM CREDIT PACKAGE</b>\n\nSend the number of credits required. Minimum custom quantity: <b>10 credits</b>.",
                parse_mode=ParseMode.HTML,
            )
        else:
            context.user_data["payment"] = packages[query.data]
            context.user_data["flow"] = "payment_method"
            await query.edit_message_text(
                f"{premium('◆', 'payment')} <b>SELECT PAYMENT METHOD</b>\n{divider()}\n\n"
                f"{premium('◆', 'credits')} <b>PACKAGE:</b> {packages[query.data]['credits']} CREDITS\n"
                f"{premium('◆', 'money')} <b>PAYABLE AMOUNT:</b> ₹{packages[query.data]['price']}\n\n"
                f"{premium('◆', 'upi')} UPI QR or {premium('◆', 'usdt')} USDT wallet details choose karo.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    styled_button("UPI PAYMENT", "paymethod_upi", "success", "upi"),
                    styled_button("USDT PAYMENT", "paymethod_usdt", "primary", "usdt"),
                ]]),
            )
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
            destination = os.getenv("PAYMENT_UPI_ID", "gauravpayout@fam").strip()
            amount = "₹" + str(package["price"]) if package.get("price") is not None else "Custom/manual"
            caption = (
                f"{premium('◆', 'payment')} <b>ANNEBELLA PAYMENT QR</b>\n{divider()}\n\n"
                f"{premium('◆', 'credits')} <b>PACKAGE:</b> {package['credits']} CREDITS\n"
                f"{premium('◆', 'money')} <b>AMOUNT:</b> {amount}\n"
                f"{premium('◆', 'upi')} <b>UPI:</b> <code>{destination}</code>\n\n"
                f"{premium('◆', 'history')} Scan the QR or copy the UPI ID, complete payment, then send the successful screenshot here for administrator approval."
            )
            await query.message.reply_photo(
                photo=payment_qr_url(package["credits"], package.get("price")),
                caption=small_caps_html(caption),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[copy_button("COPY UPI ID", destination, "success", "upi")]]),
            )
            return
        else:
            instructions = (
                f"{premium('◆', 'usdt')} <b>BINANCE ID</b>\n<code>{os.getenv('USDT_BINANCE_ID', '1114491025')}</code>\n\n"
                f"{premium('◆', 'star')} <b>BSC / BNB — BEP20</b>\n<code>{os.getenv('USDT_BEP20_ADDRESS', '0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f')}</code>\n\n"
                f"{premium('◆', 'star')} <b>TRX / TRON — TRC20</b>\n<code>{os.getenv('USDT_TRC20_ADDRESS', 'TDfzW7sn7Hut3uQr6Gnk6TyVN2aG6UoUEn')}</code>\n\n"
                f"{premium('◆', 'star')} <b>ETH / ETHEREUM — ERC20</b>\n<code>{os.getenv('USDT_ERC20_ADDRESS', '0x430b7abc929366ba7c4e3ca26b6c4177590c0c4f')}</code>"
            )
        await query.edit_message_text(
            f"{premium('◆', 'usdt')} <b>USDT PAYMENT</b>\n{divider()}\n\n"
            f"{premium('◆', 'credits')} <b>PACKAGE:</b> {package['credits']} CREDITS\n"
            f"{premium('◆', 'money')} <b>AMOUNT:</b> {'₹' + str(package['price']) if package.get('price') is not None else 'CUSTOM / MANUAL'}\n\n"
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
                await query.answer(f"Need {MINI_APP_COST - row[0]} more credits", show_alert=True)
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
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("OPEN ANNEBELLA MINI APP", web_app=WebAppInfo(url=link))]]) if link else None
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
        await query.edit_message_text(f"{premium('◆', 'search')} <b>ANNEBELLA CHECKER DIRECTORY</b>\n\nSelect an application below.", parse_mode=ParseMode.HTML, reply_markup=menu())
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
            f"{premium('◆', 'buy')} <b>ANNEBELLA CREDIT STORE</b>\n{divider()}\n\n"
            f"{premium('◆', 'credits')} <b>AVAILABLE PACKAGES</b>\n"
            f"{premium('◆', 'credits')} 100 credits — ₹49\n{premium('◆', 'credits')} 500 credits — ₹199\n"
            f"{premium('◆', 'credits')} 1000 credits — ₹349\n{premium('◆', 'credits')} 5000 credits — ₹999\n\n"
            f"{premium('◆', 'check')} Select the required credit quantity below. Package buttons contain credits only; complete pricing and payment information is shown above.",
            parse_mode=ParseMode.HTML,
            reply_markup=buy_packages_keyboard(),
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
    elif query.data.startswith("service:"):
        service = query.data.split(":", 1)[1]
        if service not in SERVICES:
            return
        context.user_data["service"] = service
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
    try:
        payload = URLSafeTimedSerializer(web.secret_key).loads(token, salt="mini-app", max_age=86400 * 30)
        user_id = int(payload["user_id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return render_template("miniapp.html", bot_name=BOT_NAME, error="This secure Mini App link is invalid or expired."), 403
    with closing(db_connect()) as db:
        user = db.execute(
            "SELECT first_name, username, credits, referral_count, mini_app_unlocked FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        searches = db.execute("SELECT COUNT(*) FROM searches WHERE telegram_id = ?", (user_id,)).fetchone()[0]
        recent = db.execute(
            "SELECT service, phone_suffix, searched_at FROM searches WHERE telegram_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,),
        ).fetchall()
    if not user or not user[4]:
        return render_template("miniapp.html", bot_name=BOT_NAME, error="Mini App access is not active for this account."), 403
    return render_template(
        "miniapp.html", bot_name=BOT_NAME, error=None, user_id=user_id, user=user,
        searches=searches, recent=recent, services=SERVICES,
    )


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
        payments = db.execute("SELECT id, telegram_id, credits, amount_inr, reference, status, created_at FROM payment_requests ORDER BY id DESC LIMIT 50").fetchall()
        tickets = db.execute("SELECT id, telegram_id, message, status, created_at FROM support_tickets ORDER BY id DESC LIMIT 50").fetchall()
        gift_cards = db.execute("SELECT id, code, credits, used_by, used_at, created_at FROM gift_cards ORDER BY id DESC LIMIT 100").fetchall()
    return render_template("admin.html", bot_name=BOT_NAME, users=users, channels=channels, user_count=user_count, search_count=search_count, total_credits=total_credits, pending_count=pending_count, payments=payments, tickets=tickets, gift_cards=gift_cards)


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
        notify_user(user_id, f"{premium('◆', 'credits')} <b>CREDIT BALANCE UPDATED</b>\n\nAdministrator adjustment: <b>{amount:+d} credits</b>. Open your profile to view the latest balance.")
    return redirect(url_for("admin_panel"))


@web.post("/admin/payments/<int:payment_id>/<action>")
@admin_required
def review_payment(payment_id, action):
    if action not in {"approve", "reject"}:
        return redirect(url_for("admin_panel"))
    with closing(db_connect()) as db:
        payment = db.execute(
            "SELECT telegram_id, credits, status FROM payment_requests WHERE id = ?", (payment_id,)
        ).fetchone()
        if payment and payment[2] == "pending":
            status = "approved" if action == "approve" else "rejected"
            db.execute("UPDATE payment_requests SET status = ?, reviewed_at = ? WHERE id = ?", (status, int(time.time()), payment_id))
            if action == "approve":
                db.execute("UPDATE users SET credits = credits + ? WHERE telegram_id = ?", (payment[1], payment[0]))
                db.execute(
                    "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'purchase', ?, ?)",
                    (payment[0], payment[1], f"Approved payment #{payment_id}", int(time.time())),
                )
            db.commit()
            flash(f"Payment #{payment_id} {status}")
            if action == "approve":
                notify_user(payment[0], f"{premium('◆', 'check')} <b>PAYMENT APPROVED</b>\n\n<b>{payment[1]} credits</b> were added to your Annebella Checker account.")
            else:
                notify_user(payment[0], f"{premium('◆', 'support')} <b>PAYMENT NOT APPROVED</b>\n\nRequest #{payment_id} could not be verified. Please contact support with the correct transaction reference.")
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
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_payment_proof))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    threading.Thread(target=run_web, daemon=True).start()
    logger.info("Starting %s", BOT_NAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
