import os
import re
import pandas as pd
from datetime import datetime
import traceback
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
OWNER_ID = 7640327597

BOT_START_TIME = datetime.utcnow()

# ================= FLASK (RENDER) =================
web = Flask(__name__)

@web.route("/")
def home():
    return "VCF BOT RUNNING OK"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web.run(host="0.0.0.0", port=port)

# ================= DEFAULTS =================
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# ================= USER SETTINGS =================
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}

# ================= ERROR HANDLER =================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    error_text = "".join(
        traceback.format_exception(None, context.error, context.error.__traceback__)
    )
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"⚠️ BOT ERROR ⚠️\n\n{error_text[:4000]}"
        )
    except:
        pass

# ================= HELPERS =================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact",
                 start_index=None, country_code="", group_num=None):

    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index or 1)):
        name = f"{contact_name}{str(i).zfill(3)}"
        if group_num:
            name += f" (Group {group_num})"

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
        for line in card.splitlines():
            if line.startswith("TEL"):
                num = re.sub(r"\D", "", line.split(":")[-1])
                if num:
                    numbers.add(num)
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            numbers.update(re.findall(r"\d{7,}", line))
    return numbers

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    d, s = uptime.days, uptime.seconds
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)

    text = (
        "☠️ VCF MAKER BOT ☠️\n\n"
        f"⏱ Uptime: {d}d {h}h {m}m {s}s\n\n"
        "📌 Commands:\n"
        "/setfilename\n"
        "/setcontactname\n"
        "/setlimit\n"
        "/setstart\n"
        "/setvcfstart\n"
        "/setcountrycode\n"
        "/setgroup\n"
        "/makevcf\n"
        "/merge → /done\n"
        "/txt2vcf\n"
        "/vcf2txt\n"
        "/reset\n"
        "/mysettings\n\n"
        "📤 Send TXT / CSV / XLSX / VCF / Numbers"
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Owner 💀", url="https://madara21566.github.io/GODMADARA-PROFILE/")]
    ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ================= CONVERT COMMANDS =================
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

# ================= FILE HANDLER =================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    user_id = update.effective_user.id

    if user_id in merge_data:
        merge_data[user_id]["files"].append(path)
        await update.message.reply_text("📥 File added for merge")
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
        if path.endswith(".csv"):
            df = pd.read_csv(path)
        elif path.endswith(".xlsx"):
            df = pd.read_excel(path)
        elif path.endswith(".txt"):
            df = pd.DataFrame({"Numbers": list(extract_numbers_from_txt(path))})
        elif path.endswith(".vcf"):
            df = pd.DataFrame({"Numbers": list(extract_numbers_from_vcf(path))})
        else:
            return

        await process_numbers(update, context, df["Numbers"].astype(str).tolist())
    finally:
        os.remove(path)

# ================= TEXT =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    numbers = re.findall(r"\d{7,}", update.message.text)
    if numbers:
        await process_numbers(update, context, numbers)

# ================= PROCESS =================
async def process_numbers(update, context, numbers):
    uid = update.effective_user.id

    contact_name = user_contact_names.get(uid, default_contact_name)
    base = user_file_names.get(uid, default_vcf_name)
    limit = user_limits.get(uid, default_limit)
    start = user_start_indexes.get(uid)
    vcf_start = user_vcf_start_numbers.get(uid)
    code = user_country_codes.get(uid, "")
    group = user_group_start_numbers.get(uid)

    numbers = list(dict.fromkeys(numbers))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for i, chunk in enumerate(chunks):
        file_no = (vcf_start + i) if vcf_start else i + 1
        grp = (group + i) if group else None
        path = generate_vcf(
            chunk,
            f"{base}_{file_no}",
            contact_name,
            (start + i * limit) if start else None,
            code,
            grp
        )
        await update.message.reply_document(open(path, "rb"))
        os.remove(path)

# ================= SETTINGS =================
async def set_filename(update, context):
    user_file_names[update.effective_user.id] = " ".join(context.args)

async def set_contact_name(update, context):
    user_contact_names[update.effective_user.id] = " ".join(context.args)

async def set_limit(update, context):
    user_limits[update.effective_user.id] = int(context.args[0])

async def set_start(update, context):
    user_start_indexes[update.effective_user.id] = int(context.args[0])

async def set_vcf_start(update, context):
    user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])

async def set_country_code(update, context):
    user_country_codes[update.effective_user.id] = context.args[0]

async def set_group_number(update, context):
    user_group_start_numbers[update.effective_user.id] = int(context.args[0])

async def reset_settings(update, context):
    uid = update.effective_user.id
    for d in [user_file_names, user_contact_names, user_limits,
              user_start_indexes, user_vcf_start_numbers,
              user_country_codes, user_group_start_numbers]:
        d.pop(uid, None)

async def my_settings(update, context):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"File: {user_file_names.get(uid, default_vcf_name)}\n"
        f"Contact: {user_contact_names.get(uid, default_contact_name)}\n"
        f"Limit: {user_limits.get(uid, default_limit)}"
    )

# ================= MERGE =================
async def merge_command(update, context):
    uid = update.effective_user.id
    merge_data[uid] = {"files": [], "filename": "Merged"}
    if context.args:
        merge_data[uid]["filename"] = "_".join(context.args)
    await update.message.reply_text("📂 Send files then /done")

async def done_merge(update, context):
    uid = update.effective_user.id
    if uid not in merge_data:
        return

    numbers = set()
    for f in merge_data[uid]["files"]:
        if f.endswith(".vcf"):
            numbers |= extract_numbers_from_vcf(f)
        elif f.endswith(".txt"):
            numbers |= extract_numbers_from_txt(f)

    name = merge_data[uid]["filename"]
    vcf = generate_vcf(list(numbers), name)
    await update.message.reply_document(open(vcf, "rb"))
    os.remove(vcf)

    for f in merge_data[uid]["files"]:
        os.remove(f)

    merge_data.pop(uid)

# ================= MAIN =================
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

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

    print("🚀 BOT + FLASK RUNNING")
    app.run_polling()
