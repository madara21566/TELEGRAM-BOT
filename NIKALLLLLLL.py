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
OWNER_ID = 7640327597  # Your Telegram ID
ALLOWED_USERS = [6808159551,7440046924,7669357884,7640327597,5849097477,2134530726,8128934569,7950732287,5989680310]

# ✅ ACCESS CHECK
def is_authorized(user_id):
    return user_id in ALLOWED_USERS

def has_access_level(user_id, required_level):
    return user_id in ALLOWED_USERS

# BOT START TIME
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

# COMMANDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized. Contact the bot owner.")
        return

    uptime_duration = datetime.utcnow() - BOT_START_TIME
    hours, rem = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    help_text = (
        "☠️ Welcome to the VCF Bot!☠️\n\n"
        f"🤖 Uptime: {hours}h {minutes}m {seconds}s\n\n"
        "Available Commands:\n"
        "/setfilename  [ FILE NAME ]\n"
        "/setcontactname [ CONTACT NAME ]\n"
        "/setlimit [ PER VCF CONTACT ]\n"
        "/setstart [ CONTACT NUMBERING START ]\n"
        "/setvcfstart [ VCF NUMBERING START ]\n"
        "/makevcf [ NAME 9876543210 ]\n"
        "/merge [ VCF NAME SET ]\n"
        "/done  [ AFTER FILE SET ]\n"
        "Send TXT, CSV, XLSX, or VCF files or numbers."
        
        "If you are not able to use the bot then click on the help button, full details are there🤫."
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("About ℹ️", url="https://t.me/godmadara1")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)

async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access_level(update.effective_user.id, 1): return
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access_level(update.effective_user.id, 1): return
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"Contact name prefix set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access_level(update.effective_user.id, 1): return
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"VCF contact limit set to {context.args[0]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access_level(update.effective_user.id, 1): return
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"Start index set to {context.args[0]}.")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access_level(update.effective_user.id, 1): return
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"VCF numbering will start from {context.args[0]}.")

async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access_level(update.effective_user.id, 1): return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /makevcf Name 9876543210")
        return
    name, number = context.args
    if not number.isdigit():
        await update.message.reply_text("Invalid phone number.")
        return
    file_name = f"{name}.vcf"
    with open(file_name, "w") as f:
        f.write(f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{number}\nEND:VCARD\n")
    await update.message.reply_document(document=open(file_name, "rb"))
    os.remove(file_name)

async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access_level(update.effective_user.id, 1): return
    if not context.args:
        await update.message.reply_text("Usage: /merge output_filename")
        return
    output_name = context.args[0]
    user_id = update.effective_user.id
    merge_data[user_id] = {'output_name': output_name, 'numbers': set()}
    await update.message.reply_text(
        f"Merge started. Send VCF or TXT files.\nFinal file: {output_name}.vcf\nSend /done when ready."
    )

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in merge_data:
        await update.message.reply_text("No active merge session.")
        return
    session = merge_data[user_id]
    if not session['numbers']:
        await update.message.reply_text("No numbers found.")
        del merge_data[user_id]
        return
    output_path = f"{session['output_name']}.vcf"
    contact_name = user_contact_names.get(user_id, default_contact_name)
    start_index = user_start_indexes.get(user_id, default_start_index)
    vcf_data = ""
    for i, num in enumerate(sorted(session['numbers']), start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{num}\nEND:VCARD\n"
    with open(output_path, 'w') as f:
        f.write(vcf_data)
    await update.message.reply_document(document=open(output_path, 'rb'))
    os.remove(output_path)
    await update.message.reply_text("Merge complete.")
    del merge_data[user_id]

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return

    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)

    file_ext = path.split('.')[-1].lower()

    if update.effective_user.id in merge_data:
        if file_ext == 'vcf':
            numbers = extract_numbers_from_vcf(path)
        elif file_ext == 'txt':
            numbers = extract_numbers_from_txt(path)
        else:
            await update.message.reply_text("Only VCF and TXT supported in merge mode.")
            os.remove(path)
            return
        merge_data[update.effective_user.id]['numbers'].update(numbers)
        os.remove(path)
        await update.message.reply_text(f"Added {len(numbers)} numbers. Send /done to finish.")
        return

    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8')
        elif path.endswith('.xlsx'):
            df = pd.read_excel(path)
        elif path.endswith('.txt'):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(path, 'r', encoding='latin-1') as f:
                    content = f.read()
            numbers = [''.join(filter(str.isdigit, w)) for w in content.split() if len(w) >=7]
            df = pd.DataFrame({'Numbers': numbers})
        elif path.endswith('.vcf'):
            numbers = extract_numbers_from_vcf(path)
            df = pd.DataFrame({'Numbers': list(numbers)})
        else:
            await update.message.reply_text("Unsupported file type.")
            return
        await process_numbers(update, context, df['Numbers'].dropna().astype(str).tolist())
    except Exception as e:
        await update.message.reply_text(f"Error processing file: {str(e)}")
    finally:
        if os.path.exists(path):
            os.remove(path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(w) >=7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, default_start_index)
    vcf_num = user_vcf_start_numbers.get(user_id, default_vcf_start_number)
    numbers = list(dict.fromkeys([n.strip() for n in numbers if n.strip().isdigit()]))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]
    for idx, chunk in enumerate(chunks):
        file_path = generate_vcf(chunk, f"{file_base}_{vcf_num+idx}", contact_name, start_index+idx*limit)
        await update.message.reply_document(document=open(file_path, "rb"))
        os.remove(file_path)

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
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()
