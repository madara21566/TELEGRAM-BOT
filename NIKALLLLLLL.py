import os
import re
import pandas as pd
import traceback
import sqlite3
import random
import string
import datetime
from datetime import datetime as dt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "YOUR_BOT_TOKEN_HERE"
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
OWNER_ID = 7640327597  # original owner id from your file
ALLOWED_USERS = [7856502907,7770325695,5564571047,7950732287,8128934569,5849097477,
                 7640327597,7669357884,5989680310,7118726445,7043391463,8047407478]

# Admins = OWNER_ID + ALLOWED_USERS (Option A)
ADMINS = list(set(ALLOWED_USERS + [OWNER_ID]))

# ==================== DATABASE SETUP ====================
# Using sqlite for keys, users, logs
DB_PATH = "bot_data.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=True)
c = conn.cursor()

# create tables; include expiry column for users
c.execute('''CREATE TABLE IF NOT EXISTS keys (
                 key TEXT PRIMARY KEY,
                 duration TEXT,
                 expiry TEXT,
                 used_by TEXT
             )''')
c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 access_level TEXT,
                 expiry TEXT
             )''')
c.execute('''CREATE TABLE IF NOT EXISTS logs (
                 timestamp TEXT,
                 user_id INTEGER,
                 action TEXT
             )''')
conn.commit()

# ==================== HELPERS (KEY SYSTEM) ====================
def generate_key(length=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def parse_duration_to_expiry(duration_str):
    """Return expiry datetime object based on duration string like '5m','2h','1d','1M'"""
    now = datetime.datetime.now()
    try:
        if duration_str.endswith('m'):
            return now + datetime.timedelta(minutes=int(duration_str[:-1]))
        elif duration_str.endswith('h'):
            return now + datetime.timedelta(hours=int(duration_str[:-1]))
        elif duration_str.endswith('d'):
            return now + datetime.timedelta(days=int(duration_str[:-1]))
        elif duration_str.endswith('M'):
            # treat 'M' as months of 30 days
            return now + datetime.timedelta(days=30*int(duration_str[:-1]))
        else:
            # if plain number, assume days
            return now + datetime.timedelta(days=int(duration_str))
    except Exception:
        # fallback: immediate expiry (now)
        return now

async def log_action(user_id, action):
    try:
        t = datetime.datetime.now().isoformat()
        c.execute('INSERT INTO logs (timestamp, user_id, action) VALUES (?, ?, ?)',
                  (t, user_id, action))
        conn.commit()
    except Exception:
        # don't crash bot for logging issues
        pass

def get_key_row(key):
    c.execute('SELECT key, duration, expiry, used_by FROM keys WHERE key = ?', (key,))
    return c.fetchone()

def is_key_valid(key):
    row = get_key_row(key)
    if not row:
        return False, "not_found"
    _, duration, expiry_str, used_by = row
    try:
        expiry_dt = datetime.datetime.fromisoformat(expiry_str)
    except Exception:
        return False, "invalid_expiry"
    if expiry_dt < datetime.datetime.now():
        return False, "expired"
    return True, {"duration": duration, "expiry": expiry_dt, "used_by": used_by}

def get_user_row(user_id):
    c.execute('SELECT user_id, username, access_level, expiry FROM users WHERE user_id = ?', (user_id,))
    return c.fetchone()

def has_valid_access(user_id):
    # Admins always have access
    if user_id in ADMINS:
        return True
    row = get_user_row(user_id)
    if not row:
        return False
    _, _, access_level, expiry_str = row
    if access_level != 'user':
        return False
    if expiry_str is None:
        return False
    try:
        expiry_dt = datetime.datetime.fromisoformat(expiry_str)
    except Exception:
        return False
    return expiry_dt >= datetime.datetime.now()

def authorize_user_with_key(user_id, username, key):
    """Mark user as having access until key expiry and update key.used_by"""
    row = get_key_row(key)
    if not row:
        return False, "Key does not exist"
    _, duration, expiry_str, used_by = row
    try:
        expiry_dt = datetime.datetime.fromisoformat(expiry_str)
    except Exception:
        return False, "Key expiry invalid"
    # Insert/update user row with expiry
    c.execute('INSERT OR REPLACE INTO users (user_id, username, access_level, expiry) VALUES (?, ?, ?, ?)',
              (user_id, username, 'user', expiry_dt.isoformat()))
    # Mark key as used_by username
    c.execute('UPDATE keys SET used_by = ? WHERE key = ?', (username or str(user_id), key))
    conn.commit()
    return True, expiry_dt

# ==================== VCF BOT (original code) ====================

# BOT START TIME
BOT_START_TIME = datetime.utcnow()

# DEFAULTS
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# USER SETTINGS (in-memory; per-run)
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}  # for txt2vcf / vcf2txt

# ERROR HANDLER
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        # notify owner/admin
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# VCF helpers
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index if start_index else 1)):
        if group_num is not None:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
    with open(f"{filename}.vcf", "w", encoding='utf-8') as f:
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

# AUTH CHECK wrapper used in handlers
def is_authorized(user_id):
    return has_valid_access(user_id)

# TXT2VCF & VCF2TXT (with custom name support)
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ You don't have access to use this bot. Use /usekey <key> or contact admin.")
        return
    conversion_mode[update.effective_user.id] = "txt2vcf"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a TXT file, I’ll convert it into VCF.")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ You don't have access to use this bot. Use /usekey <key> or contact admin.")
        return
    conversion_mode[update.effective_user.id] = "vcf2txt"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a VCF file, I’ll extract numbers into TXT.")

# START (overrides previous start to include key-info)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        # show limited start with key usage info
        help_text = (
            "☠️ Welcome to the VCF Bot!☠️\n\n"
            "You currently don't have access. Ask an admin for a key or use /usekey <key> if you have one.\n\n"
            "If you are an admin, you can use /adminpanel.\n"
        )
        await update.message.reply_text(help_text)
        return

    uptime_duration = datetime.utcnow() - BOT_START_TIME
    days = uptime_duration.days
    hours, rem = divmod(uptime_duration.seconds, 3600)
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
        "/makevcf [ NAME 9876543210 9876543211 ... ]\n"
        "/merge [ VCF NAME SET ]\n"
        "/done [ AFTER FILE SET ]\n"
        "/txt2vcf → [ Convert TXT file to VCF ]\n"
        "/vcf2txt → [ Convert VCF file to TXT ]\n\n"
        "🧹 Reset & Settings:\n"
        "/reset → reset settings to default\n"
        "/mysettings → show your current settings\n\n"
        "📤 Send TXT, CSV, XLSX, or VCF files or numbers."
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-ddhv.onrender.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, reply_markup=reply_markup)

# FILE HANDLER
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ You don't have access to use this bot. Use /usekey <key> or contact admin.")
        return

    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    user_id = update.effective_user.id

    # Merge mode
    if user_id in merge_data:
        merge_data[user_id]["files"].append(path)
        await update.message.reply_text(f"📥 File added for merge: {file.file_name}")
        return

    # Conversion modes
    if user_id in conversion_mode:
        mode = conversion_mode[user_id]

        try:
            if mode == "txt2vcf" and path.endswith(".txt"):
                numbers = extract_numbers_from_txt(path)
                if numbers:
                    filename = conversion_mode.get(f"{user_id}_name", "Converted")
                    vcf_path = generate_vcf(list(numbers), filename, "Contact")
                    await update.message.reply_document(document=open(vcf_path, "rb"))
                    os.remove(vcf_path)
                else:
                    await update.message.reply_text("❌ No numbers found in TXT file.")

            elif mode == "vcf2txt" and path.endswith(".vcf"):
                numbers = extract_numbers_from_vcf(path)
                if numbers:
                    filename = conversion_mode.get(f"{user_id}_name", "Converted")
                    txt_path = f"{filename}.txt"
                    with open(txt_path, "w", encoding='utf-8') as f:
                        f.write("\n".join(numbers))
                    await update.message.reply_document(document=open(txt_path, "rb"))
                    os.remove(txt_path)
                else:
                    await update.message.reply_text("❌ No numbers found in VCF file.")
            else:
                await update.message.reply_text("❌ Wrong file type for this command.")
        finally:
            conversion_mode.pop(user_id, None)
            conversion_mode.pop(f"{user_id}_name", None)
            if os.path.exists(path):
                os.remove(path)
        return

    # fallback: normal handling
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8', dtype=str)
            # try find numeric columns
            if 'Numbers' in df.columns:
                numbers = df['Numbers'].dropna().astype(str).tolist()
            else:
                # flatten df values
                numbers = df.astype(str).stack().tolist()
        elif path.endswith('.xlsx') or path.endswith('.xls'):
            df = pd.read_excel(path, dtype=str)
            numbers = df.astype(str).stack().tolist()
        elif path.endswith('.txt'):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            numbers = [''.join(filter(str.isdigit, w)) for w in content.split() if len(re.sub(r'[^0-9]','',w)) >= 7]
        elif path.endswith('.vcf'):
            numbers = list(extract_numbers_from_vcf(path))
        else:
            await update.message.reply_text("Unsupported file type.")
            return
        # clean numbers
        cleaned = list(dict.fromkeys([re.sub(r'[^0-9]', '', str(n)) for n in numbers if n and re.sub(r'[^0-9]', '', str(n)).isdigit()]))
        await process_numbers(update, context, cleaned)
    except Exception as e:
        await update.message.reply_text(f"Error processing file: {str(e)}")
    finally:
        if os.path.exists(path):
            os.remove(path)

# HANDLE TEXT
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ You don't have access to use this bot. Use /usekey <key> or contact admin.")
        return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(re.sub(r'[^0-9]', '', w)) >=7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

# PROCESS NUMBERS
async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, None)
    vcf_num = user_vcf_start_numbers.get(user_id, None)
    country_code = user_country_codes.get(user_id, "")
    custom_group_start = user_group_start_numbers.get(user_id, None)

    numbers = list(dict.fromkeys([n.strip() for n in numbers if n and str(n).strip().isdigit()]))
    if not numbers:
        await update.message.reply_text("No valid numbers to process.")
        return

    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for idx, chunk in enumerate(chunks):
        group_num = (custom_group_start + idx) if custom_group_start is not None else None
        file_suffix = f"{(vcf_num + idx)}" if vcf_num is not None else f"{idx+1}"
        file_path = generate_vcf(
            chunk,
            f"{file_base}_{file_suffix}",
            contact_name,
            (start_index + idx*limit) if start_index is not None else None,
            country_code,
            group_num
        )
        await update.message.reply_document(document=open(file_path, "rb"))
        os.remove(file_path)

# SETTINGS COMMANDS
async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"✅ File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"✅ Contact name set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Limit set to: {context.args[0]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Contact numbering will start from: {context.args[0]}")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ VCF numbering will start from: {context.args[0]}")

async def set_country_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if context.args:
        user_country_codes[update.effective_user.id] = context.args[0]
        await update.message.reply_text(f"✅ Country code set to: {context.args[0]}")

async def set_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if context.args and context.args[0].isdigit():
        user_group_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Group numbering will start from: {context.args[0]}")

async def reset_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    user_id = update.effective_user.id
    user_file_names.pop(user_id, None)
    user_contact_names.pop(user_id, None)
    user_limits.pop(user_id, None)
    user_start_indexes.pop(user_id, None)
    user_vcf_start_numbers.pop(user_id, None)
    user_country_codes.pop(user_id, None)
    user_group_start_numbers.pop(user_id, None)
    await update.message.reply_text("✅ All settings reset to default.")

async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    user_id = update.effective_user.id
    settings = (
        f"📂 File name: {user_file_names.get(user_id, default_vcf_name)}\n"
        f"👤 Contact name: {user_contact_names.get(user_id, default_contact_name)}\n"
        f"📊 Limit: {user_limits.get(user_id, default_limit)}\n"
        f"🔢 Start index: {user_start_indexes.get(user_id, 'Not set')}\n"
        f"📄 VCF start: {user_vcf_start_numbers.get(user_id, 'Not set')}\n"
        f"🌍 Country code: {user_country_codes.get(user_id, 'None')}\n"
        f"📑 Group start: {user_group_start_numbers.get(user_id, 'Not set')}"
    )
    await update.message.reply_text(settings)

# MAKEVCF
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name number1 number2 ...")
        return

    contact_name = context.args[0]
    numbers = context.args[1:]
    # sanitize numbers
    numbers = [re.sub(r'[^0-9]', '', n) for n in numbers if re.sub(r'[^0-9]', '', n)]
    file_path = generate_vcf(numbers, contact_name, contact_name)
    await update.message.reply_document(document=open(file_path, "rb"))
    os.remove(file_path)

# MERGE
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    user_id = update.effective_user.id
    merge_data[user_id] = {"files": [], "filename": "Merged"}  # default
    if context.args:
        merge_data[user_id]["filename"] = "_".join(context.args)
    await update.message.reply_text(
        f"📂 Send me files to merge. Final file will be: {merge_data[user_id]['filename']}.vcf\n"
        "👉 When done, use /done."
    )

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    user_id = update.effective_user.id
    if user_id not in merge_data or not merge_data[user_id]["files"]:
        await update.message.reply_text("❌ No files queued for merge.")
        return

    all_numbers = set()
    for file_path in merge_data[user_id]["files"]:
        if file_path.endswith(".vcf"):
            all_numbers.update(extract_numbers_from_vcf(file_path))
        elif file_path.endswith(".txt"):
            all_numbers.update(extract_numbers_from_txt(file_path))

    filename = merge_data[user_id]["filename"]
    vcf_path = generate_vcf(list(all_numbers), filename)
    await update.message.reply_document(document=open(vcf_path, "rb"))
    os.remove(vcf_path)
    for file_path in merge_data[user_id]["files"]:
        if os.path.exists(file_path):
            os.remove(file_path)
    merge_data.pop(user_id, None)

    await update.message.reply_text(f"✅ Merge completed → {filename}.vcf")

# ==================== KEY SYSTEM COMMANDS ====================
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text('❌ Only admin can generate keys.')
        return
    if len(context.args) < 1:
        await update.message.reply_text('Usage: /genkey [duration] (e.g. 1d, 5h, 30m, 1M)')
        return
    duration = context.args[0]
    key = generate_key()
    expiry_dt = parse_duration_to_expiry(duration)
    expiry_iso = expiry_dt.isoformat()
    try:
        c.execute('INSERT INTO keys (key, duration, expiry, used_by) VALUES (?, ?, ?, ?)',
                  (key, duration, expiry_iso, None))
        conn.commit()
        await update.message.reply_text(f'✅ Key generated: `{key}` (Expires: {expiry_iso})', parse_mode='Markdown')
        await log_action(user_id, f'Generated key {key} duration {duration}')
    except Exception as e:
        await update.message.reply_text(f"Error generating key: {e}")

async def listkeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text('❌ Only admin can view keys.')
        return
    c.execute('SELECT key, duration, expiry, used_by FROM keys ORDER BY expiry ASC')
    rows = c.fetchall()
    if not rows:
        await update.message.reply_text("No keys found.")
        return
    msg_lines = []
    for row in rows:
        k, dur, exp, used_by = row
        try:
            exp_display = exp
        except:
            exp_display = str(exp)
        msg_lines.append(f"Key: `{k}` | {dur} | Expires: {exp_display} | Used By: {used_by or '---'}")
    msg = "Active Keys:\n" + "\n".join(msg_lines)
    await update.message.reply_text(msg, parse_mode='Markdown')

async def revokekey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text('❌ Only admin can revoke keys.')
        return
    if len(context.args) < 1:
        await update.message.reply_text('Usage: /revokekey <key>')
        return
    key = context.args[0]
    c.execute('DELETE FROM keys WHERE key = ?', (key,))
    conn.commit()
    await update.message.reply_text(f'✅ Key {key} revoked.')
    await log_action(update.effective_user.id, f'Attempted invalid key {key}')
        return
    _, duration, expiry_str, used_by = row
    try:
        expiry_dt = datetime.datetime.fromisoformat(expiry_str)
    except Exception:
        await update.message.reply_text('❌ Key expiry invalid. Contact admin.')
        return
    if expiry_dt < datetime.datetime.now():
        await update.message.reply_text('❌ This key has expired.')
        await log_action(update.effective_user.id, f'Attempted expired key {key}')
        return
    ok, expiry_or_msg = authorize_user_with_key(update.effective_user.id, update.effective_user.username, key)
    if ok:
        await update.message.reply_text(f'✅ Key accepted. Access granted until {expiry_or_msg.isoformat()}.')
        await log_action(update.effective_user.id, f'Used key {key}')
    else:
        await update.message.reply_text(f'❌ Could not authorize: {expiry_or_msg}')
        await log_action(update.effective_user.id, f'Failed to authorize with key {key}')

async def adminpanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text('❌ Only admin can access panel.')
        return
    await update.message.reply_text(
        '👑 Admin Panel Commands:\n'
        '/genkey [time]\n'
        '/listkeys\n'
        '/revokekey [key]\n'
        '/stats'
    )

# Extra admin util: stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text('❌ Only admin can view stats.')
        return
    # gather some simple counts
    c.execute('SELECT COUNT(*) FROM users')
    users_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM keys')
    keys_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM logs')
    logs_count = c.fetchone()[0]
    await update.message.reply_text(f"Users: {users_count}\nKeys: {keys_count}\nLogs: {logs_count}")
# ==================== MAIN ====================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # VCF & settings commands
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

    # Key system commands
    app.add_handler(CommandHandler("genkey", genkey))
    app.add_handler(CommandHandler("listkeys", listkeys))
    app.add_handler(CommandHandler("revokekey", revokekey))
    app.add_handler(CommandHandler("usekey", usekey))
    app.add_handler(CommandHandler("adminpanel", adminpanel))
    app.add_handler(CommandHandler("stats", stats))

    # Handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🚀 Bot is running...")
    app.run_polling()
