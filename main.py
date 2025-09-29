import os
import re
import sqlite3
import random
import string
import pandas as pd
import traceback
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ✅ CONFIGURATION
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
OWNER_ID = 7640327597  # Your Telegram ID
ALLOWED_USERS = [7856502907,7770325695,5564571047,7950732287,8128934569,5849097477,
                 7640327597,7669357884,5989680310,7118726445,7043391463,8047407478]

# DB Setup for keys/logs
conn = sqlite3.connect('bot_data.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, duration TEXT, expiry TIMESTAMP, used_by TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, access_level TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS logs (timestamp TIMESTAMP, user_id INTEGER, action TEXT)''')
conn.commit()

BOT_START_TIME = datetime.utcnow()

# ✅ DEFAULTS
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# ✅ USER SETTINGS
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}  # 🔥 for txt2vcf / vcf2txt

# ✅ HELPERS
def is_authorized(user_id):
    return user_id in ALLOWED_USERS

def generate_key(length=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def parse_duration(duration_str):
    now = datetime.now()
    if duration_str.endswith('m'):
        return now + timedelta(minutes=int(duration_str[:-1]))
    elif duration_str.endswith('h'):
        return now + timedelta(hours=int(duration_str[:-1]))
    elif duration_str.endswith('d'):
        return now + timedelta(days=int(duration_str[:-1]))
    elif duration_str.endswith('M'):
        return now + timedelta(days=30*int(duration_str[:-1]))
    else:
        return now

async def log_action(user_id, action):
    c.execute('INSERT INTO logs (timestamp, user_id, action) VALUES (?, ?, ?)',
              (datetime.now(), user_id, action))
    conn.commit()

# ✅ ERROR HANDLER
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# ✅ VCF HELPERS
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index if start_index else 1)):
        if group_num:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
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

# ✅ KEY SYSTEM COMMANDS (OWNER ONLY)
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 1:
        await update.message.reply_text('Usage: /genkey [duration] (e.g. 1d, 5h)')
        return
    duration = context.args[0]
    key = generate_key()
    expiry = parse_duration(duration)
    c.execute('INSERT INTO keys (key, duration, expiry, used_by) VALUES (?, ?, ?, ?)',
              (key, duration, expiry, None))
    conn.commit()
    await update.message.reply_text(f'✅ Key generated: {key} (Expires: {expiry})')

async def listkeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    c.execute('SELECT key, duration, expiry, used_by FROM keys')
    rows = c.fetchall()
    msg = 'Active Keys:\n'
    for row in rows:
        msg += f'Key: {row[0]}, Duration: {row[1]}, Expiry: {row[2]}, Used By: {row[3]}\n'
    await update.message.reply_text(msg)

async def revokekey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 1:
        await update.message.reply_text('Usage: /revokekey <key>')
        return
    key = context.args[0]
    c.execute('DELETE FROM keys WHERE key = ?', (key,))
    conn.commit()
    await update.message.reply_text(f'✅ Key {key} revoked.')

async def usekey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text('Usage: /usekey <key>')
        return
    key = context.args[0]
    c.execute('SELECT expiry, used_by FROM keys WHERE key = ?', (key,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text('❌ Invalid key.')
        return
    expiry, used_by = row
    if expiry and datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S.%f') < datetime.now():
        await update.message.reply_text('❌ This key has expired.')
        return
    c.execute('INSERT OR REPLACE INTO users (user_id, username, access_level) VALUES (?, ?, ?)',
              (update.effective_user.id, update.effective_user.username, 'user'))
    c.execute('UPDATE keys SET used_by = ? WHERE key = ?', (update.effective_user.username, key))
    conn.commit()
    await update.message.reply_text('✅ Key accepted. Access granted.')
    await log_action(update.effective_user.id, f'Key {key} used')

async def adminpanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text('👑 Admin Panel Commands:\n/genkey [time]\n/listkeys\n/revokekey [key]')

# ✅ START
aSYNC_COMMANDS = "/genkey, /listkeys, /revokekey, /usekey, /adminpanel"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized. Contact the bot owner.")
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
        "/reset → sab settings default par le aao\n"
        "/mysettings → apne current settings dekho\n\n"
    )
    if update.effective_user.id == OWNER_ID:
        help_text += f"🔑 Key Commands: {aSYNC_COMMANDS}\n"

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-ddhv.onrender.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)

# ✅ FILE + TEXT HANDLERS SAME AS ORIGINAL
# (keeping existing handle_document, handle_text, process_numbers, settings, merge, etc.)
# ... (for brevity, reuse your original functions here unchanged)

# ✅ MAIN
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Old bot commands
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

    # Handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🚀 Bot is running...")
    app.run_polling()
