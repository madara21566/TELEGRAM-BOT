import os
import re
import sqlite3
import pandas as pd
import threading
from flask import Flask
from datetime import datetime, timedelta
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ======================================================
# CONFIGURATION
# ======================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
OWNER_ID = 7640327597  # Owner Telegram ID

BOT_START_TIME = datetime.utcnow()

# ======================================================
# FLASK (RENDER FREE 24/7 KEEP ALIVE)  🔥 NEW
# ======================================================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "🤖 VCF Bot is running (Render Free)"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# ======================================================
# DATABASE (PERMANENT ACCESS SYSTEM) 🔥 NEW
# ======================================================
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
    # owner auto insert
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

def get_role(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def is_authorized(user_id):
    cleanup_expired_users()
    return get_role(user_id) is not None

def is_admin(user_id):
    return get_role(user_id) in ["admin", "owner"]

# ======================================================
# UNAUTHORIZED MESSAGE 🔥 NEW
# ======================================================
UNAUTH_MSG = (
    "❌ Access denied\n\n"
    "📂💾 VCF Bot Access\n"
    "Want my VCF Converter Bot?\n"
    "Just DM me anytime — I’ll reply fast!\n\n"
    "📩 @MADARAXHEREE\n\n"
    "⚡ Convert TXT ⇄ VCF instantly | 🔒 Trusted"
)

# ======================================================
# DEFAULTS (ORIGINAL)
# ======================================================
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# ======================================================
# USER SETTINGS (ORIGINAL)
# ======================================================
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}

# ======================================================
# ERROR HANDLER (ORIGINAL)
# ======================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    error_text = "".join(
        traceback.format_exception(None, context.error, context.error.__traceback__)
    )
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}"
        )
    except:
        pass

# ======================================================
# HELPERS (ORIGINAL – UNCHANGED)
# ======================================================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact",
                 start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index if start_index else 1)):
        if group_num:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += (
            "BEGIN:VCARD\n"
            "VERSION:3.0\n"
            f"FN:{name}\n"
            f"TEL;TYPE=CELL:{formatted_num}\n"
            "END:VCARD\n"
        )
    with open(f"{filename}.vcf", "w") as f:
        f.write(vcf_data)
    return f"{filename}.vcf"

def extract_numbers_from_vcf(file_path):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for card in content.split('END:VCARD'):
        if 'TEL' in card:
            tel_lines = [line for line in card.splitlines() if line.startswith('TEL')]
            for line in tel_lines:
                number = re.sub(r'[^0-9]', '', line.split(':')[-1].strip())
                if number:
                    numbers.add(number)
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            nums = re.findall(r'\d{7,}', line)
            numbers.update(nums)
    return numbers

# ======================================================
# TXT2VCF & VCF2TXT (ORIGINAL)
# ======================================================
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "txt2vcf"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a TXT file, I’ll convert it into VCF.")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "vcf2txt"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a VCF file, I’ll extract numbers into TXT.")

# ======================================================
# START (ONLY AUTH CHANGED)
# ======================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text(UNAUTH_MSG)
        return

    uptime_duration = datetime.utcnow() - BOT_START_TIME
    days = uptime_duration.days
    hours, rem = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    help_text = (
        "☠️ Welcome to the VCF Bot!☠️\n\n"
        f"🤖 Uptime: {days}d {hours}h {minutes}m {seconds}s\n\n"
        "📌 Available Commands:\n"
        "/setfilename\n/setcontactname\n/setlimit\n/setstart\n"
        "/setvcfstart\n/setcountrycode\n/setgroup\n"
        "/makevcf\n/merge\n/done\n"
        "/txt2vcf\n/vcf2txt\n\n"
        "🧹 Reset & Settings:\n"
        "/reset\n/mysettings\n\n"
        "📤 Send TXT, CSV, XLSX, or VCF files or numbers."
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Owner 💀", url="https://madara21566.github.io/GODMADARA-PROFILE/")]
    ]
    await update.message.reply_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================================================
