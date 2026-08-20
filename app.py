import logging
import os
import re
import sqlite3
import threading
import time
from contextlib import closing
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
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
PHONE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")
RATE_LIMIT_SECONDS = 3
DB_PATH = os.getenv("DATABASE_PATH", "checkerbot.db")
WEB_PORT = int(os.getenv("PORT", "8080"))
PREMIUM_EMOJI_ID = os.getenv("PREMIUM_EMOJI_ID", "").strip()

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
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                banned INTEGER NOT NULL DEFAULT 0
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
            """
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        if "banned" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN banned INTEGER NOT NULL DEFAULT 0")
        db.commit()


def premium(emoji: str) -> str:
    if not PREMIUM_EMOJI_ID:
        return emoji
    return f'<tg-emoji emoji-id="{PREMIUM_EMOJI_ID}">{emoji}</tg-emoji>'


def styled_button(text: str, data: str, style: str = "primary") -> InlineKeyboardButton:
    extras = {"style": style}
    if PREMIUM_EMOJI_ID:
        extras["icon_custom_emoji_id"] = PREMIUM_EMOJI_ID
    return InlineKeyboardButton(text, callback_data=data, api_kwargs=extras)


def menu() -> InlineKeyboardMarkup:
    buttons = [styled_button(name, f"service:{name}", "primary") for name in SERVICES]
    rows = [buttons[index:index + 3] for index in range(0, len(buttons), 3)]
    rows.append([styled_button("❓ How To Use", "help", "success")])
    return InlineKeyboardMarkup(rows)


def join_menu(channels) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📢 Join {title}", url=url)] for _, title, url in channels]
    rows.append([styled_button("✅ I Have Joined", "verify_join", "success")])
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


def remember_user(update: Update) -> None:
    user = update.effective_user
    now = int(time.time())
    with closing(db_connect()) as db:
        db.execute(
            """
            INSERT INTO users (telegram_id, username, first_seen, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                last_seen = excluded.last_seen
            """,
            (user.id, user.username, now, now),
        )
        db.commit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    remember_user(update)
    if not await gate(update, context):
        return
    context.user_data.pop("service", None)
    await update.message.reply_text(
        f"{premium('✨')} <b>Welcome to {BOT_NAME}</b>\n\n"
        "Choose a service below, then send the mobile number with country code.",
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

    suffix = normalized[-4:]
    with closing(db_connect()) as db:
        db.execute(
            "INSERT INTO searches (telegram_id, service, phone_suffix, searched_at) VALUES (?, ?, ?, ?)",
            (update.effective_user.id, service, suffix, int(time.time())),
        )
        db.commit()

    await update.message.reply_text(
        f"{premium('🔎')} <b>{service}</b>\n"
        f"Number: ••••••{suffix}\n\n"
        "ℹ️ Number format is valid. Registration status is unavailable because no "
        "authorized provider integration is configured.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[styled_button("🔄 Check Another", f"service:{service}", "success")]]),
    )


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
            f"{premium('📖')} <b>How To Use</b>\n\n"
            "1️⃣ Choose a checker\n2️⃣ Send a number with country code\n"
            "3️⃣ Read the safe validation result",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[styled_button("⬅️ Main Menu", "main_menu")]]),
        )
    elif query.data == "main_menu":
        context.user_data.pop("service", None)
        await query.edit_message_text("✨ <b>Select Checker</b>", parse_mode=ParseMode.HTML, reply_markup=menu())
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
        users = db.execute("SELECT telegram_id, username, last_seen, banned FROM users ORDER BY last_seen DESC LIMIT 100").fetchall()
        channels = db.execute("SELECT id, chat_id, title, invite_url, enabled FROM channels ORDER BY id").fetchall()
        user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        search_count = db.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    return render_template("admin.html", bot_name=BOT_NAME, users=users, channels=channels, user_count=user_count, search_count=search_count)


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
