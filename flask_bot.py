import os
import re
import csv
import time
import pandas as pd
from datetime import datetime
from collections import defaultdict
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.helpers import mention_html
from io import StringIO

# Load token from environment
TOKEN = os.getenv("7727685861:AAE_tR7qsTx-_NlxfwQ-JgqeJDkpvnXEYkg")
OWNER_ID = 7640327597  # Replace with your actual Telegram user ID
bot = Bot(token=TOKEN)

app = Flask(__name__)
application = ApplicationBuilder().token(TOKEN).build()

# Default settings
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100
default_start_index = 1
default_vcf_start_number = 1

# Data structures
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
merge_data = {}
user_access = defaultdict(dict)  # {user_id: {'level': int, 'expiry': datetime/None}}
TEMP_USERS = {}
GROUP_ADMINS = set()

# Access levels
ACCESS_LEVELS = {
    'admin': 3,
    'editor': 2,
    'viewer': 1
}

def is_authorized(user_id):
    """Check if user has access to the bot"""
    if user_id == OWNER_ID:
        return True
    if user_id in GROUP_ADMINS:
        return True
    if user_id in TEMP_USERS and TEMP_USERS[user_id] > time.time():
        return True
    if user_id in user_access:
        access = user_access[user_id]
        if access['expiry'] and datetime.now() > access['expiry']:
            del user_access[user_id]
            return False
        return True
    TEMP_USERS.pop(user_id, None)
    return False

def has_access_level(user_id, required_level):
    """Check if user has sufficient access level"""
    if user_id == OWNER_ID:
        return True
    if user_id in GROUP_ADMINS:
        return True
    if user_id in user_access:
        return user_access[user_id]['level'] >= required_level
    return False

def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=1):
    """Generate VCF file from list of numbers"""
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{num}\nEND:VCARD\n"
    with open(f"{filename}.vcf", "w") as f:
        f.write(vcf_data)
    return f"{filename}.vcf"

def extract_numbers_from_vcf(file_path):
    """Extract phone numbers from a VCF file"""
    numbers = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for card in content.split('END:VCARD'):
        if 'TEL' in card:
            tel_lines = [line for line in card.splitlines() if line.startswith('TEL')]
            for line in tel_lines:
                number = line.split(':')[-1].strip()
                number = re.sub(r'[^0-9]', '', number)  # Clean the number
                if number:
                    numbers.add(number)
    return numbers

def extract_numbers_from_txt(file_path):
    """Extract phone numbers from a TXT file"""
    numbers = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line_numbers = re.findall(r'\d{7,}', line)
            numbers.update(line_numbers)
    return numbers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized. Please contact the bot owner.")
        return
    
    help_text = """Welcome to the VCF Bot!

Available Commands:
/setfilename <name> - Set VCF filename prefix
/setcontactname <name> - Set contact name prefix
/setlimit <number> - Limit contacts per VCF
/setstart <number> - Start index for contact numbering
/setvcfstart <number> - VCF file numbering start
/makevcf Name 9876543210 - Create single VCF
/merge output_name - Start merging VCF/TXT files
/done - Complete merge operation
/panel - Owner/Admin control panel

Send a TXT, CSV, XLSX, or VCF file or plain numbers to generate contacts."""
    
    await update.message.reply_text(help_text)

# ... [Rest of your functions remain unchanged] ...

@app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    application.process_update(update)
    return "ok"

@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