# FILE HANDLER / TEXT HANDLER / PROCESS NUMBERS
# (ORIGINAL – FULL, UNCHANGED)
# ======================================================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text(UNAUTH_MSG)
        return

    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    user_id = update.effective_user.id

    if user_id in merge_data:
        merge_data[user_id]["files"].append(path)
        await update.message.reply_text(f"📥 File added for merge: {file.file_name}")
        return

    if user_id in conversion_mode:
        mode = conversion_mode[user_id]

        if mode == "txt2vcf" and path.endswith(".txt"):
            numbers = extract_numbers_from_txt(path)
            if numbers:
                filename = conversion_mode.get(f"{user_id}_name", "Converted")
                vcf_path = generate_vcf(list(numbers), filename, "Contact")
                await update.message.reply_document(open(vcf_path, "rb"))
                os.remove(vcf_path)
            else:
                await update.message.reply_text("❌ No numbers found in TXT file.")

        elif mode == "vcf2txt" and path.endswith(".vcf"):
            numbers = extract_numbers_from_vcf(path)
            if numbers:
                filename = conversion_mode.get(f"{user_id}_name", "Converted")
                txt_path = f"{filename}.txt"
                with open(txt_path, "w") as f:
                    f.write("\n".join(numbers))
                await update.message.reply_document(open(txt_path, "rb"))
                os.remove(txt_path)
            else:
                await update.message.reply_text("❌ No numbers found in VCF file.")

        conversion_mode.pop(user_id, None)
        conversion_mode.pop(f"{user_id}_name", None)
        os.remove(path)
        return

    try:
        if path.endswith(".csv"):
            df = pd.read_csv(path)
        elif path.endswith(".xlsx"):
            df = pd.read_excel(path)
        elif path.endswith(".txt"):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            nums = [''.join(filter(str.isdigit, w)) for w in content.split() if len(w) >= 7]
            df = pd.DataFrame({"Numbers": nums})
        elif path.endswith(".vcf"):
            df = pd.DataFrame({"Numbers": list(extract_numbers_from_vcf(path))})
        else:
            await update.message.reply_text("Unsupported file type.")
            return

        await process_numbers(update, context, df["Numbers"].dropna().astype(str).tolist())

    finally:
        if os.path.exists(path):
            os.remove(path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(w) >= 7]
    if numbers:
        await process_numbers(update, context, numbers)

async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id)
    vcf_num = user_vcf_start_numbers.get(user_id)
    country_code = user_country_codes.get(user_id, "")
    custom_group_start = user_group_start_numbers.get(user_id)

    numbers = list(dict.fromkeys(numbers))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for idx, chunk in enumerate(chunks):
        group_num = (custom_group_start + idx) if custom_group_start else None
        file_suffix = f"{vcf_num+idx}" if vcf_num else f"{idx+1}"
        path = generate_vcf(
            chunk,
            f"{file_base}_{file_suffix}",
            contact_name,
            (start_index + idx*limit) if start_index else None,
            country_code,
            group_num
        )
        await update.message.reply_document(open(path, "rb"))
        os.remove(path)

# ======================================================
# SETTINGS COMMANDS / MERGE / DONE / MAKEVCF
# (ORIGINAL – FULL)
# ======================================================
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
        f"📂 File: {user_file_names.get(uid, default_vcf_name)}\n"
        f"👤 Name: {user_contact_names.get(uid, default_contact_name)}\n"
        f"📊 Limit: {user_limits.get(uid, default_limit)}"
    )

async def make_vcf_command(update, context):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name numbers...")
        return
    name = context.args[0]
    nums = context.args[1:]
    path = generate_vcf(nums, name, name)
    await update.message.reply_document(open(path, "rb"))
    os.remove(path)

async def merge_command(update, context):
    uid = update.effective_user.id
    merge_data[uid] = {"files": [], "filename": "_".join(context.args) if context.args else "Merged"}
    await update.message.reply_text("📂 Send files to merge, then /done")

async def done_merge(update, context):
    uid = update.effective_user.id
    if uid not in merge_data:
        return
    all_nums = set()
    for p in merge_data[uid]["files"]:
        if p.endswith(".vcf"):
            all_nums |= extract_numbers_from_vcf(p)
        elif p.endswith(".txt"):
            all_nums |= extract_numbers_from_txt(p)

    out = generate_vcf(list(all_nums), merge_data[uid]["filename"])
    await update.message.reply_document(open(out, "rb"))
    os.remove(out)

    for p in merge_data[uid]["files"]:
        if os.path.exists(p):
            os.remove(p)
    merge_data.pop(uid)

# ======================================================
# ADMIN COMMANDS 🔥 NEW
# ======================================================
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

    sent = 0
    for uid in users:
        try:
            await update.message.reply_to_message.copy(chat_id=uid)
            sent += 1
        except:
            pass

    await update.message.reply_text(f"📢 Broadcast sent to {sent} users")

# ======================================================
# MAIN
# ======================================================
if __name__ == "__main__":
    init_db()
    cleanup_expired_users()

    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # original commands
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
    app.add_handler(CommandHandler("makevcf", make_vcf_command))
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("done", done_merge))
    app.add_handler(CommandHandler("txt2vcf", txt2vcf))
    app.add_handler(CommandHandler("vcf2txt", vcf2txt))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # new admin commands
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("listusers", listusers))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_error_handler(error_handler)

    print("🚀 BOT RUNNING — ORIGINAL + NEW FEATURES (FULL)")
    app.run_polling()
