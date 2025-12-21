import os
import re
import sqlite3
import pandas as pd
import threading
import traceback
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
OWNER_ID = 7640327597

BOT_START_TIME = datetime.utcnow()

# ================= FLASK (RENDER KEEP ALIVE) =================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "🤖 Telegram VCF Bot running"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        role TEXT DEFAULT 'user',
        expiry TEXT
    )
    """)
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, role, expiry) VALUES (?, 'owner', NULL)",
        (OWNER_ID,)
    )
    conn.commit()
    conn.close()

def cleanup_expired_users():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("DELETE FROM users WHERE expiry IS NOT NULL AND expiry < ?", (now,))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def is_authorized(user_id):
    cleanup_expired_users()
    return get_user(user_id) is not None

def is_admin(user_id):
    return get_user(user_id) in ["admin", "owner"]

# ================= UNAUTHORIZED MESSAGE =================
UNAUTH_MSG = (
    "❌ Access denied\n\n"
    "📂💾 VCF Bot Access\n"
    "Want my VCF Converter Bot?\n"
    "Just DM me anytime — I’ll reply fast!\n\n"
    "📩 @MADARAXHEREE\n\n"
    "⚡ Convert TXT ⇄ VCF instantly | 🔒 Trusted"
)

# ================= DEFAULTS (ORIGINAL) =================
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}

# ================= ERROR HANDLER =================
async def error_handler(update, context):
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(error_text + "\n")
    try:
        await context.bot.send_message(OWNER_ID, "⚠️ Bot Error\n\n" + error_text[:3500])
    except:
        pass

# ================= HELPERS (ORIGINAL LOGIC) =================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact",
                 start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index or 1):
        name = f"{contact_name}{str(i).zfill(3)}"
        if group_num:
            name += f" (Group {group_num})"
        formatted = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{formatted}\nEND:VCARD\n"
    with open(f"{filename}.vcf", "w") as f:
        f.write(vcf_data)
    return f"{filename}.vcf"

def extract_numbers_from_vcf(file_path):
    numbers = set()
    with open(file_path, errors="ignore") as f:
        for line in f:
            if line.startswith("TEL"):
                n = re.sub(r"\D", "", line)
                if n:
                    numbers.add(n)
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    with open(file_path, errors="ignore") as f:
        for line in f:
            numbers.update(re.findall(r"\d{7,}", line))
    return numbers

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text(UNAUTH_MSG)
        return

    uptime = datetime.utcnow() - BOT_START_TIME
    days = uptime.days
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    help_text = (
        "☠️ Welcome to the VCF Bot!☠️\n\n"
        f"🤖 Uptime: {days}d {hours}h {minutes}m {seconds}s\n\n"
        "📌 Available Commands:\n"
        "/setfilename [ FILE NAME ]\n"
        "/setcontactname [ CONTACT NAME ]\n"
        "/setlimit [ PER VCF CONTACT ]\n"
        "/setstart [ CONTACT NUMBERING START ]\n"
        "/setvcfstart [ VCF NUMBERING START ]\n"
        "/setcountrycode [ +91 / +1 / +44 ]\n"
        "/setgroup [ START NUMBER ]\n"
        "/makevcf [ NAME numbers ]\n"
        "/merge [ VCF NAME SET ]\n"
        "/done\n"
        "/txt2vcf\n"
        "/vcf2txt\n\n"
        "🧹 Reset & Settings:\n"
        "/reset\n"
        "/mysettings\n\n"
        "📤 Send TXT, CSV, XLSX, or VCF files or numbers."
    )

    await update.message.reply_text(help_text)

# ================= SETTINGS COMMANDS (ORIGINAL) =================
async def set_filename(update, context):
    if context.args:
        user_file_names[update.effective_user.id] = " ".join(context.args)
        await update.message.reply_text("✅ File name updated")

async def set_contact_name(update, context):
    if context.args:
        user_contact_names[update.effective_user.id] = " ".join(context.args)
        await update.message.reply_text("✅ Contact name updated")

async def set_limit(update, context):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ Limit updated")

async def set_start(update, context):
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ Start index updated")

async def set_vcf_start(update, context):
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ VCF start updated")

async def set_country_code(update, context):
    if context.args:
        user_country_codes[update.effective_user.id] = context.args[0]
        await update.message.reply_text("✅ Country code set")

async def set_group_number(update, context):
    if context.args and context.args[0].isdigit():
        user_group_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ Group start set")

async def reset_settings(update, context):
    uid = update.effective_user.id
    user_file_names.pop(uid, None)
    user_contact_names.pop(uid, None)
    user_limits.pop(uid, None)
    user_start_indexes.pop(uid, None)
    user_vcf_start_numbers.pop(uid, None)
    user_country_codes.pop(uid, None)
    user_group_start_numbers.pop(uid, None)
    await update.message.reply_text("✅ All settings reset")

async def my_settings(update, context):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"📂 File name: {user_file_names.get(uid, default_vcf_name)}\n"
        f"👤 Contact name: {user_contact_names.get(uid, default_contact_name)}\n"
        f"📊 Limit: {user_limits.get(uid, default_limit)}"
    )

# ================= ACCESS COMMANDS =================
async def adduser(update, context):
    if not is_admin(update.effective_user.id):
        return
    uid = int(context.args[0])
    days = int(context.args[1])
    role = context.args[2] if len(context.args) > 2 else "user"
    expiry = (datetime.utcnow() + timedelta(days=days)).isoformat()
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO users VALUES (?,?,?)", (uid, role, expiry))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ User added")

async def removeuser(update, context):
    if not is_admin(update.effective_user.id):
        return
    uid = int(context.args[0])
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    await update.message.reply_text("❌ User removed")

async def listusers(update, context):
    if not is_admin(update.effective_user.id):
        return
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    rows = cur.fetchall()
    conn.close()
    msg = "📋 USERS:\n"
    for r in rows:
        msg += f"{r[0]} | {r[1]} | {r[2]}\n"
    await update.message.reply_text(msg)

# ================= BROADCAST =================
async def broadcast(update, context):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message then use /broadcast")
        return

    cleanup_expired_users()
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = [u[0] for u in cur.fetchall()]
    conn.close()

    sent = 0
    for uid in users:
        try:
            await update.message.reply_to_message.copy(chat_id=uid)
            sent += 1
        except:
            pass

    await update.message.reply_text(f"📢 Broadcast sent to {sent} users")

# ================= MAIN =================
if __name__ == "__main__":
    init_db()
    cleanup_expired_users()

    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setfilename", set_filename))
    app.add_handler(CommandHandler("setcontactname", set_contact_name))
    app.add_handler(CommandHandler("setlimit", set_limit))
    app.add_handler(CommandHandler("setstart", set_start))
    app.add_handler(CommandHandler("setvcfstart", set_vcf_start))
    app.add_handler(CommandHandler("setcountrycode", set_country_code))
    app.add_handler(CommandHandler("setgroup", set_group_number))
    app.add_handler(CommandHandler("reset", reset_settings))
    app.add_handler(CommandHandler("mysettings", my_settings))

    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("listusers", listusers))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_error_handler(error_handler)

    print("🚀 BOT RUNNING (ORIGINAL FEATURES + NEW SYSTEM)")
    app.run_polling()
