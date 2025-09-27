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

# ===================== CONFIG =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # set this on Render / VPS
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
OWNER_ID = 7640327597  # change if needed

# Allowed users (keep as you had)
ALLOWED_USERS = [
    7856502907, 7770325695, 5564571047, 7950732287, 8128934569, 5849097477,
    7640327597, 7669357884, 5989680310, 7118726445, 7043391463, 8047407478
]

def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

BOT_START_TIME = datetime.utcnow()

# ===================== DEFAULTS & STORAGE =====================
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# Per-user settings / mode storages
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}

# Merge / conversion modes
merge_data = {}         # { user_id: [file_paths...] }
merge_filename = {}     # { user_id: "Name" }
conversion_mode = {}    # { user_id: {"mode": "txt2vcf"/"vcf2txt", "filename": "Name"} }

# ===================== ERROR HANDLER =====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    except Exception:
        error_text = "Error formatting exception."
    with open("bot_errors.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        # send to owner (truncate)
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# ===================== HELP / ACCESS =====================
def get_access_text() -> str:
    return (
        "📂💾 *VCF Bot Access*\n"
        "Want my *VCF Converter Bot*?\n"
        "Just DM me anytime — I’ll reply fast!\n\n"
        "📩 @MADARAXHEREE\n\n"
        "⚡ TXT ⇄ VCF | 🪄 Easy | 🔒 Trusted"
    )

# ===================== HELPERS =====================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    """
    Create a .vcf file named {filename}.vcf containing numbers list.
    numbers: iterable of digit strings
    """
    vcf_data = ""
    # start index default 1 if None
    start = start_index if (start_index is not None) else 1
    for i, num in enumerate(numbers, start=start):
        # contact name with zero-padded index
        name = f"{contact_name}{str(i).zfill(3)}"
        if group_num is not None:
            name += f" (Group {group_num})"
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
    out_path = f"{filename}.vcf"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(vcf_data)
    return out_path

def extract_numbers_from_vcf(file_path):
    """
    Read a .vcf file and extract phone numbers (digits only).
    Returns a set of numbers.
    """
    numbers = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        # split by card and search TEL lines
        for card in content.split('END:VCARD'):
            if 'TEL' in card:
                for line in card.splitlines():
                    # detect TEL lines robustly (case-insensitive)
                    if line.strip().upper().startswith('TEL'):
                        val = line.split(':')[-1].strip()
                        number = re.sub(r'[^0-9]', '', val)
                        if number:
                            numbers.add(number)
    except Exception:
        pass
    return numbers

def extract_numbers_from_txt(file_path):
    """
    Read a text file and extract numbers (7+ digits).
    Returns a set of numbers.
    """
    numbers = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                found = re.findall(r'\d{7,}', line)
                for n in found:
                    numbers.add(n)
    except Exception:
        pass
    return numbers

# ===================== START (with GOD MADARA banner) =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(get_access_text(), parse_mode="Markdown")
        return

    uptime_duration = datetime.utcnow() - BOT_START_TIME
    days = uptime_duration.days
    hours, rem = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    banner = (
        "```\n"
        "╔═╗╔═╗╔╦╗    ╔╦╗╔═╗╔╦╗╔═╗╔╗╔╔═╗╔═╗\n"
        "║ ╦║╣  ║      ║ ║ ║║║║║╣ ║║║╚═╗║╣ \n"
        "╚═╝╚═╝ ╩      ╩ ╚═╝╩ ╩╚═╝╝╚╝╚═╝╚═╝\n"
        "```"
    )

    help_text = (
        f"{banner}\n"
        "☠️ *Welcome to the VCF Bot!* ☠️\n\n"
        f"🤖 *Uptime:* {days}d {hours}h {minutes}m {seconds}s\n\n"
        "📌 *Available Commands:*\n"
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
        "/txt2vcf → [ Convert TXT file to VCF ]\n"
        "/vcf2txt → [ Convert VCF file to TXT ]\n\n"
        "🧹 *Reset & Settings:*\n"
        "/reset → sab settings default par le aao\n"
        "/mysettings → apne current settings dekho\n\n"
        "📤 *Send TXT, CSV, XLSX, or VCF files or numbers.*"
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-ddhv.onrender.com")]
    ]
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ===================== CONVERSION COMMANDS =====================
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(get_access_text(), parse_mode="Markdown")
        return
    filename = context.args[0] if context.args else "Converted"
    conversion_mode[user_id] = {"mode": "txt2vcf", "filename": filename}
    await update.message.reply_text(f"📂 Send me a TXT file to convert into *{filename}.vcf*", parse_mode="Markdown")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(get_access_text(), parse_mode="Markdown")
        return
    filename = context.args[0] if context.args else "Converted"
    conversion_mode[user_id] = {"mode": "vcf2txt", "filename": filename}
    await update.message.reply_text(f"📂 Send me a VCF file to extract numbers into *{filename}.txt*", parse_mode="Markdown")

# ===================== FILE HANDLER =====================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(get_access_text(), parse_mode="Markdown")
        return

    doc = update.message.document
    file_name = doc.file_name
    # local unique path
    path = f"{doc.file_unique_id}_{file_name}"
    # download
    await (await context.bot.get_file(doc.file_id)).download_to_drive(path)

    # If user is currently adding files for merge
    if user_id in merge_data:
        merge_data[user_id].append(path)
        await update.message.reply_text(f"📥 Added for merge: {file_name}")
        return

    # If user in conversion mode (txt2vcf / vcf2txt)
    if user_id in conversion_mode:
        info = conversion_mode[user_id]
        mode = info.get("mode")
        filename = info.get("filename", "Converted")

        try:
            if mode == "txt2vcf":
                if not path.lower().endswith(".txt"):
                    await update.message.reply_text("❌ Please send a .txt file for this command.")
                else:
                    nums = extract_numbers_from_txt(path)
                    if not nums:
                        await update.message.reply_text("❌ No numbers found in the TXT file.")
                    else:
                        out = generate_vcf(list(nums), filename, "Contact")
                        await update.message.reply_document(document=open(out, "rb"))
                        os.remove(out)
            elif mode == "vcf2txt":
                if not path.lower().endswith(".vcf"):
                    await update.message.reply_text("❌ Please send a .vcf file for this command.")
                else:
                    nums = extract_numbers_from_vcf(path)
                    if not nums:
                        await update.message.reply_text("❌ No numbers found in the VCF file.")
                    else:
                        out_txt = f"{filename}.txt"
                        with open(out_txt, "w", encoding="utf-8") as f:
                            f.write("\n".join(sorted(nums)))
                        await update.message.reply_document(document=open(out_txt, "rb"))
                        os.remove(out_txt)
            else:
                await update.message.reply_text("❌ Unknown conversion mode.")
        finally:
            # clear conversion mode and remove uploaded file
            conversion_mode.pop(user_id, None)
            if os.path.exists(path):
                os.remove(path)
        return

    # Fallback: normal file processing (csv, xlsx, txt, vcf)
    try:
        ext = file_name.lower()
        if ext.endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8', dtype=str, keep_default_na=False)
            numbers = []
            for col in df.columns:
                # try to collect numeric-looking values
                numbers += [re.sub(r'[^0-9]', '', str(v)) for v in df[col].dropna().astype(str).tolist()]
        elif ext.endswith('.xlsx') or ext.endswith('.xls'):
            df = pd.read_excel(path, dtype=str)
            numbers = []
            for col in df.columns:
                numbers += [re.sub(r'[^0-9]', '', str(v)) for v in df[col].dropna().astype(str).tolist()]
        elif ext.endswith('.txt'):
            numbers = []
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # split by whitespace and extract digit sequences of length >=7
            for token in re.findall(r'\d{7,}', content):
                numbers.append(token)
        elif ext.endswith('.vcf'):
            numbers = list(extract_numbers_from_vcf(path))
        else:
            await update.message.reply_text("Unsupported file type.")
            return

        # clean & unique
        numbers = list(dict.fromkeys([n.strip() for n in numbers if n and n.strip().isdigit()]))
        if not numbers:
            await update.message.reply_text("❌ No valid numbers found in the file.")
            return
        await process_numbers(update, context, numbers)
    except Exception as e:
        await update.message.reply_text(f"Error processing file: {str(e)}")
    finally:
        if os.path.exists(path):
            os.remove(path)

# ===================== TEXT HANDLER =====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(get_access_text(), parse_mode="Markdown")
        return
    text = update.message.text
    # extract 7+ digit tokens
    numbers = re.findall(r'\d{7,}', text)
    numbers = list(dict.fromkeys(numbers))
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

# ===================== PROCESS NUMBERS (creates VCFs splitting by limit) =====================
async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    base_name = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, None)
    vcf_start = user_vcf_start_numbers.get(user_id, None)
    country_code = user_country_codes.get(user_id, "")
    group_start = user_group_start_numbers.get(user_id, None)

    # sanitize numbers list
    numbers = [n for n in numbers if isinstance(n, str) and n.strip().isdigit()]
    numbers = list(dict.fromkeys([n.strip() for n in numbers]))

    # split into chunks of size limit
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]
    for idx, chunk in enumerate(chunks):
        group_num = (group_start + idx) if group_start is not None else None
        file_suffix = f"{(vcf_start + idx)}" if vcf_start is not None else f"{idx+1}"
        target_name = f"{base_name}_{file_suffix}"
        start_for_chunk = (start_index + idx*limit) if start_index is not None else None
        out_path = generate_vcf(chunk, target_name, contact_name, start_for_chunk, country_code, group_num)
        try:
            await update.message.reply_document(document=open(out_path, "rb"))
        except Exception:
            await update.message.reply_text(f"Error sending file {out_path}")
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)

# ===================== SETTINGS COMMANDS =====================
async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /setfilename [ FILE NAME ]")
        return
    user_file_names[user_id] = ' '.join(context.args)
    await update.message.reply_text(f"✅ File name set to: {user_file_names[user_id]}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /setcontactname [ CONTACT NAME ]")
        return
    user_contact_names[user_id] = ' '.join(context.args)
    await update.message.reply_text(f"✅ Contact name set to: {user_contact_names[user_id]}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setlimit [ number ]")
        return
    user_limits[user_id] = int(context.args[0])
    await update.message.reply_text(f"✅ Limit set to: {user_limits[user_id]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setstart [ number ]")
        return
    user_start_indexes[user_id] = int(context.args[0])
    await update.message.reply_text(f"✅ Contact numbering will start from: {user_start_indexes[user_id]}")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setvcfstart [ number ]")
        return
    user_vcf_start_numbers[user_id] = int(context.args[0])
    await update.message.reply_text(f"✅ VCF numbering will start from: {user_vcf_start_numbers[user_id]}")

async def set_country_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /setcountrycode [ +91 ]")
        return
    user_country_codes[user_id] = context.args[0]
    await update.message.reply_text(f"✅ Country code set to: {user_country_codes[user_id]}")

async def set_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setgroup [ number ]")
        return
    user_group_start_numbers[user_id] = int(context.args[0])
    await update.message.reply_text(f"✅ Group numbering will start from: {user_group_start_numbers[user_id]}")

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
    txt = (
        f"📂 File name: {user_file_names.get(user_id, default_vcf_name)}\n"
        f"👤 Contact name: {user_contact_names.get(user_id, default_contact_name)}\n"
        f"📊 Limit: {user_limits.get(user_id, default_limit)}\n"
        f"🔢 Start index: {user_start_indexes.get(user_id, 'Not set')}\n"
        f"📄 VCF start: {user_vcf_start_numbers.get(user_id, 'Not set')}\n"
        f"🌍 Country code: {user_country_codes.get(user_id, 'None')}\n"
        f"📑 Group start: {user_group_start_numbers.get(user_id, 'Not set')}"
    )
    await update.message.reply_text(txt)

# ===================== MAKEVCF (command) =====================
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name number1 number2 ...")
        return
    contact_name = context.args[0]
    numbers = [n for n in context.args[1:] if re.match(r'^\d+$', n)]
    if not numbers:
        await update.message.reply_text("No valid numbers provided.")
        return
    out = generate_vcf(numbers, contact_name, contact_name)
    try:
        await update.message.reply_document(document=open(out, "rb"))
    finally:
        if os.path.exists(out):
            os.remove(out)

# ===================== MERGE COMMANDS =====================
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    filename = context.args[0] if context.args else "Merged"
    merge_filename[user_id] = filename
    merge_data[user_id] = []
    await update.message.reply_text(f"📂 Send files to merge. Final name: *{filename}.vcf*\nThen use /done", parse_mode="Markdown")

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in merge_data or not merge_data[user_id]:
        await update.message.reply_text("❌ No files queued for merge.")
        return
    all_numbers = set()
    for fpath in merge_data[user_id]:
        if fpath.lower().endswith(".vcf"):
            all_numbers.update(extract_numbers_from_vcf(fpath))
        elif fpath.lower().endswith(".txt"):
            all_numbers.update(extract_numbers_from_txt(fpath))
        else:
            # ignore unknown file types
            continue
    filename = merge_filename.get(user_id, "Merged")
    if not all_numbers:
        await update.message.reply_text("❌ No numbers found in queued files.")
    else:
        vcf_path = generate_vcf(list(all_numbers), filename)
        try:
            await update.message.reply_document(document=open(vcf_path, "rb"))
        finally:
            if os.path.exists(vcf_path):
                os.remove(vcf_path)
for fpath in merge_data[user_id]:
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    merge_data.pop(user_id, None)
    merge_filename.pop(user_id, None)
    await update.message.reply_text(f"✅ Merge completed. File: *{filename}.vcf*", parse_mode="Markdown")

# ===================== MAIN =====================
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
        exit(1)
app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Core commands
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

    # Merge & conversion
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("done", done_merge))
    app.add_handler(CommandHandler("txt2vcf", txt2vcf))
    app.add_handler(CommandHandler("vcf2txt", vcf2txt))

    # Handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🚀 GOD MADARA VCF Bot is running...")
    app.run_polling()
