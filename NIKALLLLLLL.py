import os
import re
import pandas as pd
from datetime import datetime
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import asyncio
import sqlite3
from collections import Counter

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
OWNER_ID = 7640327597  # Your Telegram ID
ALLOWED_USERS = [7856502907,7770325695,5564571047,7950732287,8128934569,5849097477,
                 7640327597,7669357884,5989680310,7118726445,7043391463,8047407478]

def is_authorized(user_id):
    return user_id in ALLOWED_USERS

BOT_START_TIME = datetime.utcnow()

# ==================== DEFAULTS / STATE ====================
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}  # for txt2vcf / vcf2txt

# new combine queue (per-user)
combine_queue = {}

# ==================== ERROR HANDLER ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# ==================== HELPERS ====================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    vcf_data = ""
    # If numbers is a set, convert to list but preserve ordering roughly
    nums = list(numbers)
    for i, num in enumerate(nums, start=(start_index if start_index else 1)):
        if group_num is not None:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
    path = f"{filename}.vcf"
    with open(path, "w", encoding="utf-8") as f:
        f.write(vcf_data)
    return path

def extract_numbers_from_vcf(file_path):
    numbers = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for card in content.split('END:VCARD'):
            if 'TEL' in card:
                tel_lines = [line for line in card.splitlines() if line.strip().upper().startswith('TEL')]
                for line in tel_lines:
                    number = re.sub(r'[^0-9]', '', line.split(':')[-1].strip())
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
                nums = re.findall(r'\d{7,}', line)
                numbers.update(nums)
    except Exception:
        pass
    return numbers

# ==================== TXT2VCF & VCF2TXT (with custom name support) ====================
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "txt2vcf"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a TXT file, I’ll convert it into VCF.")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "vcf2txt"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a VCF file, I’ll extract numbers into TXT.")

# ==================== START ====================
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
        "/done [ AFTER FILE SET ]\n"
        "/combine [ optional_filename ] -> send files -> /donecombine\n"
        "/analyze -> attach file to analyze\n"
        "/txt2vcf → [ Convert TXT file to VCF ]\n"
        "/vcf2txt → [ Convert VCF file to TXT ]\n\n"
        "🧹 Reset & Settings:\n"
        "/reset → sab settings default par le aao\n"
        "/mysettings → apne current settings dekho\n\n"
        "📤 Send TXT, CSV, XLSX, or VCF files or numbers."
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-ddhv.onrender.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)

# ==================== FILE HANDLER ====================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ You don't have access to use this bot.")
        return

    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    user_id = update.effective_user.id

    # combine queue support
    if user_id in combine_queue:
        combine_queue[user_id]["files"].append(path)
        await update.message.reply_text(f"📥 File added for combine: {file.file_name}")
        return

    # Merge mode
    if user_id in merge_data:
        merge_data[user_id]["files"].append(path)
        await update.message.reply_text(f"📥 File added for merge: {file.file_name}")
        return

    # Conversion modes
    if user_id in conversion_mode:
        mode = conversion_mode[user_id]

        if mode == "txt2vcf" and path.lower().endswith(".txt"):
            numbers = extract_numbers_from_txt(path)
            if numbers:
                filename = conversion_mode.get(f"{user_id}_name", "Converted")
                vcf_path = generate_vcf(list(numbers), filename, "Contact")
                await update.message.reply_document(document=open(vcf_path, "rb"))
                os.remove(vcf_path)
            else:
                await update.message.reply_text("❌ No numbers found in TXT file.")

        elif mode == "vcf2txt" and path.lower().endswith(".vcf"):
            numbers = extract_numbers_from_vcf(path)
            if numbers:
                filename = conversion_mode.get(f"{user_id}_name", "Converted")
                txt_path = f"{filename}.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(numbers))
                await update.message.reply_document(document=open(txt_path, "rb"))
                os.remove(txt_path)
            else:
                await update.message.reply_text("❌ No numbers found in VCF file.")

        else:
            await update.message.reply_text("❌ Wrong file type for this command.")

        conversion_mode.pop(user_id, None)
        conversion_mode.pop(f"{user_id}_name", None)
        if os.path.exists(path):
            os.remove(path)
        return

    # fallback: normal handling
    try:
        if path.lower().endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8', errors='ignore')
            # try to find numeric columns or anything that looks like phone numbers
            collected = []
            for col in df.columns:
                for val in df[col].astype(str):
                    collected += re.findall(r'\d{7,}', val)
            df2 = pd.DataFrame({'Numbers': collected})
            await process_numbers(update, context, df2['Numbers'].dropna().astype(str).tolist())
        elif path.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(path)
            collected = []
            for col in df.columns:
                for val in df[col].astype(str):
                    collected += re.findall(r'\d{7,}', val)
            await process_numbers(update, context, list(dict.fromkeys(collected)))
        elif path.lower().endswith('.txt'):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            numbers = [''.join(filter(str.isdigit, w)) for w in content.split() if len(re.sub(r'\D','',w)) >= 7]
            await process_numbers(update, context, numbers)
        elif path.lower().endswith('.vcf'):
            numbers = extract_numbers_from_vcf(path)
            await process_numbers(update, context, list(numbers))
        else:
            await update.message.reply_text("Unsupported file type.")
            return
    except Exception as e:
        await update.message.reply_text(f"Error processing file: {str(e)}")
    finally:
        # don't remove files that are queued for combine/merge (they are needed later)
        if user_id in combine_queue and path in combine_queue[user_id]["files"]:
            # keep
            pass
        elif user_id in merge_data and path in merge_data[user_id]["files"]:
            pass
        else:
            if os.path.exists(path):
                os.remove(path)

