import os
import io
import sys
import time
import threading
import traceback
import sqlite3
import datetime
from typing import Optional

import NIKALLLLLLL

from flask import Flask, render_template_string, request, jsonify, send_file
from telegram import Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============ UPTIME ============
START_TIME = datetime.datetime.now()

def format_uptime():
    delta = datetime.datetime.now() - START_TIME
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
    else:
        return f"{hours:02}:{minutes:02}:{seconds:02}"

def uptime_seconds():
    return int((datetime.datetime.now() - START_TIME).total_seconds())

# ============ ENV / CONFIG ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
APP_PORT = int(os.environ.get("PORT", "8080"))
DB_FILE = os.environ.get("DB_FILE", "bot_stats.db")
ERROR_LOG = os.environ.get("ERROR_LOG", "bot_errors.log")

# ============ DB ============
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            timestamp TEXT
        )''')
        conn.commit()

def log_action(user_id: int, username: Optional[str], action: str):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
                      (user_id, username or 'N/A', action, now))
            conn.commit()
    except Exception:
        pass

# ✅ सही जगह पर Import
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, set_country_code, set_group_number,
    make_vcf_command, merge_command, done_merge,
    handle_document, handle_text, OWNER_ID, ALLOWED_USERS,
    reset_settings, my_settings,
    txt2vcf, vcf2txt, rename_file, rename_contact   # 🔥 New features
)

# ============ TELEGRAM BOT ============
if not BOT_TOKEN:
    print("WARNING: BOT_TOKEN not set. Telegram bot will not start.")
application = Application.builder().token(BOT_TOKEN).build() if BOT_TOKEN else None
tg_bot = Bot(BOT_TOKEN) if BOT_TOKEN else None

# error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.utcnow()} - {error_text}\n\n")
    except Exception:
        pass
    try:
        if OWNER_ID:
            await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# Access guard
def is_authorized_in_db(user_id: int) -> bool:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM logs WHERE 1=0")
    except Exception:
        pass
    return user_id in getattr(NIKALLLLLLL, "ALLOWED_USERS", [])

def is_authorized(user_id: int) -> bool:
    return (user_id in getattr(NIKALLLLLLL, "ALLOWED_USERS", [])) or is_authorized_in_db(user_id)

def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        try:
            if not is_authorized(user.id):
                await update.message.reply_text("❌ You don't have access to use this bot.")
                return
            log_action(user.id, user.username, command_name)
            return await handler_func(update, context)
        except Exception:
            try:
                return await handler_func(update, context)
            except Exception:
                raise
    return wrapper

# Register handlers
if application:
    # Old commands
    application.add_handler(CommandHandler("start",          protected(start, "start")))
    application.add_handler(CommandHandler("mysettings",     protected(my_settings, 'mysettings')))
    application.add_handler(CommandHandler("reset",          protected(reset_settings, 'reset')))
    application.add_handler(CommandHandler("setfilename",    protected(set_filename, "setfilename")))
    application.add_handler(CommandHandler("setcontactname", protected(set_contact_name, "setcontactname")))
    application.add_handler(CommandHandler("setlimit",       protected(set_limit, "setlimit")))
    application.add_handler(CommandHandler("setstart",       protected(set_start, "setstart")))
    application.add_handler(CommandHandler("setvcfstart",    protected(set_vcf_start, "setvcfstart")))
    application.add_handler(CommandHandler("setcountrycode", protected(set_country_code, "setcountrycode")))
    application.add_handler(CommandHandler("setgroup",       protected(set_group_number, "setgroup")))
    application.add_handler(CommandHandler("makevcf",        protected(make_vcf_command, "makevcf")))
    application.add_handler(CommandHandler("merge",          protected(merge_command, "merge")))
    application.add_handler(CommandHandler("done",           protected(done_merge, "done")))

    # 🔥 New commands
    application.add_handler(CommandHandler("txt2vcf",        protected(txt2vcf, "txt2vcf")))
    application.add_handler(CommandHandler("vcf2txt",        protected(vcf2txt, "vcf2txt")))
    application.add_handler(CommandHandler("renamefile",     protected(rename_file, "renamefile")))
    application.add_handler(CommandHandler("renamecontact",  protected(rename_contact, "renamecontact")))

    # Handlers
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)

# ============ FLASK DASHBOARD ============
flask_app = Flask(__name__)
flask_app.secret_key = os.environ.get("FLASK_SECRET", "super-secret-key")

@flask_app.route("/")
def home():
    return render_template_string("""
    <h1>VCF Bot Dashboard</h1>
    <p>🤖 Status: Running</p>
    <p>⏱️ Uptime: {{ uptime }}</p>
    <p>📂 Database: {{ db_file }}</p>
    <p>⚠️ Error Log: {{ error_log }}</p>
    """, uptime=format_uptime(), db_file=DB_FILE, error_log=ERROR_LOG)

# ============ MAIN ============
if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=APP_PORT), daemon=True).start()
    if application:
        try:
            print("🚀 Starting Telegram bot polling...")
            application.run_polling()
        except Exception as e:
            print("Bot crashed:", e)
    else:
        print("BOT_TOKEN not set — dashboard running only.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("Stopping.")
