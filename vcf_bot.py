import os
import re
import pandas as pd
from datetime import datetime
import traceback
from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# =====================================================
# ACCESS HOOK (IMPORTANT)
# main.py yaha function inject karega
# =====================================================
def access_check(user_id: int) -> bool:
    """
    Ye function main.py se override hoga.
    Default: sabko allow (standalone testing ke liye)
    """
    return True

def is_authorized(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    fn = context.application.bot_data.get("access_check", access_check)
    return fn(user_id)

# =====================================================
# BOT START TIME
# =====================================================
BOT_START_TIME = datetime.utcnow()

# =====================================================
# DEFAULT SETTINGS
# =====================================================
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# =====================================================
# USER SETTINGS (IN-MEMORY)
# =====================================================
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}

# =====================================================
# ERROR HANDLER
# =====================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = "".join(
        traceback.format_exception(None, context.error, context.error.__traceback__)
    )
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {err}\n\n")

# =====================================================
# VCF HELPERS
# =====================================================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact",
                 start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index or 1)):
        name = f"{contact_name}{str(i).zfill(3)}"
        if group_num:
            name += f" (Group {group_num})"
        formatted = f"{country_code}{num}" if country_code else num
        vcf_data += (
            "BEGIN:VCARD\nVERSION:3.0\n"
            f"FN:{name}\n"
            f"TEL;TYPE=CELL:{formatted}\n"
            "END:VCARD\n"
        )

    path = f"{filename}.vcf"
    with open(path, "w") as f:
        f.write(vcf_data)
    return path

def extract_numbers_from_vcf(file_path):
    numbers = set()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("TEL"):
                num = re.sub(r"\D", "", line)
                if len(num) >= 7:
                    numbers.add(num)
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            for n in re.findall(r"\d{7,}", line):
                numbers.add(n)
    return numbers

# =====================================================
# START
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id, context):
        await update.message.reply_text("❌ Access denied. Please redeem key.")
        return

    uptime = datetime.utcnow() - BOT_START_TIME
    msg = (
        "☠️ VCF BOT ☠️\n\n"
        f"⏱ Uptime: {uptime}\n\n"
        "📌 Commands:\n"
        "/setfilename\n"
        "/setcontactname\n"
        "/setlimit\n"
        "/setstart\n"
        "/setvcfstart\n"
        "/setcountrycode\n"
        "/setgroup\n"
        "/makevcf\n"
        "/merge + /done\n"
        "/txt2vcf\n"
        "/vcf2txt\n"
        "/mysettings\n"
        "/reset\n\n"
        "📤 Send numbers or files"
    )
    await update.message.reply_text(msg)

# =====================================================
# FILE HANDLER
# =====================================================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id, context):
        await update.message.reply_text("❌ Access denied.")
        return

    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    uid = update.effective_user.id

    if uid in merge_data:
        merge_data[uid]["files"].append(path)
        await update.message.reply_text("📥 File added for merge")
        return

    if uid in conversion_mode:
        mode = conversion_mode.pop(uid)

        if mode == "txt2vcf" and path.endswith(".txt"):
            nums = extract_numbers_from_txt(path)
            if nums:
                p = generate_vcf(list(nums))
                await update.message.reply_document(open(p, "rb"))
                os.remove(p)

        elif mode == "vcf2txt" and path.endswith(".vcf"):
            nums = extract_numbers_from_vcf(path)
            if nums:
                out = "numbers.txt"
                with open(out, "w") as f:
                    f.write("\n".join(nums))
                await update.message.reply_document(open(out, "rb"))
                os.remove(out)

        os.remove(path)
        return

    try:
        if path.endswith(".csv"):
            df = pd.read_csv(path)
        elif path.endswith(".xlsx"):
            df = pd.read_excel(path)
        elif path.endswith(".txt"):
            nums = extract_numbers_from_txt(path)
            df = pd.DataFrame({"Numbers": list(nums)})
        elif path.endswith(".vcf"):
            nums = extract_numbers_from_vcf(path)
            df = pd.DataFrame({"Numbers": list(nums)})
        else:
            await update.message.reply_text("❌ Unsupported file")
            return

        await process_numbers(update, context, df["Numbers"].astype(str).tolist())

    finally:
        if os.path.exists(path):
            os.remove(path)