# ==================== HANDLE TEXT ====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(re.sub(r'\D','',w)) >=7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

# ==================== PROCESS NUMBERS ====================
async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, None)
    vcf_num = user_vcf_start_numbers.get(user_id, None)
    country_code = user_country_codes.get(user_id, "")
    custom_group_start = user_group_start_numbers.get(user_id, None)

    numbers = list(dict.fromkeys([n.strip() for n in numbers if n and n.strip().isdigit()]))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for idx, chunk in enumerate(chunks):
        group_num = (custom_group_start + idx) if custom_group_start is not None else None
        file_suffix = f"{vcf_num+idx}" if vcf_num is not None else f"{idx+1}"
        file_path = generate_vcf(
            chunk,
            f"{file_base}_{file_suffix}",
            contact_name,
            (start_index + idx*limit) if start_index is not None else None,
            country_code,
            group_num
        )
        try:
            await update.message.reply_document(document=open(file_path, "rb"))
        except Exception:
            # fallback: send as file
            await update.message.reply_text(f"VCF Generated: {file_path}")
        try:
            os.remove(file_path)
        except Exception:
            pass

# ==================== SETTINGS COMMANDS ====================
async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"✅ File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"✅ Contact name set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Limit set to: {context.args[0]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Contact numbering will start from: {context.args[0]}")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ VCF numbering will start from: {context.args[0]}")

async def set_country_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_country_codes[update.effective_user.id] = context.args[0]
        await update.message.reply_text(f"✅ Country code set to: {context.args[0]}")

async def set_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_group_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Group numbering will start from: {context.args[0]}")

async def reset_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_file_names.pop(user_id, None)
    user_contact_names.pop(user_id, None)
    user_limits.pop(user_id, None)
    user_start_indexes.pop(user_id, None)
    user_vcf_start_numbers.pop(user_id, None)
    user_country_codes.pop(user_id, None)
    user_group_start_numbers.pop(user_id, None)
    await update.message.reply_text("✅ All settings reset to default.")

async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = (
        f"📂 File name: {user_file_names.get(user_id, default_vcf_name)}\n"
        f"👤 Contact name: {user_contact_names.get(user_id, default_contact_name)}\n"
        f"📊 Limit: {user_limits.get(user_id, default_limit)}\n"
        f"🔢 Start index: {user_start_indexes.get(user_id, 'Not set')}\n"
        f"📄 VCF start: {user_vcf_start_numbers.get(user_id, 'Not set')}\n"
        f"🌍 Country code: {user_country_codes.get(user_id, 'None')}\n"
        f"📑 Group start: {user_group_start_numbers.get(user_id, 'Not set')}"
    )
    await update.message.reply_text(settings)

# ==================== MAKEVCF ====================
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name number1 number2 ...")
        return

    contact_name = context.args[0]
    numbers = context.args[1:]

    file_path = generate_vcf(numbers, contact_name, contact_name)
    await update.message.reply_document(document=open(file_path, "rb"))
    os.remove(file_path)

