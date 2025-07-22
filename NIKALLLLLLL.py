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

# âœ… CONFIGURATION
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 7640327597
ALLOWED_USERS = [7440046924,7669357884,7640327597,5849097477,2134530726,8128934569,7950732287,5989680310,7983528757]

def is_authorized(user_id): return user_id in ALLOWED_USERS
def has_access_level(user_id, level): return user_id in ALLOWED_USERS

BOT_START_TIME = datetime.utcnow()

# âœ… DEFAULT SETTINGS
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100
default_start_index = 1
default_vcf_start_number = 1

user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_groups = {}
merge_data = {}

# âœ… VCF FUNCTIONS
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=1, group_suffix=""):
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index):
        name = f"{contact_name}{str(i).zfill(3)} {group_suffix}".strip()
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

# âœ… COMMAND HANDLERS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    uptime = datetime.utcnow() - BOT_START_TIME
    h, m, s = uptime.seconds // 3600, (uptime.seconds // 60) % 60, uptime.seconds % 60
    txt = (
        f"â˜ ï¸ Welcome to VCF Bot â˜ ï¸\n\nðŸ¤– Uptime: {h}h {m}m {s}s\n\n"
        "Commands:\n"
        "/setfilename [name]\n"
        "/setcontactname [name]\n"
        "/setlimit [number]\n"
        "/setstart [index]\n"
        "/setvcfstart [index]\n"
        "/makevcf [Name 9876543210]\n"
        "/merge [filename]\n"
        "/done\n"
        "/fixvcf\n"
        "/info\n"
        "/rename [newprefix]\n"
        "/vcftotxt\n"
        "/setgroup [GroupName]"
    )
    btn = [[InlineKeyboardButton("Help ðŸ“–", url="https://t.me/GODMADARAVCFMAKER")],
           [InlineKeyboardButton("Bot Status ðŸ‘ï¸â€ðŸ—¨ï¸", url="https://telegram-bot-z3zl.onrender.com/")]]
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(btn))

async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text("âœ… Filename set.")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text("âœ… Contact name set.")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("âœ… Limit set.")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("âœ… Start index set.")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("âœ… VCF start number set.")

async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_groups[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"âœ… Group suffix set: {user_groups[update.effective_user.id]}")

async def rename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_contact_names[update.effective_user.id] = context.args[0]
        await update.message.reply_text(f"âœ… Prefix renamed to: {context.args[0]}")

async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("âŒ Usage: /makevcf Name 9876543210")
        return
    name, number = context.args
    path = generate_vcf([number], name, name)
    await update.message.reply_document(open(path, "rb")); os.remove(path)

async def fix_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        await update.message.reply_text("âŒ Please send a VCF file with this command.")
        return
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    numbers = extract_numbers_from_vcf(path)
    fixed = generate_vcf(numbers, "FixedVCF")
    await update.message.reply_document(open(fixed, "rb"))
    os.remove(path); os.remove(fixed)

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        await update.message.reply_text("âŒ Please send a VCF file with this command.")
        return
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    numbers = extract_numbers_from_vcf(path)
    await update.message.reply_text(f"âœ… Total contacts: {len(numbers)}")
    os.remove(path)

async def vcf_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        await update.message.reply_text("âŒ Please send a VCF file with this command.")
        return
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    numbers = extract_numbers_from_vcf(path)
    with open("contacts.txt", "w") as f: f.write('\n'.join(sorted(numbers)))
    await update.message.reply_document(open("contacts.txt", "rb"))
    os.remove(path); os.remove("contacts.txt")