# =====================================================
# TEXT HANDLER
# =====================================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id, context):
        return
    nums = re.findall(r"\d{7,}", update.message.text)
    if nums:
        await process_numbers(update, context, nums)

# =====================================================
# PROCESS NUMBERS
# =====================================================
async def process_numbers(update, context, numbers):
    uid = update.effective_user.id
    numbers = list(dict.fromkeys(numbers))

    limit = user_limits.get(uid, default_limit)
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for i, chunk in enumerate(chunks):
        path = generate_vcf(chunk)
        await update.message.reply_document(open(path, "rb"))
        os.remove(path)

# =====================================================
# SETTINGS COMMANDS
# =====================================================
async def set_filename(update, context):
    if context.args:
        user_file_names[update.effective_user.id] = " ".join(context.args)
        await update.message.reply_text("✅ Filename set")

async def set_contact_name(update, context):
    if context.args:
        user_contact_names[update.effective_user.id] = " ".join(context.args)
        await update.message.reply_text("✅ Contact name set")

async def set_limit(update, context):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ Limit set")

async def reset_settings(update, context):
    uid = update.effective_user.id
    user_file_names.pop(uid, None)
    user_contact_names.pop(uid, None)
    user_limits.pop(uid, None)
    await update.message.reply_text("✅ Settings reset")

async def my_settings(update, context):
    uid = update.effective_user.id
    msg = (
        f"File: {user_file_names.get(uid, default_vcf_name)}\n"
        f"Contact: {user_contact_names.get(uid, default_contact_name)}\n"
        f"Limit: {user_limits.get(uid, default_limit)}"
    )
    await update.message.reply_text(msg)

# =====================================================
# TXT ↔ VCF
# =====================================================
async def txt2vcf(update, context):
    if not is_authorized(update.effective_user.id, context): return
    conversion_mode[update.effective_user.id] = "txt2vcf"
    await update.message.reply_text("📂 Send TXT file")

async def vcf2txt(update, context):
    if not is_authorized(update.effective_user.id, context): return
    conversion_mode[update.effective_user.id] = "vcf2txt"
    await update.message.reply_text("📂 Send VCF file")

# =====================================================
# MERGE
# =====================================================
async def merge(update, context):
    uid = update.effective_user.id
    merge_data[uid] = {"files": []}
    await update.message.reply_text("📂 Send files to merge, then /done")

async def done(update, context):
    uid = update.effective_user.id
    if uid not in merge_data:
        await update.message.reply_text("❌ Nothing to merge")
        return

    nums = set()
    for f in merge_data[uid]["files"]:
        if f.endswith(".vcf"):
            nums |= extract_numbers_from_vcf(f)
        elif f.endswith(".txt"):
            nums |= extract_numbers_from_txt(f)

    path = generate_vcf(list(nums), "Merged")
    await update.message.reply_document(open(path, "rb"))
    os.remove(path)

    for f in merge_data[uid]["files"]:
        if os.path.exists(f): os.remove(f)
    merge_data.pop(uid, None)

# =====================================================
# REGISTER HANDLERS (IMPORTANT)
# =====================================================
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setfilename", set_filename))
    app.add_handler(CommandHandler("setcontactname", set_contact_name))
    app.add_handler(CommandHandler("setlimit", set_limit))
    app.add_handler(CommandHandler("reset", reset_settings))
    app.add_handler(CommandHandler("mysettings", my_settings))
    app.add_handler(CommandHandler("txt2vcf", txt2vcf))
    app.add_handler(CommandHandler("vcf2txt", vcf2txt))
    app.add_handler(CommandHandler("merge", merge))
    app.add_handler(CommandHandler("done", done))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
