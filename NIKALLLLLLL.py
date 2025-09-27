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
OWNER_ID = 7640327597
ALLOWED_USERS = [7856502907,7770325695,5564571047,7950732287,8128934569,5849097477,7640327597,7669357884,5989680310,7118726445,7043391463,8047407478]

def is_authorized(user_id):
    return user_id in ALLOWED_USERS

BOT_START_TIME = datetime.utcnow()

# ✅ DEFAULTS
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# ✅ USER DATA
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
merge_filename = {}
conversion_mode = {}  # { user_id: {"mode": "txt2vcf", "filename": "NAME"} }

# ✅ ERROR HANDLER
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# ✅ ACCESS TEXT
def get_access_text():
    return (
        "📂💾 *VCF Bot Access*\n"
        "Want my *VCF Converter Bot*?\n"
        "Just DM me anytime — I’ll reply fast!\n\n"
        "📩 @MADARAXHEREE\n\n"
        "⚡ TXT ⇄ VCF | 🪄 Easy | 🔒 Trusted"
    )

# ✅ HELPERS
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index if start_index else 1)):
        name = f"{contact_name}{str(i).zfill(3)}" + (f" (Group {group_num})" if group_num else "")
        formatted_num = f"{country_code}{num}" if country_code else num
        vcf_data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{formatted_num}\nEND:VCARD\n"
    with open(f"{filename}.vcf", "w") as f:
        f.write(vcf_data)
    return f"{filename}.vcf"

def extract_numbers_from_vcf(file_path):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for card in content.split('END:VCARD'):
        if 'TEL' in card:
            for line in card.splitlines():
                if line.startswith('TEL'):
                    number = re.sub(r'[^0-9]', '', line.split(':')[-1].strip())
                    if number:
                        numbers.add(number)
    return numbers

def extract_numbers_from_txt(file_path):
    numbers = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            nums = re.findall(r'\d{7,}', line)
            numbers.update(nums)
    return numbers

# ✅ START COMMAND (with GOD MADARA Banner)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
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

# ✅ TXT2VCF
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filename = context.args[0] if context.args else "Converted"
    conversion_mode[update.effective_user.id] = {"mode": "txt2vcf", "filename": filename}
    await update.message.reply_text(f"📂 Send me a TXT file to convert into *{filename}.vcf*")

# ✅ VCF2TXT
async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filename = context.args[0] if context.args else "Converted"
    conversion_mode[update.effective_user.id] = {"mode": "vcf2txt", "filename": filename}
    await update.message.reply_text(f"📂 Send me a VCF file to extract numbers into *{filename}.txt*")

# ✅ DOCUMENT HANDLER
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(get_access_text(), parse_mode="Markdown")
        return

    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)

    # MERGE MODE
    if user_id in merge_data:
        merge_data[user_id].append(path)
        await update.message.reply_text(f"📥 Added for merge: {file.file_name}")
        return

    # CONVERSION MODES
    if user_id in conversion_mode:
        mode_info = conversion_mode[user_id]
        mode, filename = mode_info["mode"], mode_info["filename"]

        if mode == "txt2vcf" and path.endswith(".txt"):
            nums = extract_numbers_from_txt(path)
            if nums:
                out = generate_vcf(list(nums), filename, "Contact")
                await update.message.reply_document(document=open(out, "rb"))
                os.remove(out)
        elif mode == "vcf2txt" and path.endswith(".vcf"):
            nums = extract_numbers_from_vcf(path)
            if nums:
                txt = f"{filename}.txt"
                with open(txt, "w") as f:
                    f.write("\n".join(nums))
                await update.message.reply_document(document=open(txt, "rb"))
                os.remove(txt)
        else:
            await update.message.reply_text("❌ Wrong file type.")
        conversion_mode.pop(user_id, None)
        os.remove(path)
        return

    # NORMAL FILE
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path)
        elif path.endswith('.xlsx'):
            df = pd.read_excel(path)
        elif path.endswith('.txt'):
            with open(path, 'r', encoding='utf-8') as f:
                nums = [''.join(filter(str.isdigit, w)) for w in f.read().split() if len(w) >= 7]
            df = pd.DataFrame({'Numbers': nums})
        elif path.endswith('.vcf'):
            nums = extract_numbers_from_vcf(path)
            df = pd.DataFrame({'Numbers': list(nums)})
        else:
            await update.message.reply_text("Unsupported file type.")
            return
        await process_numbers(update, context, df['Numbers'].dropna().astype(str).tolist())
    finally:
        if os.path.exists(path): os.remove(path)

