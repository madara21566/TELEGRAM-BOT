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

BOT_START_TIME = datetime.utcnow()

# ✅ DEFAULTS
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# ✅ USER SETTINGS
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}

# ✅ ERROR HANDLER (NO ACCESS / OWNER CHECK)
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(
        traceback.format_exception(
            None, context.error, context.error.__traceback__
        )
    )
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")

# ✅ HELPERS
def generate_vcf(numbers, filename="Contacts", contact_name="Contact",
                 start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index if start_index else 1)):
        if group_num:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"

        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += (
            "BEGIN:VCARD\n"
            "VERSION:3.0\n"
            f"FN:{name}\n"
            f"TEL;TYPE=CELL:{formatted_num}\n"
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
        for line in card.splitlines():
            if line.startswith('TEL'):
                num = re.sub(r'[^0-9]', '', line.split(':')[-1])
                if num:
                    numbers.add(num)
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            nums = re.findall(r'\d{7,}', line)
            numbers.update(nums)
    return numbers

# ✅ TXT2VCF / VCF2TXT
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "txt2vcf"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 TXT file bhejo, VCF bana dunga.")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "vcf2txt"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 VCF file bhejo, TXT bana dunga.")

# ✅ START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    h, r = divmod(uptime.seconds, 3600)
    m, s = divmod(r, 60)

    text = (
        "☠️ GOD MADARA VCF BOT ☠️\n\n"
        f"⏱ Uptime: {uptime.days}d {h}h {m}m {s}s\n\n"
        "📌 Commands:\n"
        "/setfilename\n"
        "/setcontactname\n"
        "/setlimit\n"
        "/setstart\n"
        "/setvcfstart\n"
        "/setcountrycode\n"
        "/setgroup\n"
        "/makevcf\n"
        "/merge\n"
        "/done\n"
        "/txt2vcf\n"
        "/vcf2txt\n\n"
        "📤 TXT / CSV / XLSX / VCF bhejo"
    )

    await update.message.reply_text(text)

# ✅ DOCUMENT HANDLER
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)

    user_id = update.effective_user.id

    if user_id in merge_data:
        merge_data[user_id]["files"].append(path)
        await update.message.reply_text("📥 Merge queue me add ho gaya")
        return

    if user_id in conversion_mode:
        mode = conversion_mode[user_id]

        if mode == "txt2vcf" and path.endswith(".txt"):
            numbers = extract_numbers_from_txt(path)
            name = conversion_mode.get(f"{user_id}_name", "Converted")
            vcf = generate_vcf(list(numbers), name)
            await update.message.reply_document(open(vcf, "rb"))
            os.remove(vcf)

        elif mode == "vcf2txt" and path.endswith(".vcf"):
            numbers = extract_numbers_from_vcf(path)
            name = conversion_mode.get(f"{user_id}_name", "Converted")
            txt = f"{name}.txt"
            with open(txt, "w") as f:
                f.write("\n".join(numbers))
            await update.message.reply_document(open(txt, "rb"))
            os.remove(txt)

        conversion_mode.pop(user_id, None)
        conversion_mode.pop(f"{user_id}_name", None)
        os.remove(path)
        return

    try:
        if path.endswith(".vcf"):
            nums = extract_numbers_from_vcf(path)
        elif path.endswith(".txt"):
            nums = extract_numbers_from_txt(path)
        elif path.endswith(".csv"):
            nums = pd.read_csv(path).iloc[:, 0].astype(str).tolist()
        elif path.endswith(".xlsx"):
            nums = pd.read_excel(path).iloc[:, 0].astype(str).tolist()
        else:
            await update.message.reply_text("❌ Unsupported file")
            return

        await process_numbers(update, context, nums)

    finally:
        if os.path.exists(path):
            os.remove(path)

# ✅ TEXT HANDLER
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nums = re.findall(r'\d{7,}', update.message.text)
    if nums:
        await process_numbers(update, context, nums)
    else:
        await update.message.reply_text("❌ Number nahi mila")

# ✅ PROCESS NUMBERS
async def process_numbers(update, context, numbers):
    uid = update.effective_user.id
    base = user_file_names.get(uid, default_vcf_name)
    cname = user_contact_names.get(uid, default_contact_name)
    limit = user_limits.get(uid, default_limit)
    start = user_start_indexes.get(uid)
    vcf_start = user_vcf_start_numbers.get(uid)
    code = user_country_codes.get(uid, "")
    group = user_group_start_numbers.get(uid)

    numbers = list(dict.fromkeys(numbers))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for i, chunk in enumerate(chunks):
        fname = f"{base}_{(vcf_start+i) if vcf_start else (i+1)}"
        vcf = generate_vcf(
            chunk, fname, cname,
            (start + i*limit) if start else None,
            code,
            (group + i) if group else None
        )
        await update.message.reply_document(open(vcf, "rb"))
        os.remove(vcf)

# ✅ SETTINGS COMMANDS
async def set_filename(update, context):
    user_file_names[update.effective_user.id] = " ".join(context.args)

async def set_contact_name(update, context):
    user_contact_names[update.effective_user.id] = " ".join(context.args)

async def set_limit(update, context):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])

async def set_start(update, context):
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])

async def set_vcf_start(update, context):
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])

async def set_country_code(update, context):
    if context.args:
        user_country_codes[update.effective_user.id] = context.args[0]

async def set_group_number(update, context):
    if context.args and context.args[0].isdigit():
        user_group_start_numbers[update.effective_user.id] = int(context.args[0])

# ✅ MERGE
async def merge_command(update, context):
    merge_data[update.effective_user.id] = {
        "files": [],
        "filename": "_".join(context.args) if context.args else "Merged"
    }
    await update.message.reply_text("📂 Files bhejo, /done likho jab khatam")

async def done_merge(update, context):
    uid = update.effective_user.id
    files = merge_data.get(uid)
    if not files:
        return

    nums = set()
    for f in files["files"]:
        if f.endswith(".vcf"):
            nums.update(extract_numbers_from_vcf(f))
        elif f.endswith(".txt"):
            nums.update(extract_numbers_from_txt(f))

    vcf = generate_vcf(list(nums), files["filename"])
    await update.message.reply_document(open(vcf, "rb"))
    os.remove(vcf)

    for f in files["files"]:
        if os.path.exists(f):
            os.remove(f)

    merge_data.pop(uid, None)

# ✅ MAIN
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setfilename", set_filename))
    app.add_handler(CommandHandler("setcontactname", set_contact_name))
    app.add_handler(CommandHandler("setlimit", set_limit))
    app.add_handler(CommandHandler("setstart", set_start))
    app.add_handler(CommandHandler("setvcfstart", set_vcf_start))
    app.add_handler(CommandHandler("setcountrycode", set_country_code))
    app.add_handler(CommandHandler("setgroup", set_group_number))
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("done", done_merge))
    app.add_handler(CommandHandler("txt2vcf", txt2vcf))
    app.add_handler(CommandHandler("vcf2txt", vcf2txt))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🚀 Bot Running (Public Access)")
    app.run_polling()
