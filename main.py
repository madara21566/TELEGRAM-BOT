import os
import re
import pandas as pd
from datetime import datetime
import tempfile
import threading
import uvicorn
from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# === FastAPI health check for Render ===
fastapi_app = FastAPI()

@fastapi_app.get("/")
def root():
    return {"status": "Bot is running"}

def run_web():
    port = int(os.environ.get("PORT", 10000))  # Important for Render
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)

# === Bot Configuration ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "VCF_Bot")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing from environment variables.")

OWNER_ID = 7640327597
ALLOWED_USERS = [
    7440046924, 7669357884, 7640327597, 5849097477,
    2134530726, 8128934569, 7950732287, 5989680310, 7983528757
]

# Bot state
BOT_START_TIME = datetime.utcnow()
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100
default_start_index = 1
default_vcf_start_number = 1

# User settings
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
merge_data = {}

# === Utility Functions ===
def is_authorized(user_id): return user_id in ALLOWED_USERS
def has_access_level(user_id, level): return is_authorized(user_id)

def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=1):
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{num}\nEND:VCARD\n"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".vcf", mode="w", encoding="utf-8") as tmp:
        tmp.write(vcf_data)
        return tmp.name

def extract_numbers_from_vcf(file_path):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for card in content.split('END:VCARD'):
        for line in card.splitlines():
            if line.startswith('TEL'):
                number = re.sub(r'[^0-9]', '', line.split(':')[-1].strip())
                if number:
                    numbers.add(number)
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            numbers.update(re.findall(r'\d{7,}', line))
    return numbers

# === Telegram Bot Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized. Contact the bot owner.")
        return

    uptime = datetime.utcnow() - BOT_START_TIME
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    text = (
        "✨ Welcome to the VCF Bot! ✨\n\n"
        f"🕐 Uptime: {hours}h {minutes}m {seconds}s\n\n"
        "📌 Available Commands:\n"
        "/setfilename [file name]\n"
        "/setcontactname [contact name]\n"
        "/setlimit [contacts per file]\n"
        "/setstart [start index]\n"
        "/setvcfstart [vcf file number]\n"
        "/makevcf [Name 9876543210]\n"
        "/merge [output file name]\n"
        "/done to complete merge\n\n"
        "Send TXT, CSV, XLSX, or VCF files, or paste numbers directly."
    )

    keyboard = [
        [InlineKeyboardButton("Help 📘", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot Status 🔗", url="https://telegram-bot-z3zl.onrender.com/")]
    ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if has_access_level(update.effective_user.id, 1) and context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"✅ File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if has_access_level(update.effective_user.id, 1) and context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"✅ Contact name set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if has_access_level(update.effective_user.id, 1) and context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Limit set to {context.args[0]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if has_access_level(update.effective_user.id, 1) and context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Start index set to {context.args[0]}")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if has_access_level(update.effective_user.id, 1) and context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ VCF file number start set to {context.args[0]}")

async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if has_access_level(update.effective_user.id, 1) and len(context.args) == 2:
        name, number = context.args
        if number.isdigit():
            path = generate_vcf([number], name, name, 1)
            await update.message.reply_document(document=open(path, "rb"))
            os.remove(path)
        else:
            await update.message.reply_text("⚠️ Invalid number.")
    else:
        await update.message.reply_text("Usage: /makevcf Name 9876543210")

async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if has_access_level(update.effective_user.id, 1) and context.args:
        merge_data[update.effective_user.id] = {'output_name': context.args[0], 'numbers': set()}
        await update.message.reply_text("📥 Merge started. Send VCF or TXT files. Use /done when done.")

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = merge_data.get(user_id)
    if not session or not session['numbers']:
        await update.message.reply_text("❌ No numbers to merge.")
        merge_data.pop(user_id, None)
        return
    contact_name = user_contact_names.get(user_id, default_contact_name)
    start_index = user_start_indexes.get(user_id, default_start_index)
    file_path = generate_vcf(sorted(session['numbers']), session['output_name'], contact_name, start_index)
    await update.message.reply_document(document=open(file_path, 'rb'))
    os.remove(file_path)
    await update.message.reply_text("✅ Merge complete.")
    del merge_data[user_id]

# === File/Text Handlers ===
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    ext = path.split('.')[-1].lower()

    if update.effective_user.id in merge_data:
        if ext == 'vcf':
            numbers = extract_numbers_from_vcf(path)
        elif ext == 'txt':
            numbers = extract_numbers_from_txt(path)
        else:
            await update.message.reply_text("Only VCF and TXT supported in merge mode.")
            os.remove(path)
            return
        merge_data[update.effective_user.id]['numbers'].update(numbers)
        await update.message.reply_text(f"➕ Added {len(numbers)} numbers.")
        os.remove(path)
        return

    try:
        if ext == 'csv':
            df = pd.read_csv(path)
        elif ext == 'xlsx':
            df = pd.read_excel(path)
        elif ext == 'txt':
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            numbers = [''.join(filter(str.isdigit, word)) for word in content.split() if len(word) >= 7]
            df = pd.DataFrame({'Numbers': numbers})
        elif ext == 'vcf':
            numbers = extract_numbers_from_vcf(path)
            df = pd.DataFrame({'Numbers': list(numbers)})
        else:
            await update.message.reply_text("❌ Unsupported file format.")
            return
        await process_numbers(update, context, df['Numbers'].dropna().astype(str).tolist())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        if os.path.exists(path):
            os.remove(path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(w) >= 7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("❌ No valid numbers found.")

async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, default_start_index)
    vcf_num = user_vcf_start_numbers.get(user_id, default_vcf_start_number)

    numbers = list(dict.fromkeys([n.strip() for n in numbers if n.strip().isdigit()]))
    chunks = [numbers[i:i + limit] for i in range(0, len(numbers), limit)]

    for idx, chunk in enumerate(chunks):
        file_path = generate_vcf(chunk, f"{file_base}_{vcf_num + idx}", contact_name, start_index + idx * limit)
        await update.message.reply_document(document=open(file_path, "rb"))
        os.remove(file_path)

# === Main Entry Point ===
if __name__ == '__main__':
    threading.Thread(target=run_web).start()

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
