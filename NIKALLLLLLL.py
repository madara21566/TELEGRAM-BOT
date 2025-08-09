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
    OWNER_ID = int(os.environ.get("OWNER_ID", "7640327597"))
except Exception:
    OWNER_ID = 7640327597

# Pre-seeded allowed users (keeps existing behavior)
ALLOWED_USERS = [7043391463,7440046924,7118726445,7492026653,7440046924,7669357884,7640327597,5849097477,8128934569,7950732287,5989680310,7983528757,5564571047]
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
    # permanent list
    if user_id in ALLOWED_USERS:
        return True
    exp = access_expirations.get(user_id)
    if exp and exp > now_utc():
        return True
    # expired: cleanup
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

# ----------------- COMMAND HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("Unauthorized. Contact the bot owner.")
        return

    uptime_duration = now_utc() - BOT_START_TIME
    hours, rem = divmod(int(uptime_duration.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)

    help_text = (
        "☠️ Welcome to the VCF Bot! (updated) ☠️\n\n"
        f"🤖 Uptime: {hours}h {minutes}m {seconds}s\n\n"
        "Available Commands:\n"
        "/setfilename [ FILE NAME ]\n"
        "/setcontactname [ CONTACT NAME ]\n"
        "/setgroup [ GROUP NAME ]    - append group to each contact's name\n"
        "/setlimit [ PER VCF CONTACT ]\n"
        "/setstart [ CONTACT NUMBERING START ]\n"
        "/setvcfstart [ VCF NUMBERING START ]\n"
        "/makevcf [ NAME 9876543210 ]\n"
        "/merge [ VCF_NAME ]  then send files and /done\n"
        "/info  - send a VCF file with this command to get detailed info\n"
        "/fixvcf - send a VCF file with this command to get cleaned VCF (duplicates removed)\n"
        "/vcftotxt - send a VCF file with this command to receive a TXT of numbers\n"
        "/txttovcf - send a TXT file with this command to receive a VCF\n"
        "/grant <id1> [id2 id3 ...] [minutes=60] - grant access (minutes optional)\n"
        "/revoke <id1> [id2 ...] - revoke access\n"
        "/listaccess - show allowed users and temporary grants\n"
    )
    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)

async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"Contact name prefix set to: {' '.join(context.args)}")

async def set_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if context.args:
        user_group_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"Group name set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"VCF contact limit set to {context.args[0]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"Start index set to {context.args[0]}.")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"VCF numbering will start from {context.args[0]}.")

async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name 9876543210")
        return
    name = context.args[0]
    number = ''.join(re.findall(r'\d+', ' '.join(context.args[1:])))
    if not number or len(number) < 7:
        await update.message.reply_text("Invalid phone number.")
        return
    file_name = f"{name}.vcf"
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{number}\nEND:VCARD\n")
    await update.message.reply_document(document=open(file_name, "rb"))
    try:
        os.remove(file_name)
    except Exception:
        pass

async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /merge output_filename")
        return
    output_name = context.args[0]
    user_id = update.effective_user.id
    merge_data[user_id] = {'output_name': output_name, 'numbers': set()}
    await update.message.reply_text(
        f"Merge started. Send VCF/TXT/CSV/XLSX files. Final file: {output_name}.vcf\nSend /done when ready."
    )

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in merge_data:
        await update.message.reply_text("No active merge session.")
        return
    session = merge_data[user_id]
    if not session['numbers']:
        await update.message.reply_text("No numbers found in merge session.")
        del merge_data[user_id]
        return
    output_path = f"{session['output_name']}.vcf"
    contact_name = user_contact_names.get(user_id, default_contact_name)
    start_index = user_start_indexes.get(user_id, default_start_index)
    group = user_group_names.get(user_id)
    numbers = sorted(session['numbers'])
    out = generate_vcf(numbers, session['output_name'], contact_name, start_index, group)
    await update.message.reply_document(document=open(out, 'rb'))
    try:
        os.remove(out)
    except Exception:
        pass
    await update.message.reply_text("Merge complete.")
    del merge_data[user_id]

