import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
import httpx
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters


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
RATE_LIMIT_SECONDS = 3
DB_PATH = os.getenv("DATABASE_PATH", "checkerbot.db")
WEB_PORT = int(os.getenv("PORT", "8080"))
PREMIUM_EMOJI_ID = os.getenv("PREMIUM_EMOJI_ID", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/annebella").strip()
SIGNUP_CREDITS = int(os.getenv("SIGNUP_CREDITS", "10"))
REFERRAL_CREDITS = int(os.getenv("REFERRAL_CREDITS", "5"))
CHECK_COST = int(os.getenv("CHECK_COST", "1"))

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
                referral_count INTEGER NOT NULL DEFAULT 0
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
            """
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        migrations = {
            "banned": "ALTER TABLE users ADD COLUMN banned INTEGER NOT NULL DEFAULT 0",
            "first_name": "ALTER TABLE users ADD COLUMN first_name TEXT",
            "credits": "ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 0",
            "referred_by": "ALTER TABLE users ADD COLUMN referred_by INTEGER",
            "referral_count": "ALTER TABLE users ADD COLUMN referral_count INTEGER NOT NULL DEFAULT 0",
        }
        for column, statement in migrations.items():
            if column not in columns:
                db.execute(statement)
        db.commit()


def premium(emoji: str, name: str = "sparkle") -> str:
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(name, "")
    if not emoji_id:
        return emoji
    return f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>'


def styled_button(text: str, data: str, style: str = "primary", emoji: str = "") -> InlineKeyboardButton:
    extras = {"style": style}
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(emoji, "")
    if emoji_id:
        extras["icon_custom_emoji_id"] = emoji_id
    return InlineKeyboardButton(text, callback_data=data, api_kwargs=extras)


def styled_url_button(text: str, url: str, style: str = "primary", emoji: str = "") -> InlineKeyboardButton:
    extras = {"style": style}
    emoji_id = PREMIUM_EMOJI_ID or EMOJI_IDS.get(emoji, "")
    if emoji_id:
        extras["icon_custom_emoji_id"] = emoji_id
    return InlineKeyboardButton(text, url=url, api_kwargs=extras)


def menu() -> InlineKeyboardMarkup:
    buttons = [styled_button(name, f"service:{name}", "primary", "search") for name in SERVICES]
    rows = [buttons[index:index + 3] for index in range(0, len(buttons), 3)]
    rows.extend([
        [styled_button("👤 My Profile", "profile", "primary", "profile"), styled_button("💎 Buy Credits", "buy", "success", "buy")],
        [styled_button("👥 Refer & Earn", "referral", "success", "referral"), styled_button("🛟 Support", "support", "danger", "support")],
        [styled_button("📖 How It Works", "help", "primary", "sparkle")],
    ])
    return InlineKeyboardMarkup(rows)


def join_menu(channels) -> InlineKeyboardMarkup:
    rows = [[styled_url_button(f"📢 Join {title}", url, "primary", "sparkle")] for _, title, url in channels]
    rows.append([styled_button("✅ Verify Membership", "verify_join", "success", "check")])
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
        await update.effective_message.reply_text("🚫 Your access has been suspended.")
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
        if not existing:
            db.execute(
                "INSERT INTO credit_transactions (telegram_id, amount, kind, note, created_at) VALUES (?, ?, 'signup', 'Welcome credits', ?)",
                (user.id, SIGNUP_CREDITS, now),
            )
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
    return not bool(existing)


def user_summary(user_id: int):
    with closing(db_connect()) as db:
        return db.execute(
            "SELECT first_name, username, credits, referral_count, first_seen FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    referred_by = None
    if context.args and context.args[0].startswith("ref_"):
        value = context.args[0][4:]
        referred_by = int(value) if value.isdigit() else None
    is_new = remember_user(update, referred_by)
    if is_new and referred_by and referred_by != update.effective_user.id:
        try:
            await context.bot.send_message(
                referred_by,
                f"🎉 <b>Referral reward credited</b>\n\nA new user joined through your link. "
                f"<b>{REFERRAL_CREDITS} credits</b> have been added to your Annebella account.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.info("Could not deliver referral notification to %s", referred_by)
    if not await gate(update, context):
        return
    context.user_data.pop("service", None)
    signup_note = f"\n\n🎁 <b>Welcome bonus:</b> {SIGNUP_CREDITS} credits added." if is_new else ""
    await update.message.reply_text(
        f"{premium('✨')} <b>Welcome to {BOT_NAME}</b>\n\n"
        "Professional multi-service registration intelligence in one secure interface. "
        "Choose a checker, enter an authorized mobile number, and receive a clear provider response."
        f"\n\n💎 <b>Per successful lookup:</b> {CHECK_COST} credit{signup_note}",
        parse_mode=ParseMode.HTML,
        reply_markup=menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await gate(update, context):
        return
    await update.message.reply_text(
        f"{premium('📖')} <b>How To Use</b>\n\n"
        "1️⃣ Send /start\n2️⃣ Choose a checker\n3️⃣ Send a number with country code\n"
        "Example: <code>+919876543210</code>\n\n"
        "This bot validates input and reports only data available through configured, "
        "authorized integrations. It does not bypass OTPs or expose private account data.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[styled_button("⬅️ Main Menu", "main_menu", "primary")]]),
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    configured = {value.strip() for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip()}
    if str(update.effective_user.id) not in configured:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    with closing(db_connect()) as db:
        users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        searches = db.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    await update.message.reply_text(
        f"★ Bot Statistics ★\n├ Active Users: {users}\n└ Total Searches: {searches}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    remember_user(update)
    if not await gate(update, context):
        return
    text = update.message.text.strip()

    flow = context.user_data.get("flow")
    if flow == "payment_reference":
        match = re.fullmatch(r"(\d{2,6})\s+(.{4,80})", text)
        if not match:
            await update.message.reply_text(
                "❌ <b>Invalid payment submission</b>\n\nSend: <code>credits transaction_reference</code>\n"
                "Example: <code>100 UPI123456789</code>", parse_mode=ParseMode.HTML
            )
            return
        credits, reference = int(match.group(1)), match.group(2).strip()
        amount = credits
        with closing(db_connect()) as db:
            db.execute(
                "INSERT INTO payment_requests (telegram_id, credits, amount_inr, reference, created_at) VALUES (?, ?, ?, ?, ?)",
                (update.effective_user.id, credits, amount, reference, int(time.time())),
            )
            db.commit()
        context.user_data.pop("flow", None)
        await update.message.reply_text(
            f"{premium('✅', 'check')} <b>Payment request received</b>\n\n"
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
                    f"🛟 <b>New support ticket</b>\n\nUser: <code>{update.effective_user.id}</code>\nMessage:\n{text[:1500]}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                logger.info("Could not deliver support alert to admin %s", admin_id)
        await update.message.reply_text(
            f"{premium('✅', 'check')} <b>Support request submitted</b>\n\n"
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
            "❌ Invalid mobile number. Send 8–15 digits, optionally starting with +."
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
            f"💎 <b>Insufficient credits</b>\n\nThis lookup requires {CHECK_COST} credit. "
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
        await update.message.reply_text("❌ Could not parse that mobile number.")
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
        status_line = f"⚠️ <b>Status:</b> {checker_error}"
    elif checker_result is True:
        status_line = "✅ <b>Registered</b>"
    else:
        status_line = "❌ <b>Not Registered</b>"
    details = [
        f"{premium('🔎')} <b>{service}</b>\n"
        f"Number: <code>••••••{suffix}</code>\n\n"
        f"{status_line}\n"
        f"💎 <b>Lookup charge:</b> {CHECK_COST if checker_error is None else 0} credit\n\n"
        f"🌍 <b>Region:</b> {region}\n"
        f"📡 <b>Number type:</b> {line_type}\n"
        f"🏢 <b>Original carrier:</b> {original_carrier}\n"
        f"🕒 <b>Timezone:</b> {zones}"
    ]
    await update.message.reply_text(
        "".join(details),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[styled_button("🔄 Check Another", f"service:{service}", "success")]]),
    )


async def registration_lookup(service: str, number: str):
    api_url = os.getenv("CHECKER_API_URL", "https://superassets.in").strip().rstrip("/")
    api_key = os.getenv("CHECKER_API_KEY", "").strip()
    if not api_key:
        return None, "Checker API is not configured"
    service_id = SERVICE_IDS.get(service, service.lower())
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                f"{api_url}/api/v1/check",
                params={"service": service_id, "number": number.lstrip("+")},
                headers={"X-API-Key": api_key},
            )
            if response.status_code == 429:
                return None, "Rate limit reached; try again shortly"
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Registration lookup unavailable: %s", type(exc).__name__)
        return None, "Checker service temporarily unavailable"

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    registered = data.get("registered")
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
    await query.answer()
    remember_user(update)
    if query.data == "verify_join":
        if not await membership_ok(update.effective_user.id, context):
            await query.answer("Join all required channels first.", show_alert=True)
            return
        await query.edit_message_text(
            f"{premium('✅')} <b>Verified!</b>\n\nChoose a checker:",
            parse_mode=ParseMode.HTML,
            reply_markup=menu(),
        )
        return
    if not await gate(update, context):
        return
    if query.data == "help":
        await query.edit_message_text(
            f"{premium('📖')} <b>How Annebella Checker Works</b>\n\n"
            "<b>1.</b> Select the required service from the checker directory.\n"
            "<b>2.</b> Submit a mobile number in international format, for example <code>+919876543210</code>.\n"
            "<b>3.</b> The bot validates the number and requests an authorized provider lookup.\n"
            "<b>4.</b> A successful determined lookup costs the displayed credit amount. Failed or undetermined provider responses are not charged.\n\n"
            "Use this service only for numbers you are authorized to process.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("⬅️ Main Menu", "main_menu")]]),
        )
    elif query.data == "main_menu":
        context.user_data.pop("service", None)
        context.user_data.pop("flow", None)
        await query.edit_message_text("✨ <b>Annebella Checker Directory</b>\n\nSelect a service or manage your account below.", parse_mode=ParseMode.HTML, reply_markup=menu())
    elif query.data == "profile":
        row = user_summary(update.effective_user.id)
        name, username, credits, referrals, first_seen = row
        await query.edit_message_text(
            f"{premium('👤', 'profile')} <b>Account Overview</b>\n\n"
            f"<b>Name:</b> {name or 'Telegram User'}\n"
            f"<b>Username:</b> {'@' + username if username else 'Not set'}\n"
            f"<b>Telegram ID:</b> <code>{update.effective_user.id}</code>\n"
            f"<b>Available credits:</b> {credits}\n"
            f"<b>Successful referrals:</b> {referrals}\n"
            f"<b>Member since:</b> {time.strftime('%d %b %Y', time.localtime(first_seen))}\n\n"
            "Credits are charged only for determined provider responses.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("Buy Credits", "buy", "success", "buy"), styled_button("Back", "main_menu", "danger", "back")]]),
        )
    elif query.data == "referral":
        username = BOT_USERNAME or (await context.bot.get_me()).username
        link = f"https://t.me/{username}?start=ref_{update.effective_user.id}"
        row = user_summary(update.effective_user.id)
        await query.edit_message_text(
            f"{premium('👥', 'referral')} <b>Refer & Earn</b>\n\n"
            f"Invite a genuine new user and receive <b>{REFERRAL_CREDITS} credits</b> after they start the bot through your personal link. "
            "Self-referrals and previously registered accounts do not qualify.\n\n"
            f"<b>Your referrals:</b> {row[3]}\n"
            f"<b>Your reward link:</b>\n<code>{link}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_url_button("Share Referral Link", f"https://t.me/share/url?url={link}", "success", "referral")], [styled_button("Back", "main_menu", "danger", "back")]]),
        )
    elif query.data == "buy":
        context.user_data["flow"] = "payment_reference"
        context.user_data.pop("service", None)
        upi_id = os.getenv("PAYMENT_UPI_ID", "Contact support").strip()
        await query.edit_message_text(
            f"{premium('💎', 'buy')} <b>Purchase Checker Credits</b>\n\n"
            "<b>Standard rate:</b> ₹1 per credit\n"
            f"<b>UPI ID:</b> <code>{upi_id}</code>\n\n"
            "After payment, send the requested credit quantity followed by the transaction reference.\n"
            "Example: <code>100 UPI123456789</code>\n\n"
            "Payment requests remain pending until manually verified by an administrator. Never send a UPI PIN, OTP, password, or card details.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("Cancel", "main_menu", "danger", "back")]]),
        )
    elif query.data == "support":
        context.user_data["flow"] = "support"
        context.user_data.pop("service", None)
        await query.edit_message_text(
            f"{premium('🛟', 'support')} <b>Customer Support</b>\n\n"
            "Describe your issue in one detailed message. Include the checker name, approximate time, and error shown—never include OTPs, passwords, or payment PINs.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_url_button("Developer Support", SUPPORT_URL, "danger", "support")], [styled_button("Cancel", "main_menu", "danger", "back")]]),
        )
    elif query.data.startswith("service:"):
        service = query.data.split(":", 1)[1]
        if service not in SERVICES:
            return
        context.user_data["service"] = service
        await query.edit_message_text(
            f"{premium('📱')} <b>{service} Checker</b>\n\nSend mobile number with country code:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("⬅️ Back", "main_menu", "danger")]]),
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
    return render_template("admin.html", bot_name=BOT_NAME, users=users, channels=channels, user_count=user_count, search_count=search_count, total_credits=total_credits, pending_count=pending_count, payments=payments, tickets=tickets)


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
        notify_user(user_id, f"💎 <b>Credit balance updated</b>\n\nAdministrator adjustment: <b>{amount:+d} credits</b>. Open your profile to view the latest balance.")
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
                notify_user(payment[0], f"✅ <b>Payment approved</b>\n\n<b>{payment[1]} credits</b> were added to your Annebella Checker account.")
            else:
                notify_user(payment[0], f"❌ <b>Payment not approved</b>\n\nRequest #{payment_id} could not be verified. Please contact support with the correct transaction reference.")
    return redirect(url_for("admin_panel"))


@web.post("/admin/tickets/<int:ticket_id>/close")
@admin_required
def close_ticket(ticket_id):
    with closing(db_connect()) as db:
        db.execute("UPDATE support_tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
        db.commit()
    flash(f"Support ticket #{ticket_id} closed")
    return redirect(url_for("admin_panel"))


def notify_user(user_id: int, html: str) -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": user_id, "text": html, "parse_mode": "HTML"},
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
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(callbacks))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    threading.Thread(target=run_web, daemon=True).start()
    logger.info("Starting %s", BOT_NAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
