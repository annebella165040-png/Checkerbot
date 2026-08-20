import logging
import os
import re
import sqlite3
import time
from contextlib import closing

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


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

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


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
                last_seen INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                phone_suffix TEXT NOT NULL,
                searched_at INTEGER NOT NULL
            );
            """
        )
        db.commit()


def menu() -> ReplyKeyboardMarkup:
    rows = []
    for index in range(0, len(SERVICES), 4):
        rows.append([KeyboardButton(name) for name in SERVICES[index:index + 4]])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, input_field_placeholder="Select a checker")


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
    context.user_data.pop("service", None)
    await update.message.reply_text(
        f"Welcome to {BOT_NAME}!\n\nSelect Checker",
        reply_markup=menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Use /start, choose a service, then send a mobile number with country code.\n"
        "Example: +919876543210\n\n"
        "This bot validates input and reports only data available through configured, "
        "authorized integrations. It does not bypass OTPs or expose private account data."
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
    text = update.message.text.strip()

    if text in SERVICES:
        context.user_data["service"] = text
        await update.message.reply_text(
            f"{text} Checker selected.\nEnter Mobile Number with country code:"
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

    suffix = normalized[-4:]
    with closing(db_connect()) as db:
        db.execute(
            "INSERT INTO searches (telegram_id, service, phone_suffix, searched_at) VALUES (?, ?, ?, ?)",
            (update.effective_user.id, service, suffix, int(time.time())),
        )
        db.commit()

    await update.message.reply_text(
        f"🔎 {service}\n"
        f"Number: ••••••{suffix}\n\n"
        "ℹ️ Number format is valid. Registration status is unavailable because no "
        "authorized provider integration is configured."
    )


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")
    init_db()
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Starting %s", BOT_NAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
