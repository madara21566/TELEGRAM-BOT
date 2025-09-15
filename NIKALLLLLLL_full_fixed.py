import os
import re
import io
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

# CONFIG
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 7640327597
ALLOWED_USERS = [8047407478,7043391463,7440046924,7118726445,7492026653,5989680310,
                 7440046924,7669357884,7640327597,5849097477,8128934569,7950732287,
                 5989680310,7983528757,5564571047,8171988129,7770325695,7856502907]

def is_authorized(user_id):
    return user_id in ALLOWED_USERS

BOT_START_TIME = datetime.utcnow()

# defaults & per-user settings
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
conversion_mode = {}  # txt2vcf / vcf2txt

# STRICT cleaner: returns ONLY digits (enforces)
def clean_number(number: str, country_code: str = "") -> str:
    if not isinstance(number, str):
        number = str(number)
    num = re.sub(r'[^0-9]', '', number)
    if not num:
        return ""
    cc = country_code.lstrip('+') if country_code else ""
    if cc:
        if num.startswith(cc):
            return num
        if len(num) == 10:
            return cc + num
    return num

# error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {err}\n\n")
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"Bot Error:\n{err[:4000]}")
    except Exception:
        pass

# VCF generator: enforce digit-only
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    buf = io.StringIO()
    for i, raw in enumerate(numbers, start=(start_index if start_index else 1)):
        num = clean_number(raw, country_code)
        num = re.sub(r'[^0-9]', '', num)
        if not num:
            continue
        if group_num is not None:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"
        buf.write("BEGIN:VCARD\nVERSION:3.0\n")
        buf.write(f"FN:{name}\n")
        buf.write(f"TEL;TYPE=CELL:{num}\n")
        buf.write("END:VCARD\n")
    return io.BytesIO(buf.getvalue().encode('utf-8'))

def extract_numbers_from_vcf(file_path, country_code=""):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for card in content.split('END:VCARD'):
        if 'TEL' in card:
            for line in card.splitlines():
                if line.strip().upper().startswith('TEL'):
                    number = line.split(':')[-1].strip()
                    cleaned = clean_number(number, country_code)
                    cleaned = re.sub(r'[^0-9]', '', cleaned)
                    if cleaned:
                        numbers.add(cleaned)
    return numbers

def extract_numbers_from_txt(file_path, country_code=""):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            for raw in re.findall(r'\d[\d\-\+\(\) ]{6,}\d|\d{7,}', line):
                cleaned = clean_number(raw, country_code)
                cleaned = re.sub(r'[^0-9]', '', cleaned)
                if cleaned:
                    numbers.add(cleaned)
    return numbers

# commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return
    uptime = datetime.utcnow() - BOT_START_TIME
    d = uptime.days
    h, rem = divmod(uptime.seconds, 3600)
    m, s = divmod(rem, 60)
    text = (f"VCF Bot\nUptime: {d}d {h}h {m}m {s}s\n\nCommands:\n"
            "/setfilename name\n/setcontactname name\n/setlimit n\n/setstart n\n"
            "/setvcfstart n\n/setcountrycode +91\n/setgroup n\n/makevcf Name num1 num2...\n"
            "/merge -> send files -> /done\n/txt2vcf\n/vcf2txt")
    keyboard = [[InlineKeyboardButton("Help", url="https://t.me/GODMADARAVCFMAKER")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "txt2vcf"
    await update.message.reply_text("Send a .txt file to convert to VCF.")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "vcf2txt"
    await update.message.reply_text("Send a .vcf file to extract numbers.")

async def rename_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text("Filename set.")

async def rename_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text("Contact prefix set.")

# document handler
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    user_id = update.effective_user.id
    cc = user_country_codes.get(user_id, "")

    if user_id in merge_data and merge_data[user_id] is not None:
        merge_data[user_id].append(path)
        await update.message.reply_text(f"Added for merge: {file.file_name}")
        return

    if user_id in conversion_mode:
        mode = conversion_mode.pop(user_id, None)
        if mode == "txt2vcf" and path.lower().endswith('.txt'):
            nums = extract_numbers_from_txt(path, cc)
            if nums:
                vcf_buf = generate_vcf(sorted(nums), "Converted", "Contact", country_code=cc)
                await update.message.reply_document(document=vcf_buf, filename="Converted.vcf")
            else:
                await update.message.reply_text("No numbers found.")
        elif mode == "vcf2txt" and path.lower().endswith('.vcf'):
            nums = extract_numbers_from_vcf(path, cc)
            if nums:
                txt_buf = io.BytesIO("\n".join(sorted(nums)).encode('utf-8'))
                await update.message.reply_document(document=txt_buf, filename="Converted.txt")
            else:
                await update.message.reply_text("No numbers found.")
        else:
            await update.message.reply_text("Wrong file type for mode.")
        if os.path.exists(path): os.remove(path)
        return

    try:
        lower = path.lower()
        numbers = []
        if lower.endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8', dtype=str, keep_default_na=False)
            col = df.columns[0]
            for val in df[col].astype(str).tolist():
                for raw in re.findall(r'\d[\d\-\+\(\) ]{6,}\d|\d{7,}', val):
                    n = re.sub(r'[^0-9]', '', clean_number(raw, cc))
                    if n:
                        numbers.append(n)
        elif lower.endswith('.xlsx') or lower.endswith('.xls'):
            df = pd.read_excel(path, dtype=str)
            col = df.columns[0]
            for val in df[col].astype(str).tolist():
                for raw in re.findall(r'\d[\d\-\+\(\) ]{6,}\d|\d{7,}', val):
                    n = re.sub(r'[^0-9]', '', clean_number(raw, cc))
                    if n:
                        numbers.append(n)
        elif lower.endswith('.txt'):
            numbers = list(extract_numbers_from_txt(path, cc))
        elif lower.endswith('.vcf'):
            numbers = list(extract_numbers_from_vcf(path, cc))
        else:
            await update.message.reply_text("Unsupported file.")
            return
        await process_numbers(update, context, numbers)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
    finally:
        if os.path.exists(path):
            os.remove(path)

# handle plain text
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    cc = user_country_codes.get(update.effective_user.id, "")
    raw = update.message.text or ""
    found = re.findall(r'\d[\d\-\+\(\) ]{6,}\d|\d{7,}', raw)
    numbers = [re.sub(r'[^0-9]', '', clean_number(r, cc)) for r in found if r]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers.")

# process numbers to vcf
async def process_numbers(update, context, numbers):
    uid = update.effective_user.id
    contact = user_contact_names.get(uid, default_contact_name)
    file_base = user_file_names.get(uid, default_vcf_name)
    limit = user_limits.get(uid, default_limit)
    start_index = user_start_indexes.get(uid, None)
    vcf_num = user_vcf_start_numbers.get(uid, None)
    cc = user_country_codes.get(uid, "")
    group_start = user_group_start_numbers.get(uid, None)

    cleaned = []
    for n in numbers:
        n2 = re.sub(r'[^0-9]', '', clean_number(n, cc))
        if n2 and n2 not in cleaned:
            cleaned.append(n2)
    if not cleaned:
        await update.message.reply_text("No numbers to convert.")
        return

    chunks = [cleaned[i:i+limit] for i in range(0, len(cleaned), limit)]
    for idx, chunk in enumerate(chunks):
        group_num = (group_start + idx) if group_start else None
        file_suffix = (vcf_num + idx) if vcf_num else (idx+1)
        vcf_buf = generate_vcf(chunk, f"{file_base}_{file_suffix}", contact, (start_index + idx*limit) if start_index else None, cc, group_num)
        await update.message.reply_document(document=vcf_buf, filename=f"{file_base}_{file_suffix}.vcf")

# settings commands
async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text("Filename set.")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text("Contact name set.")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("Limit set.")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("Start index set.")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("VCF start set.")

async def set_country_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_country_codes[update.effective_user.id] = context.args[0].lstrip('+')
        await update.message.reply_text("Country code set.")

async def set_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_group_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("Group start set.")

async def reset_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_file_names.pop(uid, None)
    user_contact_names.pop(uid, None)
    user_limits.pop(uid, None)
    user_start_indexes.pop(uid, None)
    user_vcf_start_numbers.pop(uid, None)
    user_country_codes.pop(uid, None)
    user_group_start_numbers.pop(uid, None)
    await update.message.reply_text("Settings reset.")

async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = (f"File: {user_file_names.get(uid, default_vcf_name)}\n"
           f"Contact: {user_contact_names.get(uid, default_contact_name)}\n"
           f"Limit: {user_limits.get(uid, default_limit)}\n"
           f"Start idx: {user_start_indexes.get(uid, 'Not set')}\n"
           f"VCF start: {user_vcf_start_numbers.get(uid, 'Not set')}\n"
           f"Country code: {user_country_codes.get(uid, 'None')}\n"
           f"Group start: {user_group_start_numbers.get(uid, 'Not set')}")
    await update.message.reply_text(txt)

# makevcf command
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name num1 num2 ...")
        return
    uid = update.effective_user.id
    cc = user_country_codes.get(uid, "")
    contact = context.args[0]
    raw_numbers = context.args[1:]
    cleaned = []
    for r in raw_numbers:
        n = re.sub(r'[^0-9]', '', clean_number(r, cc))
        if n and n not in cleaned:
            cleaned.append(n)
    if not cleaned:
        await update.message.reply_text("No valid numbers.")
        return
    vcf_buf = generate_vcf(cleaned, filename=contact, contact_name=contact, country_code=cc)
    await update.message.reply_document(document=vcf_buf, filename=f"{contact}.vcf")

# merge
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    merge_data[uid] = []
    await update.message.reply_text("Send files to merge then /done.")

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in merge_data or not merge_data[uid]:
        await update.message.reply_text("No files queued.")
        return
    all_nums = set()
    for p in merge_data[uid]:
        if p.lower().endswith('.vcf'):
            all_nums.update(extract_numbers_from_vcf(p))
        elif p.lower().endswith('.txt'):
            all_nums.update(extract_numbers_from_txt(p))
        if os.path.exists(p):
            try: os.remove(p)
            except: pass
    merge_data[uid] = []
    if not all_nums:
        await update.message.reply_text("No numbers found.")
        return
    vcf_buf = generate_vcf(sorted(all_nums), "Merged", "Contact")
    await update.message.reply_document(document=vcf_buf, filename="Merged.vcf")
    await update.message.reply_text("Merge done.")

# main
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("txt2vcf", txt2vcf))
    app.add_handler(CommandHandler("vcf2txt", vcf2txt))
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
    app.add_handler(CommandHandler("renamefile", rename_file))
    app.add_handler(CommandHandler("renamecontact", rename_contact))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    print("Bot running...")
    app.run_polling()