# ✅ TEXT HANDLER
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nums = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(w) >=7]
    if nums:
        await process_numbers(update, context, nums)
    else:
        await update.message.reply_text("No valid numbers found.")

# ✅ PROCESS NUMBERS
async def process_numbers(update, context, numbers):
    uid = update.effective_user.id
    cname = user_contact_names.get(uid, default_contact_name)
    fname = user_file_names.get(uid, default_vcf_name)
    limit = user_limits.get(uid, default_limit)
    start = user_start_indexes.get(uid)
    vcfnum = user_vcf_start_numbers.get(uid)
    code = user_country_codes.get(uid, "")
    gstart = user_group_start_numbers.get(uid)

    numbers = list(dict.fromkeys([n.strip() for n in numbers if n.strip().isdigit()]))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for idx, chunk in enumerate(chunks):
        group = (gstart + idx) if gstart else None
        suffix = f"{vcfnum+idx}" if vcfnum else f"{idx+1}"
        path = generate_vcf(chunk, f"{fname}_{suffix}", cname, (start + idx*limit) if start else None, code, group)
        await update.message.reply_document(document=open(path, "rb"))
        os.remove(path)

# ✅ MERGE
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filename = context.args[0] if context.args else "Merged"
    merge_filename[update.effective_user.id] = filename
    merge_data[update.effective_user.id] = []
    await update.message.reply_text(f"📂 Send files to merge. Final name: *{filename}.vcf*\nThen use /done", parse_mode="Markdown")

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in merge_data or not merge_data[uid]:
        await update.message.reply_text("❌ No files queued for merge.")
        return
    all_nums = set()
    for fpath in merge_data[uid]:
        if fpath.endswith(".vcf"):
            all_nums.update(extract_numbers_from_vcf(fpath))
        elif fpath.endswith(".txt"):
            all_nums.update(extract_numbers_from_txt(fpath))
    fname = merge_filename.get(uid, "Merged")
    vcf = generate_vcf(list(all_nums), fname)
    await update.message.reply_document(document=open(vcf, "rb"))
    os.remove(vcf)
    for fpath in merge_data[uid]:
        if os.path.exists(fpath): os.remove(fpath)
    merge_data.pop(uid, None)
    merge_filename.pop(uid, None)
    await update.message.reply_text(f"✅ Merge completed. File: *{fname}.vcf*", parse_mode="Markdown")

# ✅ MAKEVCF
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name number1 number2 ...")
        return
    cname = context.args[0]
    nums = context.args[1:]
    path = generate_vcf(nums, cname, cname)
    await update.message.reply_document(document=open(path, "rb"))
    os.remove(path)

   # ✅ MAIN
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('setfilename', set_filename))
    app.add_handler(CommandHandler('setcontactname', set_contact_name))
    app.add_handler(CommandHandler('setlimit', set_limit))
    app.add_handler(CommandHandler('setstart', set_start))
    app.add_handler(CommandHandler('setvcfstart', set_vcf_start))
    app.add_handler(CommandHandler('setcountrycode', set_country_code))
    app.add_handler(CommandHandler('setgroup', set_group_number))
    app.add_handler(CommandHandler('reset', reset_settings))
    app.add_handler(CommandHandler('mysettings', my_settings))
    app.add_handler(CommandHandler('makevcf', make_vcf_command))
    app.add_handler(CommandHandler('merge', merge_command))
    app.add_handler(CommandHandler('done', done_merge))

    # File and text handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Error handler
    app.add_error_handler(error_handler)

    print("🚀 Bot is running...")
    app.run_polling()
                                                      