# ==================== MERGE ====================
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    merge_data[user_id] = {"files": [], "filename": "Merged"}  # default
    if context.args:
        merge_data[user_id]["filename"] = "_".join(context.args)
    await update.message.reply_text(
        f"📂 Send me files to merge. Final file will be: {merge_data[user_id]['filename']}.vcf\n"
        "👉 When done, use /done."
    )

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in merge_data or not merge_data[user_id]["files"]:
        await update.message.reply_text("❌ No files queued for merge.")
        return

    all_numbers = set()
    for file_path in merge_data[user_id]["files"]:
        if file_path.lower().endswith(".vcf"):
            all_numbers.update(extract_numbers_from_vcf(file_path))
        elif file_path.lower().endswith(".txt"):
            all_numbers.update(extract_numbers_from_txt(file_path))

    filename = merge_data[user_id]["filename"]
    vcf_path = generate_vcf(list(all_numbers), filename)
    await update.message.reply_document(document=open(vcf_path, "rb"))
    os.remove(vcf_path)

    for file_path in merge_data[user_id]["files"]:
        if os.path.exists(file_path):
            os.remove(file_path)
    merge_data.pop(user_id, None)

    await update.message.reply_text(f"✅ Merge completed → {filename}.vcf")

# ==================== NEW: /analyze ====================
async def analyze_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Expect user to attach file immediately with the command
    # If user sends command and then the file separately, we also support: they can send file and bot's command can be ignored.
    # Here we try to access attached document in the same message; if not present, instruct user to attach.
    if not update.message.document:
        await update.message.reply_text("📄 Attach a TXT, CSV, XLSX, or VCF file with /analyze (send the file along with the command or reply to the file with /analyze).")
        return

    file = update.message.document
    path = f"analyze_{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)

    all_numbers = []
    try:
        if path.lower().endswith('.vcf'):
            nums = extract_numbers_from_vcf(path)
            all_numbers = list(nums)
        elif path.lower().endswith('.txt'):
            nums = extract_numbers_from_txt(path)
            all_numbers = list(nums)
        elif path.lower().endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8', errors='ignore')
            for col in df.columns:
                for val in df[col].astype(str):
                    all_numbers += re.findall(r'\d{7,}', val)
        elif path.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(path)
            for col in df.columns:
                for val in df[col].astype(str):
                    all_numbers += re.findall(r'\d{7,}', val)
        else:
            await update.message.reply_text("❌ Unsupported file type for analysis.")
            return

        # normalize numbers
        all_numbers = [re.sub(r'\D', '', n) for n in all_numbers if n and re.sub(r'\D','',n)]
        total = len(all_numbers)
        unique_count = len(set(all_numbers))
        dupes = total - unique_count
        invalid = sum(1 for n in all_numbers if not n.isdigit() or len(n) < 7)

        # country-code summary heuristic (prefixes)
        prefixes = []
        for n in all_numbers:
            if len(n) >= 10:
                # take up to first 3 digits as prefix heuristic
                prefixes.append("+" + n[:3])
            elif len(n) >= 7:
                prefixes.append(n[:2])
        prefix_counts = Counter(prefixes).most_common(8)
        prefix_summary = "\n".join([f"{p[0]} → {p[1]}" for p in prefix_counts]) if prefix_counts else "None"

        result = (
            f"📊 *File Analysis*\n"
            f"──────────────────\n"
            f"📁 File: {file.file_name}\n"
            f"📱 Total numbers found: *{total}*\n"
            f"✅ Unique: *{unique_count}*\n"
            f"🔁 Duplicates: *{dupes}*\n"
            f"🚫 Invalid (non-digit or too short): *{invalid}*\n\n"
            f"🌍 *Top Prefixes/Codes:*\n{prefix_summary}"
        )
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error analyzing file: {e}")
    finally:
        if os.path.exists(path):
            os.remove(path)

# ==================== NEW: /combine and /donecombine ====================
async def combine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    combine_queue[user_id] = {"files": [], "filename": "Combined"}
    if context.args:
        combine_queue[user_id]["filename"] = "_".join(context.args)
    await update.message.reply_text(
        f"📂 Send me TXT/CSV/XLSX/VCF files to combine.\nWhen finished, use /donecombine to create merged VCF ({combine_queue[user_id]['filename']}.vcf)."
    )

async def done_combine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entry = combine_queue.get(user_id)
    if not entry or not entry.get("files"):
        await update.message.reply_text("❌ No files queued for combine.")
        return

    all_numbers = set()
    for file_path in entry["files"]:
        try:
            lower = file_path.lower()
            if lower.endswith(".vcf"):
                all_numbers.update(extract_numbers_from_vcf(file_path))
            elif lower.endswith(".txt"):
                all_numbers.update(extract_numbers_from_txt(file_path))
            elif lower.endswith(".csv"):
                try:
                    df = pd.read_csv(file_path, encoding='utf-8', errors='ignore')
                    for col in df.columns:
                        for val in df[col].astype(str):
                            all_numbers.update(re.findall(r'\d{7,}', val))
                except:
                    pass
            elif lower.endswith(('.xlsx', '.xls')):
                try:
                    df = pd.read_excel(file_path)
                    for col in df.columns:
                        for val in df[col].astype(str):
                            all_numbers.update(re.findall(r'\d{7,}', val))
                except:
                    pass
        except Exception:
            continue

    filename = entry.get("filename", "Combined")
    # cleanup numbers: digits only
    cleaned = [re.sub(r'\D', '', n) for n in all_numbers if re.sub(r'\D', '', n)]
    vcf_path = generate_vcf(cleaned, filename)
    await update.message.reply_document(document=open(vcf_path, "rb"))
    try:
        os.remove(vcf_path)
    except:
        pass

    # cleanup uploaded temp files
    for f in entry["files"]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except:
            pass
    combine_queue.pop(user_id, None)
    await update.message.reply_text(f"✅ Combine complete → {filename}.vcf")

