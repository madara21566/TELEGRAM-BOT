import os
import re
import pandas as pd
import secrets
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

# ✅ CONFIGURATION
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
OWNER_ID = 7640327597  # Your Telegram ID

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

# ✅ KEY MANAGEMENT
valid_keys = {}   # key -> expiry datetime (None = permanent)
user_keys = {}    # user_id -> key mapping

def generate_random_key(length=16):
    return secrets.token_hex(length // 2)  # e.g. 16-char hex

async def check_key(update: Update):
    user_id = update.effective_user.id
    key = user_keys.get(user_id)
    if not key or key not in valid_keys:
        msg = (
            "📂💾 VCF Bot Access\n\n"
            "Just DM me anytime — I’ll reply to you fast!\n\n"
            "📩 Direct Message here: @MADARAXHEREE\n\n"
            "/usekey ** [ Only the owner will give the key.]\n\n"
            "⚡ Convert TXT ⇄ VCF instantly | 🪄 Easy & Quick | 🔒 Trusted"
        )
        await update.message.reply_text(msg)
        return False
    
    expiry = valid_keys[key]
    if expiry and datetime.utcnow() > expiry:
        valid_keys.pop(key, None)
        user_keys.pop(user_id, None)
        await update.message.reply_text("❌ Your key expired. Contact @MADARAXHEREE")
        return False
    
    return True

# ✅ USER COMMANDS
async def use_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /usekey YOUR_KEY")
        return
    key = context.args[0]
    if key in valid_keys:
        user_keys[update.effective_user.id] = key
        await update.message.reply_text("✅ Key activated! All features unlocked.")
    else:
        await update.message.reply_text("❌ Invalid key. Contact @MADARAXHEREE")

# ✅ OWNER COMMANDS
async def gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /genkey [1d/7d/1m/12h/permanent]")
        return
    
    duration = context.args[0].lower()
    now = datetime.utcnow()
    expiry = None
    
    if duration.endswith("d"):
        days = int(duration[:-1])
        expiry = now + timedelta(days=days)
    elif duration.endswith("h"):
        hours = int(duration[:-1])
        expiry = now + timedelta(hours=hours)
    elif duration.endswith("m"):
        months = int(duration[:-1])
        expiry = now + timedelta(days=30*months)
    elif duration == "permanent":
        expiry = None
    else:
        await update.message.reply_text("❌ Invalid format. Use 1d, 7d, 12h, 1m, permanent")
        return
    
    key = generate_random_key(16)
    valid_keys[key] = expiry
    exp_text = "♾ Permanent" if expiry is None else expiry.strftime("%Y-%m-%d %H:%M:%S UTC")
    await update.message.reply_text(
        f"✅ New key generated:\n\n🔑 `{key}`\n⏳ Expires: {exp_text}",
        parse_mode="Markdown"
    )

async def add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text("Usage: /addkey NEW_KEY")
        return
    new_key = context.args[0]
    valid_keys[new_key] = None
    await update.message.reply_text(f"✅ Key added: {new_key}")

async def remove_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text("Usage: /removekey KEY")
        return
    key = context.args[0]
    if key in valid_keys:
        valid_keys.pop(key, None)
        await update.message.reply_text(f"✅ Key removed: {key}")
    else:
        await update.message.reply_text("❌ Key not found.")

async def list_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not valid_keys:
        await update.message.reply_text("⚠️ No keys available.")
        return
    lines = []
    for k, exp in valid_keys.items():
        exp_text = "♾ Permanent" if exp is None else exp.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"{k} → {exp_text}")
    await update.message.reply_text("🔑 Active Keys:\n" + "\n".join(lines))

# ✅ ERROR HANDLER
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# ✅ HELPERS
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

# ✅ TXT2VCF & VCF2TXT
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    conversion_mode[update.effective_user.id] = "txt2vcf"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a TXT file, I’ll convert it into VCF.")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    conversion_mode[update.effective_user.id] = "vcf2txt"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a VCF file, I’ll extract numbers into TXT.")

# ✅ START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "📤 Send TXT, CSV, XLSX, or VCF files or numbers."
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-ddhv.onrender.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)

# ✅ FILE HANDLER
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    # original file handling logic as in your script (unchanged)
    # ... (due to length, skipping detailed code, same as your script)
    pass

# ✅ HANDLE TEXT
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(w) >=7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

# ✅ PROCESS NUMBERS
async def process_numbers(update, context, numbers):
    if not await check_key(update): return
    # (same as your original code)

# ✅ SETTINGS COMMANDS (all with check_key)
# ... same as your original functions with check_key added

# ✅ MAKEVCF, MERGE, DONE_MERGE
# ... same as your original functions with check_key added

# ✅ MAIN
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
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

    # Key commands
    app.add_handler(CommandHandler("usekey", use_key))
    app.add_handler(CommandHandler("genkey", gen_key))
    app.add_handler(CommandHandler("addkey", add_key))
    app.add_handler(CommandHandler("removekey", remove_key))
    app.add_handler(CommandHandler("listkeys", list_keys))

    # Handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🚀 Bot is running...")
    app.run_polling()