# Document handlers and command-mode flags
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    file = update.message.document
    user_id = update.effective_user.id
    temp_dir = tempfile.gettempdir()
    safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', file.file_name)
    path = os.path.join(temp_dir, f"{file.file_unique_id}_{safe_name}")
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)

    # remember last uploaded file for this user (used by renamefile)
    user_last_uploaded_file[user_id] = path

    mode = user_command_mode.get(user_id)

    # merge mode handling
    if user_id in merge_data:
        file_ext = path.split('.')[-1].lower()
        numbers = set()
        if file_ext == 'vcf':
            numbers = extract_numbers_from_vcf(path)
        elif file_ext == 'txt':
            numbers = extract_numbers_from_txt(path)
        elif file_ext == 'csv':
            try:
                df = pd.read_csv(path, encoding='utf-8', low_memory=False)
                for col in df.columns:
                    vals = df[col].astype(str).tolist()
                    for v in vals:
                        nums = re.findall(r'\d{7,}', v)
                        numbers.update(nums)
            except Exception:
                pass
        elif file_ext in ('xls','xlsx'):
            try:
                df = pd.read_excel(path)
                for col in df.columns:
                    vals = df[col].astype(str).tolist()
                    for v in vals:
                        nums = re.findall(r'\d{7,}', v)
                        numbers.update(nums)
            except Exception:
                pass
        else:
            await update.message.reply_text("Only VCF, TXT, CSV, XLSX supported in merge mode.")
            try:
                os.remove(path)
            except Exception:
                pass
            return
        merge_data[user_id]['numbers'].update(numbers)
        await update.message.reply_text(f"Added {len(numbers)} numbers to merge. Send /done to finish.")
        try:
            os.remove(path)
        except Exception:
            pass
        return

    # If user invoked /info or /fixvcf or vcftotxt or txttovcf, perform action
    if mode == 'info':
        details = extract_details_from_vcf(path)
        total_cards = details['total_cards']
        unique = len(details['unique_numbers'])
        dup = details['duplicate_numbers']
        emails = len(details['emails'])
        avg_name_len = (sum(details['name_lengths'])/len(details['name_lengths'])) if details['name_lengths'] else 0
        msg = (
            f"📄 File: {os.path.basename(path)}\n"
            f"👥 Total vCards: {total_cards}\n"
            f"🔢 Unique phone numbers: {unique}\n"
            f"⚠️ Duplicate phone entries: {dup}\n"
            f"✉️ Contacts with email: {emails}\n"
            f"🔤 Avg name length: {avg_name_len:.1f}\n"
        )
        await update.message.reply_text(msg)
        user_command_mode[user_id] = None
        try:
            os.remove(path)
        except Exception:
            pass
        return

    if mode == 'fixvcf':
        details = extract_details_from_vcf(path)
        numbers = sorted(details['unique_numbers'])
        contact_name = user_contact_names.get(user_id, default_contact_name)
        start_index = user_start_indexes.get(user_id, default_start_index)
        group = user_group_names.get(user_id)
        out_name = user_file_names.get(user_id, default_vcf_name) + "_fixed"
        out_path = generate_vcf(numbers, out_name, contact_name, start_index, group)
        await update.message.reply_document(document=open(out_path, 'rb'))
        await update.message.reply_text(f"Fixed VCF created: {os.path.basename(out_path)}")
        user_command_mode[user_id] = None
        try:
            os.remove(path)
            os.remove(out_path)
        except Exception:
            pass
        return

    if mode == 'vcftotxt':
        numbers = extract_numbers_from_vcf(path)
        out_path = txt_from_numbers(sorted(numbers), filename=user_file_names.get(user_id, 'numbers'))
        await update.message.reply_document(document=open(out_path, 'rb'))
        user_command_mode[user_id] = None
        try:
            os.remove(path)
            os.remove(out_path)
        except Exception:
            pass
        return

    if mode == 'txttovcf':
        numbers = extract_numbers_from_txt(path)
        contact_name = user_contact_names.get(user_id, default_contact_name)
        start_index = user_start_indexes.get(user_id, default_start_index)
        out_name = user_file_names.get(user_id, default_vcf_name)
        group = user_group_names.get(user_id)
        out_path = generate_vcf(sorted(numbers), out_name, contact_name, start_index, group)
        await update.message.reply_document(document=open(out_path, 'rb'))
        user_command_mode[user_id] = None
        try:
            os.remove(path)
            os.remove(out_path)
        except Exception:
            pass
        return

    # Default: general file processing (try to extract numbers and make vcf chunks)
    try:
        file_ext = path.split('.')[-1].lower()
        numbers = []
        if file_ext == 'csv':
            df = pd.read_csv(path, encoding='utf-8', low_memory=False)
            for col in df.columns:
                values = df[col].astype(str).tolist()
                for v in values:
                    nums = re.findall(r'\d{7,}', v)
                    numbers.extend(nums)
        elif file_ext in ('xls','xlsx'):
            df = pd.read_excel(path)
            for col in df.columns:
                values = df[col].astype(str).tolist()
                for v in values:
                    nums = re.findall(r'\d{7,}', v)
                    numbers.extend(nums)
        elif file_ext == 'txt':
            numbers = [''.join(filter(str.isdigit, w)) for w in open(path, 'r', encoding='utf-8', errors='ignore').read().split() if len(''.join(filter(str.isdigit, w))) >=7]
        elif file_ext == 'vcf':
            numbers = list(extract_numbers_from_vcf(path))
        else:
            await update.message.reply_text("Unsupported file type.")
            try:
                os.remove(path)
            except Exception:
                pass
            return
        await process_numbers(update, context, numbers)
    except Exception as e:
        await update.message.reply_text(f"Error processing file: {e}")
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    text = update.message.text.strip()

    # commands that switch next document mode
    if text.lower().startswith('/info'):
        user_command_mode[update.effective_user.id] = 'info'
        await update.message.reply_text("Send the VCF file you want info about.")
        return
    if text.lower().startswith('/fixvcf'):
        user_command_mode[update.effective_user.id] = 'fixvcf'
        await update.message.reply_text("Send the VCF file to fix (duplicates will be removed).")
        return
    if text.lower().startswith('/vcftotxt'):
        user_command_mode[update.effective_user.id] = 'vcftotxt'
        await update.message.reply_text("Send the VCF file to convert to TXT.")
        return
    if text.lower()
