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

# ✅ CONFIGURATION
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
OWNER_ID = 7640327597  # Your Telegram ID
ALLOWED_USERS = [
    8047407478,7043391463,7440046924,7118726445,7492026653,5989680310,
    7440046924,7669357884,7640327597,5849097477,8128934569,7950732287,
    5989680310,7983528757,5564571047,8171988129
]

# ✅ ACCESS CHECK
def is_authorized(user_id):
    return user_id in ALLOWED_USERS

# BOT START TIME
BOT_START_TIME = datetime.utcnow()

# DEFAULTS
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100
default_start_index = None
default_vcf_start_number = None
default_group_start_number = None

# USER SETTINGS
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}

# ✅ ERROR HANDLER
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}"
        )
    except Exception as e:
        print("Failed to send error notification:", e)

# ✅ VCF Generation
def generate_vcf(numbers, filename="Contacts", contact_name="Contact",
                 start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index if start_index else 1)):
        if group_num:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        elif start_index:
            name = f"{contact_name}{str(i).zfill(3)}"
        else:
            name = f"{contact_name}"
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

# ✅ START
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
        "/done [ AFTER FILE SET ]\n\n"
        "🧹 Reset & Settings:\n"
        "/reset → sab settings default par le aao\n"
        "/mysettings → apne current settings dekho\n\n"
        "📤 Send TXT, CSV, XLSX, or VCF files or numbers."
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-z3zl.onrender.com/")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)

# ✅ SET COMMANDS
async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"Contact name prefix set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"VCF contact limit set to {context.args[0]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"Start index set to {context.args[0]}.")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"VCF numbering will start from {context.args[0]}.")

async def set_country_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]
        user_country_codes[update.effective_user.id] = code
        await update.message.reply_text(f"✅ Country code set to: {code}")
    else:
        await update.message.reply_text("Usage: /setcountrycode +91")

async def set_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setgroup 5")
        return
    num = int(context.args[0])
    user_group_start_numbers[update.effective_user.id] = num
    await update.message.reply_text(f"✅ Group numbering will start from: {num}")

# ✅ RESET ALL
async def reset_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_file_names.pop(user_id, None)
    user_contact_names.pop(user_id, None)
    user_limits.pop(user_id, None)
    user_start_indexes.pop(user_id, None)
    user_vcf_start_numbers.pop(user_id, None)
    user_country_codes.pop(user_id, None)
    user_group_start_numbers.pop(user_id, None)
    await update.message.reply_text("♻️ All your settings reset ho gaye!")

# ✅ SHOW CURRENT SETTINGS
async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_name = user_file_names.get(user_id, default_vcf_name)
    contact_name = user_contact_names.get(user_id, default_contact_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, None)
    vcf_start = user_vcf_start_numbers.get(user_id, None)
    country_code = user_country_codes.get(user_id, "None")
    group_start = user_group_start_numbers.get(user_id, None)

    settings_text = (
        "⚙️ **Your Current Settings** ⚙️\n\n"
        f"📂 File name: `{file_name}`\n"
        f"👤 Contact name: `{contact_name}`\n"
        f"📊 Limit per VCF: `{limit}`\n"
        f"🔢 Start index: `{start_index}`\n"
        f"📑 VCF numbering start: `{vcf_start}`\n"
        f"🌍 Country code: `{country_code}`\n"
        f"🗂️ Group start number: `{group_start}`"
    )
    await update.message.reply_text(settings_text, parse_mode="Markdown")

# ✅ MAKE VCF
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name 9876543210 9876543211 ...")
        return

    user_id = update.effective_user.id
    name = context.args[0]
    numbers = context.args[1:]

    country_code = user_country_codes.get(user_id, "")
    start_index = user_start_indexes.get(user_id, None)
    vcf_num = user_vcf_start_numbers.get(user_id, None)
    group_num = user_group_start_numbers.get(user_id, None)

    numbers = list(dict.fromkeys([n.strip() for n in numbers if n.strip().isdigit()]))

    if not numbers:
        await update.message.reply_text("⚠️ No valid numbers provided.")
        return

    file_name = f"{name}_{vcf_num if vcf_num else 1}.vcf"
    vcf_data = ""

    for i, num in enumerate(numbers, start=(start_index if start_index else 1)):
        if group_num:
            contact_name = f"{name}{str(i).zfill(3)} (Group {group_num})"
        elif start_index:
            contact_name = f"{name}{str(i).zfill(3)}"
        else:
            contact_name = f"{name}"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += (
            f"BEGIN:VCARD\nVERSION:3.0\nFN:{contact_name}\n"
            f"TEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
        )

    with open(file_name, "w") as f:
        f.write(vcf_data)

    await update.message.reply_document(document=open(file_name, "rb"))
    os.remove(file_name)

# ✅ MAIN
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('setfilename', set_filename))
    app.add_handler(CommandHandler('setcontactname', set_contact_name))
    app.add_handler(CommandHandler('setlimit', set_limit))
    app.add_handler(CommandHandler('setstart', set_start))
    app.add_handler(CommandHandler('setvcfstart', set_vcf_start))
    app.add_handler(CommandHandler('setcountrycode', set_country_code))
    app.add_handler(CommandHandler('setgroup', set_group_number))
    app.add_handler(CommandHandler('reset', reset_settings))
    app.add_handler(CommandHandler('mysettings', my_settings))
    app.add_handler(CommandHandler('makevcf', make_vcf_command))
    app.add_error_handler(error_handler)
    app.run_polling()
    
