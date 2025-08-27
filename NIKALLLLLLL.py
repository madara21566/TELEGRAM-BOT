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
ALLOWED_USERS = [8047407478,7043391463,7440046924,7118726445,7492026653,5989680310,
                 7440046924,7669357884,7640327597,5849097477,8128934569,7950732287,
                 5989680310,7983528757,5564571047,8171988129]

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

# ✅ VCF Generation (no default group text)
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=1, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index):
        if group_num is not None:  # only add group if explicitly set
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"
        formatted_num = f"{country_code}{num}" if country_code else num
        for number in numbers:
    vcf_data += (
        "BEGIN:VCARD\n"
        "VERSION:3.0\n"
        f"N:{contact_name}\n"
        f"TEL;TYPE=CELL:{number}\n"
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

# ✅ START
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
        "📌 Available Commands:\n"
        "/setfilename [ FILE NAME ]\n"
        "/setcontactname [ CONTACT NAME ]\n"
        "/setlimit [ PER VCF CONTACT ]\n"
        "/setstart [ CONTACT NUMBERING START ]\n"
        "/setvcfstart [ VCF NUMBERING START ]\n"
        "/setcountrycode [ +91 / +1 / +44 ]\n"
        "/setgroup [ START NUMBER ]\n"
        "/makevcf [ NAME 9876543210 ]\n"
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
    await update.message.reply_text(
        "♻️ All your settings reset ho gaye!\n\n"
        "🔹 Now using defaults:\n"
        f"- File name: {default_vcf_name}\n"
        f"- Contact name: {default_contact_name}\n"
        f"- Limit: {default_limit}\n"
        f"- Start index: {default_start_index}\n"
        f"- VCF start: {default_vcf_start_number}\n"
        f"- Country code: None\n"
        f"- Group start: 1"
    )

# ✅ SHOW CURRENT SETTINGS
async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_name = user_file_names.get(user_id, default_vcf_name)
    contact_name = user_contact_names.get(user_id, default_contact_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, default_start_index)
    vcf_start = user_vcf_start_numbers.get(user_id, default_vcf_start_number)
    country_code = user_country_codes.get(user_id, "None")
    group_start = user_group_start_numbers.get(user_id, 1)

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

# ✅ MAKE VCF (Multi-number support)
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name 9876543210 8765432109 ...")
        return
    
    name = context.args[0]
    numbers = context.args[1:]
    numbers = [n for n in numbers if n.isdigit()]  # filter valid numbers

    if not numbers:
        await update.message.reply_text("No valid phone numbers found.")
        return

    country_code = user_country_codes.get(update.effective_user.id, "")
    vcf_file = f"{name}.vcf"

    with open(vcf_file, "w") as f:
        for i, num in enumerate(numbers, start=1):
            formatted_num = f"{country_code}{num}" if country_code else num
            f.write(
                f"BEGIN:VCARD
VERSION:3.0
FN:{name}{str(i).zfill(3)}
TEL;TYPE=CELL:{formatted_num}
END:VCARD
"
            )

    await update.message.reply_document(document=open(vcf_file, "rb"))
    os.remove(vcf_file)


# ✅ MERGE MODE
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    country_code = user_country_codes.get(user_id, "")
    vcf_data = ""
    for i, num in enumerate(sorted(session['numbers']), start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
    with open(output_path, 'w') as f:
        f.write(vcf_data)
    await update.message.reply_document(document=open(output_path, 'rb'))
    os.remove(output_path)
    await update.message.reply_text("Merge complete.")
    del merge_data[user_id]

# ✅ FILE HANDLING
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
                numbers = [''.join(filter(str.isdigit, w)) for w in content.split() if len(w) >=7]
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

# ✅ HANDLE TEXT
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(w) >=7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

# ✅ PROCESS NUMBERS
async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, default_start_index)
    vcf_num = user_vcf_start_numbers.get(user_id, default_vcf_start_number)
    country_code = user_country_codes.get(user_id, "")
    custom_group_start = user_group_start_numbers.get(user_id, 1)

    numbers = list(dict.fromkeys([n.strip() for n in numbers if n.strip().isdigit()]))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for idx, chunk in enumerate(chunks):
        group_num = custom_group_start + idx
        file_path = generate_vcf(
            chunk,
            f"{file_base}_{vcf_num+idx}",
            contact_name,
            start_index+idx*limit,
            country_code,
            group_num
        )
        await update.message.reply_document(document=open(file_path, "rb"))
        os.remove(file_path)

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
    app.add_handler(CommandHandler('merge', merge_command))
    app.add_handler(CommandHandler('done', done_merge))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    app.run_polling()
    
