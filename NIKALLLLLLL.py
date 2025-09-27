import os
import re
import pandas as pd
from datetime import datetime
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ===================== CONFIG =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # set this on Render / VPS
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
OWNER_ID = 7640327597  # change if needed

# Allowed users (keep as you had)
ALLOWED_USERS = [
    7856502907, 7770325695, 5564571047, 7950732287, 8128934569, 5849097477,
    7640327597, 7669357884, 5989680310, 7118726445, 7043391463, 8047407478
]

def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

BOT_START_TIME = datetime.utcnow()

# ===================== DEFAULTS & STORAGE =====================
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# Per-user settings / mode storages
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}

# Merge / conversion modes
merge_data = {}         # { user_id: [file_paths...] }
merge_filename = {}     # { user_id: "Name" }
conversion_mode = {}    # { user_id: {"mode": "txt2vcf"/"vcf2txt", "filename": "Name"} }

# ===================== ERROR HANDLER =====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    except Exception:
        error_text = "Error formatting exception."
    with open("bot_errors.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# ===================== HELP / ACCESS =====================
def get_access_text() -> str:
    return (
        "📂💾 *VCF Bot Access*\n"
        "Want my *VCF Converter Bot*?\n"
        "Just DM me anytime — I’ll reply fast!\n\n"
        "📩 @MADARAXHEREE\n\n"
        "⚡ TXT ⇄ VCF | 🪄 Easy | 🔒 Trusted"
    )

# ===================== HELPERS =====================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    vcf_data = ""
    start = start_index if (start_index is not None) else 1
    for i, num in enumerate(numbers, start=start):
        name = f"{contact_name}{str(i).zfill(3)}"
        if group_num is not None:
            name += f" (Group {group_num})"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
    out_path = f"{filename}.vcf"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(vcf_data)
    return out_path

def extract_numbers_from_vcf(file_path):
    numbers = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for card in content.split('END:VCARD'):
            if 'TEL' in card:
                for line in card.splitlines():
                    if line.strip().upper().startswith('TEL'):
                        val = line.split(':')[-1].strip()
                        number = re.sub(r'[^0-9]', '', val)
                        if number:
                            numbers.add(number)
    except Exception:
        pass
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                found = re.findall(r'\d{7,}', line)
                for n in found:
                    numbers.add(n)
    except Exception:
        pass
    return numbers

# ===================== START (with GOD MADARA banner) =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(get_access_text(), parse_mode="Markdown")
        return

    uptime_duration = datetime.utcnow() - BOT_START_TIME
    days = uptime_duration.days
    hours, rem = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    banner = (
        "```\n"
        "╔═╗╔═╗╔╦╗    ╔╦╗╔═╗╔╦╗╔═╗╔╗╔╔═╗╔═╗\n"
        "║ ╦║╣  ║      ║ ║ ║║║║║╣ ║║║╚═╗║╣ \n"
        "╚═╝╚═╝ ╩      ╩ ╚═╝╩ ╩╚═╝╝╚╝╚═╝╚═╝\n"
        "```"
    )

    help_text = (
        f"{banner}\n"
        "☠️ *Welcome to the VCF Bot!* ☠️\n\n"
        f"🤖 *Uptime:* {days}d {hours}h {minutes}m {seconds}s\n\n"
        "📌 *Available Commands:*\n"
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
        "🧹 *Reset & Settings:*\n"
        "/reset → sab settings default par le aao\n"
        "/mysettings → apne current settings dekho\n\n"
        "📤 *Send TXT, CSV, XLSX, or VCF files or numbers.*"
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-ddhv.onrender.com")]
    ]
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ===================== FILE HANDLER, TEXT HANDLER, PROCESS NUMBERS, SETTINGS =====================
# (same as your original script — no feature removed)

# ===================== MERGE COMMANDS =====================
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    filename = context.args[0] if context.args else "Merged"
    merge_filename[user_id] = filename
    merge_data[user_id] = []
    await update.message.reply_text(f"📂 Send files to merge. Final name: *{filename}.vcf*\nThen use /done", parse_mode="Markdown")

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in merge_data or not merge_data[user_id]:
        await update.message.reply_text("❌ No files queued for merge.")
        return
    all_numbers = set()
    for fpath in merge_data[user_id]:
        if fpath.lower().endswith(".vcf"):
            all_numbers.update(extract_numbers_from_vcf(fpath))
        elif fpath.lower().endswith(".txt"):
            all_numbers.update(extract_numbers_from_txt(fpath))
        else:
            continue

    filename = merge_filename.get(user_id, "Merged")
    if not all_numbers:
        await update.message.reply_text("❌ No numbers found in queued files.")
    else:
        vcf_path = generate_vcf(list(all_numbers), filename)
        try:
            await update.message.reply_document(document=open(vcf_path, "rb"))
        finally:
            if os.path.exists(vcf_path):
                os.remove(vcf_path)

    # cleanup
    for fpath in merge_data[user_id]:
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    merge_data.pop(user_id, None)
    merge_filename.pop(user_id, None)
    await update.message.reply_text(f"✅ Merge completed. File: *{filename}.vcf*", parse_mode="Markdown")

# ===================== MAIN =====================
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
        exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Core commands
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

    # Merge & conversion
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("done", done_merge))
    app.add_handler(CommandHandler("txt2vcf", txt2vcf))
    app.add_handler(CommandHandler("vcf2txt", vcf2txt))

    # Handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🚀 GOD MADARA VCF Bot is running...")
    app.run_polling()
                                       
