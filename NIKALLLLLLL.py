import os
import re
import pandas as pd
from datetime import datetime
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
OWNER_ID = 7640327597
ALLOWED_USERS = [7440046924,7669357884,7640327597,5849097477,2134530726,8128934569,7950732287,5989680310,7983528757]

# ✅ ACCESS CHECK
def is_authorized(user_id):
    return user_id in ALLOWED_USERS

def has_access_level(user_id, required_level):
    return user_id in ALLOWED_USERS

BOT_START_TIME = datetime.utcnow()

# DEFAULTS
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100
default_start_index = 1
default_vcf_start_number = 1

# USER SETTINGS
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
merge_data = {}

# VCF Generation
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=1):
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{num}\nEND:VCARD\n"
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

# ✅ NEW COMMAND: VCF TO TXT
async def vcf_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return

    if not context.args:
        await update.message.reply_text("Usage: /vcftotxt filename.vcf")
        return

    file_name = ' '.join(context.args)
    if not os.path.exists(file_name):
        await update.message.reply_text(f"File not found: {file_name}")
        return

    numbers = extract_numbers_from_vcf(file_name)
    if not numbers:
        await update.message.reply_text("No numbers found in the VCF.")
        return

    txt_file = file_name.rsplit('.', 1)[0] + ".txt"
    with open(txt_file, "w") as f:
        f.write('\n'.join(numbers))

    await update.message.reply_document(document=open(txt_file, "rb"))
    os.remove(txt_file)

# COMMANDS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized. Contact the bot owner.")
        return

    uptime_duration = datetime.utcnow() - BOT_START_TIME
    hours, rem = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    help_text = (
        "\u2620\ufe0f Welcome to the VCF Bot!\u2620\ufe0f\n\n"
        f"\ud83e\udd16 Uptime: {hours}h {minutes}m {seconds}s\n\n"
        "Available Commands:\n"
        "/setfilename  [ FILE NAME ]\n"
        "/setcontactname [ CONTACT NAME ]\n"
        "/setlimit [ PER VCF CONTACT ]\n"
        "/setstart [ CONTACT NUMBERING START ]\n"
        "/setvcfstart [ VCF NUMBERING START ]\n"
        "/makevcf [ NAME 9876543210 ]\n"
        "/merge [ VCF NAME SET ]\n"
        "/done  [ AFTER FILE SET ]\n"
        "/vcftotxt [ filename.vcf ]\n"
        "Send TXT, CSV, XLSX, or VCF files or numbers."
    )

    keyboard = [
        [InlineKeyboardButton("Help \ud83d\udcd6", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status \ud83d\udc41\ufe0f\u200d\ud83d\udca8", url="https://telegram-bot-z3zl.onrender.com/")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)

# Other command handlers remain the same
# Include all previous commands like set_filename, make_vcf_command, etc.
# Add `vcf_to_txt` to your handler list where required:

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('setfilename', set_filename))
    app.add_handler(CommandHandler('setcontactname', set_contact_name))
    app.add_handler(CommandHandler('setlimit', set_limit))
    app.add_handler(CommandHandler('setstart', set_start))
    app.add_handler(CommandHandler('setvcfstart', set_vcf_start))
    app.add_handler(CommandHandler('makevcf', make_vcf_command))
    app.add_handler(CommandHandler('merge', merge_command))
    app.add_handler(CommandHandler('done', done_merge))
    app.add_handler(CommandHandler('vcftotxt', vcf_to_txt))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()
    
