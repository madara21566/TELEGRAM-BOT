import os
import re
import pandas as pd
from datetime import datetime
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# =====================================================
# CONFIG
# =====================================================
OWNER_ID = int(os.environ.get("OWNER_ID", "7640327597"))

# 🔗 Access hook from access_system.py
def is_authorized(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    fn = context.application.bot_data.get("access_check")
    return fn(user_id) if fn else False

BOT_START_TIME = datetime.utcnow()

# =====================================================
# DEFAULTS
# =====================================================
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# =====================================================
# USER SETTINGS
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
    error_text = "".join(
        traceback.format_exception(
            None, context.error, context.error.__traceback__
        )
    )
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")

    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}"
        )
    except Exception:
        pass

# =====================================================
# HELPERS
# =====================================================
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
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    for card in content.split("END:VCARD"):
        if "TEL" in card:
            for line in card.splitlines():
                if line.startswith("TEL"):
                    number = re.sub(r"[^0-9]", "", line.split(":")[-1])
                    if number:
                        numbers.add(number)
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            numbers.update(re.findall(r"\d{7,}", line))
    return numbers

# =====================================================
# TXT2VCF / VCF2TXT
# =====================================================
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "txt2vcf"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send TXT file")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversion_mode[update.effective_user.id] = "vcf2txt"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send VCF file")

# =====================================================
# START
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # 👑 OWNER (NO KEY EVER)
    if uid == OWNER_ID:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 Admin Panel", callback_data="open_admin")]
        ])
        await update.message.reply_text(
            "☠️ Welcome to the VCF Bot ☠️\n\n👑 Full access granted",
            reply_markup=kb
        )
        return

    # ❌ UNAUTHORIZED USER
    if not is_authorized(uid, context):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Redeem Your Key", callback_data="redeem_key")]
        ])
        await update.message.reply_text(
            "❌ Access denied\n\n"
            "📂💾 VCF Bot Access\n"
            "Want my VCF Converter Bot?\n"
            "DM me anytime!\n\n"
            "📩 @MADARAXHEREE\n\n"
            "⚡ TXT ⇄ VCF | 🔒 Trusted",
            reply_markup=kb
        )
        return

    # ✅ PREMIUM USER
    uptime = datetime.utcnow() - BOT_START_TIME
    d = uptime.days
    h, rem = divmod(uptime.seconds, 3600)
    m, s = divmod(rem, 60)

    await update.message.reply_text(
        "☠️ Welcome to the VCF Bot ☠️\n\n"
        f"🤖 Uptime: {d}d {h}h {m}m {s}s\n\n"
        "📤 Send numbers or files to start."
    )

# =====================================================
# FILE HANDLER
# =====================================================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id, context):
        return

    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    user_id = update.effective_user.id

    # Merge mode
    if user_id in merge_data:
        merge_data[user_id]["files"].append(path)
        await update.message.reply_text(f"📥 Added: {file.file_name}")
        return

    # Conversion mode
    if user_id in conversion_mode:
        mode = conversion_mode[user_id]

        if mode == "txt2vcf" and path.endswith(".txt"):
            numbers = extract_numbers_from_txt(path)
            if numbers:
                name = conversion_mode.get(f"{user_id}_name", "Converted")
                vcf = generate_vcf(list(numbers), name)
                await update.message.reply_document(open(vcf, "rb"))
                os.remove(vcf)

        elif mode == "vcf2txt" and path.endswith(".vcf"):
            numbers = extract_numbers_from_vcf(path)
            if numbers:
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
        if path.endswith(".csv"):
            df = pd.read_csv(path)
        elif path.endswith(".xlsx"):
            df = pd.read_excel(path)
        elif path.endswith(".txt"):
            numbers = extract_numbers_from_txt(path)
            df = pd.DataFrame({"Numbers": list(numbers)})
        elif path.endswith(".vcf"):
            numbers = extract_numbers_from_vcf(path)
            df = pd.DataFrame({"Numbers": list(numbers)})
        else:
            await update.message.reply_text("Unsupported file type.")
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

    numbers = re.findall(r"\d{7,}", update.message.text)
    if numbers:
        await process_numbers(update, context, numbers)

# =====================================================
# PROCESS NUMBERS
# =====================================================
async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id

    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id)
    vcf_num = user_vcf_start_numbers.get(user_id)
    country_code = user_country_codes.get(user_id, "")
    group_start = user_group_start_numbers.get(user_id)

    numbers = list(dict.fromkeys(numbers))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for idx, chunk in enumerate(chunks):
        group = (group_start + idx) if group_start else None
        suffix = (vcf_num + idx) if vcf_num else (idx + 1)

        vcf = generate_vcf(
            chunk,
            f"{file_base}_{suffix}",
            contact_name,
            (start_index + idx * limit) if start_index else None,
            country_code,
            group
        )

        await update.message.reply_document(open(vcf, "rb"))
        os.remove(vcf)

# =====================================================
# SETTINGS COMMANDS (UNCHANGED)
# =====================================================
async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_file_names[update.effective_user.id] = " ".join(context.args)
        await update.message.reply_text("✅ File name updated")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_contact_names[update.effective_user.id] = " ".join(context.args)
        await update.message.reply_text("✅ Contact name updated")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ Limit updated")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ Start index updated")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ VCF numbering updated")

async def set_country_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        user_country_codes[update.effective_user.id] = context.args[0]
        await update.message.reply_text("✅ Country code updated")

async def set_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        user_group_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text("✅ Group numbering updated")

async def reset_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_file_names.pop(uid, None)
    user_contact_names.pop(uid, None)
    user_limits.pop(uid, None)
    user_start_indexes.pop(uid, None)
    user_vcf_start_numbers.pop(uid, None)
    user_country_codes.pop(uid, None)
    user_group_start_numbers.pop(uid, None)
    await update.message.reply_text("✅ Settings reset")

async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"📂 File: {user_file_names.get(uid, default_vcf_name)}\n"
        f"👤 Name: {user_contact_names.get(uid, default_contact_name)}\n"
        f"📊 Limit: {user_limits.get(uid, default_limit)}"
    )

# =====================================================
# MERGE
# =====================================================
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    merge_data[uid] = {"files": [], "filename": "_".join(context.args) if context.args else "Merged"}
    await update.message.reply_text("📂 Send files to merge, then /done")

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in merge_data:
        return

    numbers = set()
    for f in merge_data[uid]["files"]:
        if f.endswith(".vcf"):
            numbers |= extract_numbers_from_vcf(f)
        elif f.endswith(".txt"):
            numbers |= extract_numbers_from_txt(f)

    vcf = generate_vcf(list(numbers), merge_data[uid]["filename"])
    await update.message.reply_document(open(vcf, "rb"))
    os.remove(vcf)

    for f in merge_data[uid]["files"]:
        if os.path.exists(f):
            os.remove(f)

    merge_data.pop(uid)
    await update.message.reply_text("✅ Merge completed")

# =====================================================
# REGISTER HANDLERS
# =====================================================
def register_handlers(app):
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
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("done", done_merge))
    app.add_handler(CommandHandler("txt2vcf", txt2vcf))
    app.add_handler(CommandHandler("vcf2txt", vcf2txt))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
