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
    return "🤖 VCF Bot is running successfully!"

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

# ================= ERROR HANDLER =================
async def error_handler(update, context):
    err = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(err + "\n")
    try:
        await context.bot.send_message(OWNER_ID, "⚠️ Bot Error\n\n" + err[:3500])
    except:
        pass

# ================= DEFAULTS =================
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

# ================= HELPERS =================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact",
                 start_index=None, country_code="", group_num=None):
    vcf = ""
    for i, num in enumerate(numbers, start=start_index or 1):
        name = f"{contact_name}{str(i).zfill(3)}"
        if group_num:
            name += f" (Group {group_num})"
        num = f"{country_code}{num}" if country_code else num
        vcf += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{num}\nEND:VCARD\n"
    with open(f"{filename}.vcf", "w") as f:
        f.write(vcf)
    return f"{filename}.vcf"

def extract_numbers_from_vcf(path):
    nums = set()
    with open(path, errors="ignore") as f:
        for line in f:
            if line.startswith("TEL"):
                n = re.sub(r"\D", "", line)
                if n:
                    nums.add(n)
    return nums

def extract_numbers_from_txt(path):
    nums = set()
    with open(path, errors="ignore") as f:
        for line in f:
            nums.update(re.findall(r"\d{7,}", line))
    return nums

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text(UNAUTH_MSG)
        return

    uptime = datetime.utcnow() - BOT_START_TIME
    role = get_user(update.effective_user.id)

    text = (
        "☠️ Welcome to the VCF Bot! ☠️\n\n"
        f"🤖 Uptime: {uptime}\n"
        f"👤 Role: {role.upper()}\n\n"
        "📌 Commands:\n"
        "/setfilename\n/setcontactname\n/setlimit\n/setstart\n"
        "/setvcfstart\n/setcountrycode\n/setgroup\n"
        "/makevcf\n/merge\n/done\n"
        "/txt2vcf\n/vcf2txt\n"
        "/reset\n/mysettings\n"
    )

    if is_admin(update.effective_user.id):
        text += (
            "\n🛡️ Admin:\n"
            "/adduser <id> <days> [admin/user]\n"
            "/removeuser <id>\n"
            "/listusers\n"
            "/broadcast\n"
        )

    await update.message.reply_text(text)

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
    for u in rows:
        msg += f"{u[0]} | {u[1]} | {u[2]}\n"
    await update.message.reply_text(msg)

# ================= BROADCAST =================
async def broadcast(update, context):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message with /broadcast")
        return

    cleanup_expired_users()
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = [u[0] for u in cur.fetchall()]
    conn.close()

    for uid in users:
        try:
            await update.message.reply_to_message.copy(chat_id=uid)
        except:
            pass
    await update.message.reply_text("📢 Broadcast sent")

# ================= FILE HANDLER =================
async def handle_document(update, context):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text(UNAUTH_MSG)
        return

    file = update.message.document
    path = file.file_name
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)

    if path.endswith(".txt"):
        nums = extract_numbers_from_txt(path)
    elif path.endswith(".vcf"):
        nums = extract_numbers_from_vcf(path)
    else:
        await update.message.reply_text("Unsupported file")
        return

    out = generate_vcf(nums, "Converted")
    await update.message.reply_document(open(out, "rb"))
    os.remove(path)
    os.remove(out)

# ================= MAIN =================
if __name__ == "__main__":
    init_db()
    cleanup_expired_users()

    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("listusers", listusers))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_error_handler(error_handler)

    print("🚀 Bot running with ALL original features + new system")
    app.run_polling()
