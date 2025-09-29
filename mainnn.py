import os
import re
import sqlite3
import random
import string
import pandas as pd
import traceback
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
OWNER_ID = 7640327597  # change if you want
# initial allowed users (keeps your existing list)
ALLOWED_USERS = [
    7856502907,7770325695,5564571047,7950732287,8128934569,5849097477,
    7640327597,7669357884,5989680310,7118726445,7043391463,8047407478
]

DB_PATH = "bot_data.db"
ERROR_LOG = "bot_errors.log"

# ---------------- DB (keys, users, logs) ----------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            duration TEXT,
            expiry TEXT,
            used_by TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            access_level TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_id INTEGER,
            action TEXT
        )''')
        conn.commit()

def db_execute(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(query, params)
        if fetch:
            res = c.fetchall()
            return res
        conn.commit()

# ---------------- BOT START TIME ----------------
BOT_START_TIME = datetime.now(timezone.utc)

# ---------------- DEFAULTS & USER SETTINGS ----------------
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
conversion_mode = {}  # keyed by user id

# ---------------- UTIL HELPERS ----------------
def is_authorized(user_id: int) -> bool:
    # check ALLOWED_USERS or presence in users table (granted via keys)
    if user_id in ALLOWED_USERS:
        return True
    rows = db_execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetch=True)
    return bool(rows)

def generate_key(length=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def parse_duration(duration_str: str):
    now = datetime.now(timezone.utc)
    try:
        if duration_str.endswith('m'):
            return now + timedelta(minutes=int(duration_str[:-1]))
        elif duration_str.endswith('h'):
            return now + timedelta(hours=int(duration_str[:-1]))
        elif duration_str.endswith('d'):
            return now + timedelta(days=int(duration_str[:-1]))
        elif duration_str.endswith('M'):
            return now + timedelta(days=30*int(duration_str[:-1]))
    except Exception:
        pass
    return now

def add_log(user_id: int, action: str):
    ts = datetime.now(timezone.utc).isoformat()
    db_execute("INSERT INTO logs (timestamp, user_id, action) VALUES (?, ?, ?)", (ts, user_id, action))

# ---------------- ERROR HANDLER ----------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} - {error_text}\n\n")
    except Exception:
        pass
    try:
        if OWNER_ID and context and getattr(context, "bot", None):
            await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# ---------------- VCF HELPERS ----------------
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    vcf_data = ""
    start = int(start_index) if start_index is not None else 1
    for i, num in enumerate(numbers, start=start):
        if group_num is not None:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
    path = f"{filename}.vcf"
    with open(path, "w", encoding="utf-8") as f:
        f.write(vcf_data)
    return path

def extract_numbers_from_vcf(file_path):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for card in content.split('END:VCARD'):
        if 'TEL' in card:
            tel_lines = [line for line in card.splitlines() if line.upper().startswith('TEL')]
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

# ---------------- KEY SYSTEM (OWNER ONLY) ----------------
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text('Usage: /genkey [duration] (e.g. 1d, 5h, 30m)')
        return
    duration = context.args[0]
    key = generate_key(12)
    expiry_dt = parse_duration(duration)
    db_execute("INSERT OR REPLACE INTO keys (key, duration, expiry, used_by) VALUES (?, ?, ?, ?)",
               (key, duration, expiry_dt.isoformat(), None))
    await update.message.reply_text(f'✅ Key generated: `{key}`\nExpires: {expiry_dt.isoformat()}', parse_mode="Markdown")
    add_log(update.effective_user.id, f"genkey:{key}")

async def listkeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    rows = db_execute("SELECT key, duration, expiry, used_by FROM keys", fetch=True)
    if not rows:
        await update.message.reply_text("No keys found.")
        return
    msg = "Active Keys:\n"
    for key, dur, expiry, used_by in rows:
        msg += f"- {key} | {dur} | expiry={expiry} | used_by={used_by}\n"
    await update.message.reply_text(msg)
    add_log(update.effective_user.id, "listkeys")

async def revokekey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text('Usage: /revokekey <key>')
        return
    key = context.args[0]
    db_execute("DELETE FROM keys WHERE key = ?", (key,))
    await update.message.reply_text(f'✅ Key {key} revoked.')
    add_log(update.effective_user.id, f"revokekey:{key}")

async def usekey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Usage: /usekey <key>')
        return
    key = context.args[0]
    rows = db_execute("SELECT expiry, used_by FROM keys WHERE key = ?", (key,), fetch=True)
    if not rows:
        await update.message.reply_text('❌ Invalid key.')
        return
    expiry_iso, used_by = rows[0]
    try:
        expiry_dt = datetime.fromisoformat(expiry_iso) if expiry_iso else None
    except Exception:
        expiry_dt = None
    if expiry_dt and expiry_dt < datetime.now(timezone.utc):
        await update.message.reply_text('❌ This key has expired.')
        return
    # grant user access (insert into users table)
    db_execute("INSERT OR REPLACE INTO users (user_id, username, access_level) VALUES (?, ?, ?)",
               (update.effective_user.id, update.effective_user.username or "", "user"))
    db_execute("UPDATE keys SET used_by = ? WHERE key = ?", (update.effective_user.username or "", key))
    await update.message.reply_text('✅ Key accepted. Access granted.')
    add_log(update.effective_user.id, f"usekey:{key}")

async def adminpanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text('👑 Admin Panel Commands:\n/genkey [time]\n/listkeys\n/revokekey [key]')

# ---------------- START ----------------
ASYNC_COMMANDS = "/genkey, /listkeys, /revokekey, /usekey, /adminpanel"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("Unauthorized. Contact the bot owner.")
        return

    uptime_duration = datetime.now(timezone.utc) - BOT_START_TIME
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
        "/reset → sab settings default par le aao\n"
        "/mysettings → apne current settings dekho\n\n"
    )
    if user.id == OWNER_ID:
        help_text += f"🔑 Key Commands: {ASYNC_COMMANDS}\n"

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-ddhv.onrender.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)
    add_log(user.id, "start")

# ---------------- FILE / TEXT HANDLERS ----------------
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversion_mode[user_id] = "txt2vcf"
    if context.args:
        conversion_mode[f"{user_id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a TXT file, I’ll convert it into VCF.")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversion_mode[user_id] = "vcf2txt"
    if context.args:
        conversion_mode[f"{user_id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a VCF file, I’ll extract numbers into TXT.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("❌ You don't have access to use this bot.")
        return

    file = update.message.document
    if not file:
        await update.message.reply_text("No document found.")
        return
    path = f"{file.file_unique_id}_{file.file_name}"
    # download
    try:
        file_obj = await context.bot.get_file(file.file_id)
        await file_obj.download_to_drive(path)
    except Exception as e:
        await update.message.reply_text(f"Download failed: {e}")
        return

    user_id = user.id

    # Merge mode
    if user_id in merge_data:
        merge_data[user_id]["files"].append(path)
        await update.message.reply_text(f"📥 File added for merge: {file.file_name}")
        return

    # Conversion modes
    if user_id in conversion_mode:
        mode = conversion_mode[user_id]
        if mode == "txt2vcf" and path.lower().endswith(".txt"):
            numbers = extract_numbers_from_txt(path)
            if numbers:
                filename = conversion_mode.get(f"{user_id}_name", "Converted")
                vcf_path = generate_vcf(list(numbers), filename, "Contact")
                await update.message.reply_document(document=open(vcf_path, "rb"))
                os.remove(vcf_path)
            else:
                await update.message.reply_text("❌ No numbers found in TXT file.")
        elif mode == "vcf2txt" and path.lower().endswith(".vcf"):
            numbers = extract_numbers_from_vcf(path)
            if numbers:
                filename = conversion_mode.get(f"{user_id}_name", "Converted")
                txt_path = f"{filename}.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(numbers))
                await update.message.reply_document(document=open(txt_path, "rb"))
                os.remove(txt_path)
            else:
                await update.message.reply_text("❌ No numbers found in VCF file.")
        else:
            await update.message.reply_text("❌ Wrong file type for this command.")
        conversion_mode.pop(user_id, None)
        conversion_mode.pop(f"{user_id}_name", None)
        if os.path.exists(path):
            os.remove(path)
        return

    # fallback: normal processing of uploaded file (csv, xlsx, txt, vcf)
    try:
        if path.lower().endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8', errors='ignore')
            nums = df.iloc[:,0].astype(str).tolist() if not df.empty else []
        elif path.lower().endswith('.xlsx') or path.lower().endswith('.xls'):
            df = pd.read_excel(path)
            nums = df.iloc[:,0].astype(str).tolist() if not df.empty else []
        elif path.lower().endswith('.txt'):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            nums = [''.join(filter(str.isdigit, w)) for w in content.split() if len(re.sub(r'[^0-9]', '', w)) >= 7]
        elif path.lower().endswith('.vcf'):
            nums = list(extract_numbers_from_vcf(path))
        else:
            await update.message.reply_text("Unsupported file type.")
            return
        await process_numbers(update, context, nums)
    except Exception as e:
        await update.message.reply_text(f"Error processing file: {e}")
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("❌ You don't have access to use this bot.")
        return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(re.sub(r'[^0-9]', '', w)) >=7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

# ---------------- PROCESS NUMBERS ----------------
async def process_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, None)
    vcf_num = user_vcf_start_numbers.get(user_id, None)
    country_code = user_country_codes.get(user_id, "")
    custom_group_start = user_group_start_numbers.get(user_id, None)

    # sanitize numbers
    numbers = list(dict.fromkeys([re.sub(r'[^0-9]', '', n).strip() for n in numbers if re.sub(r'[^0-9]', '', n).strip()]))
    if not numbers:
        await update.message.reply_text("No valid numbers found after sanitization.")
        return

    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]
    for idx, chunk in enumerate(chunks):
        group_num = (custom_group_start + idx) if custom_group_start is not None else None
        file_suffix = f"{(vcf_num + idx)}" if vcf_num is not None else f"{idx+1}"
        filename = f"{file_base}_{file_suffix}"
        start_i = (start_index + idx*limit) if start_index is not None else None
        file_path = generate_vcf(chunk, filename, contact_name, start_i, country_code, group_num)
        try:
            await update.message.reply_document(document=open(file_path, "rb"))
        except Exception as e:
            await update.message.reply_text(f"Failed to send file: {e}")
        try:
            os.remove(file_path)
        except Exception:
            pass
        add_log(update.effective_user.id, "makevcf")

# ---------------- SETTINGS COMMANDS ----------------
async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setfilename [ File name ]")
        return
    user_file_names[update.effective_user.id] = ' '.join(context.args)
    await update.message.reply_text(f"✅ File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setcontactname [ Contact name ]")
        return
    user_contact_names[update.effective_user.id] = ' '.join(context.args)
    await update.message.reply_text(f"✅ Contact name set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Limit set to: {context.args[0]}")
    else:
        await update.message.reply_text("Usage: /setlimit [number]")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Contact numbering will start from: {context.args[0]}")
    else:
        await update.message.reply_text("Usage: /setstart [number]")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ VCF numbering will start from: {context.args[0]}")
    else:
        await update.message.reply_text("Usage: /setvcfstart [number]")

async def set_country_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_country_codes[update.effective_user.id] = context.args[0]
        await update.message.reply_text(f"✅ Country code set to: {context.args[0]}")
    else:
        await update.message.reply_text("Usage: /setcountrycode [ +91 ]")

async def set_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_group_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Group numbering will start from: {context.args[0]}")
    else:
        await update.message.reply_text("Usage: /setgroup [number]")

async def reset_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
  # ---------------- MAKEVCF & MERGE ----------------
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name number1 number2 ...")
        return
    contact_name = context.args[0]
    numbers = context.args[1:]
    file_path = generate_vcf(numbers, contact_name, contact_name)
    try:
        await update.message.reply_document(document=open(file_path, "rb"))
    except Exception as e:
        await update.message.reply_text(f"Failed to send file: {e}")
    try:
        os.remove(file_path)
    except Exception:
        pass
    add_log(update.effective_user.id, "makevcf")

async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    merge_data[user_id] = {"files": [], "filename": "Merged"}
    if context.args:
        merge_data[user_id]["filename"] = "_".join(context.args)
    await update.message.reply_text(
        f"📂 Send me files to merge. Final file will be: {merge_data[user_id]['filename']}.vcf\n"
        "👉 When done, use /done."
    )
    await update.message.reply_text(settings)

# ---------------- MAKEVCF & MERGE ----------------
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name number1 number2 ...")
        return
    contact_name = context.args[0]
    numbers = context.args[1:]
    file_path = generate_vcf(numbers, contact_name, contact_name)
    try:
        await update.message.reply_document(document=open(file_path, "rb"))
    except Exception as e:
        await update.message.reply_text(f"Failed to send file: {e}")
    try:
        os.remove(file_path)
    except Exception:
        pass
    add_log(update.effective_user.id, "makevcf")

async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    merge_data[user_id] = {"files": [], "filename": "Merged"}
    if context.args:
        merge_data[user_id]["filename"] = "_".join(context.args)
    await update.message.reply_text(
        f"📂 Send me files to merge. Final file will be: {merge_data[user_id]['filename']}.vcf\n"
        "👉When done, use /done."
    )

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in merge_data or not merge_data[user_id]["files"]:
        await update.message.reply_text("❌ No files queued for merge.")
        return
    all_numbers = set()
    for file_path in merge_data[user_id]["files"]:
        if file_path.lower().endswith(".vcf"):
            all_numbers.update(extract_numbers_from_vcf(file_path))
        elif file_path.lower().endswith(".txt"):
            all_numbers.update(extract_numbers_from_txt(file_path))
    filename = merge_data[user_id]["filename"]
    vcf_path = generate_vcf(list(all_numbers), filename)
    try:
        await update.message.reply_document(document=open(vcf_path, "rb"))
    except Exception as e:
        await update.message.reply_text(f"Failed to send merged file: {e}")
    try:
        os.remove(vcf_path)
    except Exception:
        pass
    for file_path in merge_data[user_id]["files"]:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
    merge_data.pop(user_id, None)
    add_log(user_id, "merge")

# ---------------- PROTECT / WRAPPERS ----------------
def access_message():
    return (
        "📂💾 *VCF Bot Access*\n"
        "Want my *VCF Converter Bot*?\n"
        "Just DM the owner — they will assist you.\n\n"
        "📩 *Owner:* @MADARAXHEREE\n\n"
        "⚡ Convert TXT ⇄ VCF instantly | 🪄 Easy & Quick | 🔒 Trusted"
    )

def protected(handler_func, owner_only=False):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        # Owner-only commands: don't expose if not owner
        if owner_only and user.id != OWNER_ID:
            return
        if not is_authorized(user.id):
            await update.message.reply_text(access_message(), parse_mode="Markdown")
            return
        try:
            # log and call
            add_log(user.id, handler_func.__name__)
            return await handler_func(update, context)
        except Exception:
            # attempt to still run handler to avoid blocking due to logging errors
            return await handler_func(update, context)
    return wrapper

# ---------------- APP / HANDLERS REGISTRATION ----------------
if __name__ == "__main__":
    init_db()

    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set. Please set BOT_TOKEN environment variable.")
        print("The script will not start the Telegram bot without BOT_TOKEN.")
    app = ApplicationBuilder().token(BOT_TOKEN).build() if BOT_TOKEN else None

    if app:
        # core commands
        app.add_handler(CommandHandler("start", protected(start)))
        app.add_handler(CommandHandler("mysettings", protected(my_settings)))
        app.add_handler(CommandHandler("reset", protected(reset_settings)))
        app.add_handler(CommandHandler("setfilename", protected(set_filename)))
        app.add_handler(CommandHandler("setcontactname", protected(set_contact_name)))
        app.add_handler(CommandHandler("setlimit", protected(set_limit)))
        app.add_handler(CommandHandler("setstart", protected(set_start)))
        app.add_handler(CommandHandler("setvcfstart", protected(set_vcf_start)))
        app.add_handler(CommandHandler("setcountrycode", protected(set_country_code)))
        app.add_handler(CommandHandler("setgroup", protected(set_group_number)))
        app.add_handler(CommandHandler("makevcf", protected(make_vcf_command)))
        app.add_handler(CommandHandler("merge", protected(merge_command)))
        app.add_handler(CommandHandler("done", protected(done_merge)))
        app.add_handler(CommandHandler("txt2vcf", protected(txt2vcf)))
        app.add_handler(CommandHandler("vcf2txt", protected(vcf2txt)))

        # key system commands
        app.add_handler(CommandHandler("genkey", protected(genkey, owner_only=True)))
        app.add_handler(CommandHandler("listkeys", protected(listkeys, owner_only=True)))
        app.add_handler(CommandHandler("revokekey", protected(revokekey, owner_only=True)))
        app.add_handler(CommandHandler("usekey", protected(usekey)))  # usekey can be used by anyone (protected checks overall access)
        app.add_handler(CommandHandler("adminpanel", protected(adminpanel, owner_only=True)))

        # message / document handlers
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_error_handler(error_handler)

        print("🚀 Bot is running (polling)...")
        app.run_polling()
    else:
        print("BOT_TOKEN not provided, nothing to run.")