# ==================== NEW: /broadcast (owner-only, supports text and media) ====================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Only owner can broadcast.")
        return

    # If message is a reply to media or document, we should capture that and forward
    # Parse message text from args or caption
    text = " ".join(context.args) if context.args else (update.message.caption or "")
    if not text and update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text

    # If still empty, require text
    if not text and not update.message.photo and not update.message.video and not update.message.document:
        await update.message.reply_text("Usage: /broadcast Your message here\nOr reply to a media/document with /broadcast.")
        return

    # Collect users from logs DB (same DB as main.py)
    users = []
    try:
        db = os.environ.get("DB_FILE", "bot_stats.db")
        with sqlite3.connect(db) as conn:
            c = conn.cursor()
            c.execute("SELECT DISTINCT user_id FROM logs")
            users = [row[0] for row in c.fetchall()]
    except Exception:
        users = []

    if not users:
        await update.message.reply_text("❌ No users found in DB to broadcast to.")
        return

    sent = 0
    failed = 0
    await update.message.reply_text(f"📣 Starting broadcast to {len(users)} users...")

    # Prepare media if present in command message (owner may send media with caption)
    media_to_send = None
    media_type = None
    # If the owner is replying to a message with media, use that
    source_msg = update.message.reply_to_message if update.message.reply_to_message else update.message

    # If there's a document/photo/video in the source, try to download temporarily and send as document/photo/video
    tmp_media_path = None
    try:
        if source_msg.document:
            f = source_msg.document
            tmp_media_path = f"broadcast_{f.file_unique_id}_{f.file_name}"
            await (await context.bot.get_file(f.file_id)).download_to_drive(tmp_media_path)
            media_type = "document"
        elif source_msg.photo:
            # take highest resolution photo
            p = source_msg.photo[-1]
            tmp_media_path = f"broadcast_photo_{p.file_unique_id}.jpg"
            await (await context.bot.get_file(p.file_id)).download_to_drive(tmp_media_path)
            media_type = "photo"
        elif source_msg.video:
            v = source_msg.video
            tmp_media_path = f"broadcast_video_{v.file_unique_id}.mp4"
            await (await context.bot.get_file(v.file_id)).download_to_drive(tmp_media_path)
            media_type = "video"
    except Exception:
        tmp_media_path = None
        media_type = None

    # loop users
    for uid in users:
        try:
            if media_type and tmp_media_path and os.path.exists(tmp_media_path):
                if media_type == "document":
                    await context.bot.send_document(chat_id=uid, document=open(tmp_media_path, "rb"), caption=text or None)
                elif media_type == "photo":
                    await context.bot.send_photo(chat_id=uid, photo=open(tmp_media_path, "rb"), caption=text or None)
                elif media_type == "video":
                    await context.bot.send_video(chat_id=uid, video=open(tmp_media_path, "rb"), caption=text or None)
            else:
                if text:
                    await context.bot.send_message(chat_id=uid, text=f"📢 Broadcast:\n\n{text}")
            sent += 1
            # small delay to avoid flood limits
            await asyncio.sleep(0.12)
        except Exception:
            failed += 1
            continue

    # cleanup tmp media
    try:
        if tmp_media_path and os.path.exists(tmp_media_path):
            os.remove(tmp_media_path)
    except:
        pass

    await update.message.reply_text(f"✅ Broadcast done. Sent: {sent}, Failed: {failed}")

# ==================== MAIN ====================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
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
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("done", done_merge))
    app.add_handler(CommandHandler("txt2vcf", txt2vcf))
    app.add_handler(CommandHandler("vcf2txt", vcf2txt))

    # Newly added commands
    app.add_handler(CommandHandler("analyze", analyze_file))
    app.add_handler(CommandHandler("combine", combine_command))
    app.add_handler(CommandHandler("donecombine", done_combine))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # Handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🚀 Bot is running...")
    app.run_polling()
      
