import os
import re
import tempfile
import logging
from datetime import datetime, timedelta
from typing import Set, List, Dict, Optional

import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------- CONFIG -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
try:
    OWNER_ID = os.environ.get("OWNER_ID")
except Exception:
    OWNER_ID = None  # fallback if not found

# Pre-seeded allowed users (keeps existing behavior)
ALLOWED_USERS = [7043391463,7440046924,7118726445,7492026653,7440046924,7669357884,7640327597,5849097477,8128934569,7950732287,7983528757,5564571047]
# Temporary access expirations: user_id -> datetime when access expires (or removed)
access_expirations: Dict[int, Optional[datetime]] = {}

# ----------------- DEFAULTS & USER STATE -----------------
BOT_START_TIME = datetime.utcnow()

default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100
default_start_index = 1
default_vcf_start_number = 1

# Per-user settings and transient state
user_file_names: Dict[int, str] = {}
user_contact_names: Dict[int, str] = {}
user_limits: Dict[int, int] = {}
user_start_indexes: Dict[int, int] = {}
user_vcf_start_numbers: Dict[int, int] = {}
user_group_names: Dict[int, str] = {}
merge_data: Dict[int, Dict] = {}
user_last_uploaded_file: Dict[int, str] = {}
user_command_mode: Dict[int, Optional[str]] = {}  # 'info','fixvcf','vcftotxt','txttovcf'

# ----------------- LOGGING -----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------- HELPERS -----------------
def now_utc():
    return datetime.utcnow()

def is_authorized(user_id: int) -> bool:
    if user_id in ALLOWED_USERS:
        return True
    exp = access_expirations.get(user_id)
    if exp and exp > now_utc():
        return True
    if exp and exp <= now_utc():
        access_expirations.pop(user_id, None)
    return False

def grant_access(user_ids: List[int], duration_minutes: Optional[int] = None):
    for uid in user_ids:
        if duration_minutes is None:
            if uid not in ALLOWED_USERS:
                ALLOWED_USERS.append(uid)
            access_expirations.pop(uid, None)
        else:
            access_expirations[uid] = now_utc() + timedelta(minutes=duration_minutes)

def revoke_access(user_ids: List[int]):
    for uid in user_ids:
        if uid in ALLOWED_USERS:
            try:
                ALLOWED_USERS.remove(uid)
            except ValueError:
                pass
        access_expirations.pop(uid, None)

# ----------------- VCF / TXT utilities -----------------
def generate_vcf(numbers: List[str], filename: str = "Contacts", contact_name: str = "Contact", start_index: int = 1, group: Optional[str] = None) -> str:
    vcf_data = ""
    for i, num in enumerate(numbers, start=start_index):
        name = f"{contact_name}{str(i).zfill(3)}"
        if group:
            name = f"{name} {group}"
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{num}\nEND:VCARD\n"
    path = f"{filename}.vcf"
    with open(path, "w", encoding="utf-8") as f:
        f.write(vcf_data)
    return path

def extract_numbers_from_vcf(file_path: str) -> Set[str]:
    numbers = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return set()
    for card in content.split('END:VCARD'):
        if not card.strip():
            continue
        for line in card.splitlines():
            if line.upper().startswith('TEL'):
                num = re.sub(r'[^0-9]', '', line.split(':')[-1].strip())
                if num:
                    numbers.add(num)
    return numbers

def extract_details_from_vcf(file_path: str) -> Dict:
    details = {
        'total_cards': 0,
        'unique_numbers': set(),
        'duplicate_numbers': 0,
        'names': [],
        'emails': set(),
        'name_lengths': []
    }
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return details
    cards = [c for c in content.split('END:VCARD') if c.strip()]
    details['total_cards'] = len(cards)
    for card in cards:
        fn_lines = [l for l in card.splitlines() if l.upper().startswith('FN:')]
        name = fn_lines[0].split(':',1)[1].strip() if fn_lines else ''
        if name:
            details['names'].append(name)
            details['name_lengths'].append(len(name))
        tel_lines = [line for line in card.splitlines() if line.upper().startswith('TEL')]
        for line in tel_lines:
            number = re.sub(r'[^0-9]', '', line.split(':')[-1].strip())
            if number:
                if number in details['unique_numbers']:
                    details['duplicate_numbers'] += 1
                details['unique_numbers'].add(number)
        em_lines = [l for l in card.splitlines() if l.upper().startswith('EMAIL')]
        for el in em_lines:
            parts = el.split(':', 1)
            if len(parts) > 1:
                details['emails'].add(parts[1].strip())
    return details

def extract_numbers_from_txt(file_path: str) -> Set[str]:
    numbers = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                nums = re.findall(r'\d{7,}', line)
                numbers.update(nums)
    except Exception:
        pass
    return numbers

def txt_from_numbers(numbers: List[str], filename: str = 'numbers') -> str:
    path = f"{filename}.txt"
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(numbers))
    return path

# --------- All command handler functions from your original code stay same here ---------
# (start, set_filename, set_contact_name, set_group_name, set_limit, set_start, set_vcf_start,
# make_vcf_command, merge_command, done_merge, handle_document, handle_text, process_numbers,
# grant_command, revoke_command, listaccess_command, rename_in_file_command)

# ----------------- STARTUP -----------------
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set. Exiting.")
        return

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('setfilename', set_filename))
    app.add_handler(CommandHandler('setcontactname', set_contact_name))
    app.add_handler(CommandHandler('setgroup', set_group_name))
    app.add_handler(CommandHandler('setlimit', set_limit))
    app.add_handler(CommandHandler('setstart', set_start))
    app.add_handler(CommandHandler('setvcfstart', set_vcf_start))
    app.add_handler(CommandHandler('makevcf', make_vcf_command))
    app.add_handler(CommandHandler('merge', merge_command))
    app.add_handler(CommandHandler('done', done_merge))
    app.add_handler(CommandHandler('grant', grant_command))
    app.add_handler(CommandHandler('revoke', revoke_command))
    app.add_handler(CommandHandler('listaccess', listaccess_command))
    app.add_handler(CommandHandler('renamefile', rename_in_file_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot starting...")
    app.run_polling()
