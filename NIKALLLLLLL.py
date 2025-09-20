import os
import re
import pandas as pd
from datetime import datetime
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ========== CONFIGURATION ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 7640327597
ALLOWED_USERS = [7640327597]  # add more IDs

def is_authorized(user_id):
    return user_id in ALLOWED_USERS

BOT_START_TIME = datetime.utcnow()

# ========== DEFAULTS ==========
default_vcf_name = "Contacts"
default_contact_name = "Contact"
default_limit = 100

# ========== USER SETTINGS ==========
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
user_country_codes = {}
user_group_start_numbers = {}
merge_data = {}
conversion_mode = {}

# ========== HELPERS ==========
def generate_vcf(numbers, filename="Contacts", contact_name="Contact", start_index=None, country_code="", group_num=None):
    vcf_data = ""
    for i, num in enumerate(numbers, start=(start_index if start_index else 1)):
        if group_num:
            name = f"{contact_name}{str(i).zfill(3)} (Group {group_num})"
        else:
            name = f"{contact_name}{str(i).zfill(3)}"
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
            tel_lines = [line for line in card.splitlines() if line.startswith('TEL')]
            for line in tel_lines:
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

# ========== INLINE MENUS ==========
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📂 Make VCF", callback_data="makevcf"),
         InlineKeyboardButton("🔀 Merge Files", callback_data="merge")],
        [InlineKeyboardButton("📝 TXT → VCF", callback_data="txt2vcf"),
         InlineKeyboardButton("📤 VCF → TXT", callback_data="vcf2txt")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("❌ Reset", callback_data="reset")],
        [InlineKeyboardButton("📊 My Stats", callback_data="mysettings"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def settings_menu():
    keyboard = [
        [InlineKeyboardButton("📂 Set Filename", callback_data="setfilename")],
        [InlineKeyboardButton("👤 Set Contact Name", callback_data="setcontactname")],
        [InlineKeyboardButton("📊 Set Limit", callback_data="setlimit")],
        [InlineKeyboardButton("🔢 Set Start Index", callback_data="setstart")],
        [InlineKeyboardButton("📄 Set VCF Start", callback_data="setvcfstart")],
        [InlineKeyboardButton("🌍 Set Country Code", callback_data="setcountrycode")],
        [InlineKeyboardButton("📑 Set Group Start", callback_data="setgroup")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== START ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized. Contact the bot owner.")
        return

    uptime_duration = datetime.utcnow() - BOT_START_TIME
    days = uptime_duration.days
    hours, rem = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    text = (
        "☠️ Welcome to the VCF Bot!☠️\n\n"
        f"🤖 Uptime: {days}d {hours}h {minutes}m {seconds}s\n\n"
        "📌 Use the buttons below 👇"
    )
    await update.message.reply_text(text, reply_markup=main_menu())

# ========== CALLBACK HANDLER ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_authorized(user_id):
        await query.edit_message_text("❌ Unauthorized")
        return

    data = query.data

    if data == "makevcf":
        await query.edit_message_text("Use: `/makevcf NAME number1 number2 ...`", parse_mode="Markdown")

    elif data == "merge":
        merge_data[user_id] = []
        await query.edit_message_text("📂 Send me files to merge. When done, use /done")

    elif data == "txt2vcf":
        conversion_mode[user_id] = "txt2vcf"
        await query.edit_message_text("📂 Send me a TXT file, I’ll convert it into VCF.")

    elif data == "vcf2txt":
        conversion_mode[user_id] = "vcf2txt"
        await query.edit_message_text("📂 Send me a VCF file, I’ll extract numbers into TXT.")

    elif data == "settings":
        await query.edit_message_text("⚙️ Settings Menu:", reply_markup=settings_menu())

    elif data == "back_main":
        await query.edit_message_text("⬅️ Back to main menu:", reply_markup=main_menu())

    elif data == "reset":
        reset_user_settings(user_id)
        await query.edit_message_text("✅ All settings reset.", reply_markup=main_menu())

    elif data == "mysettings":
        settings = get_user_settings(user_id)
        await query.edit_message_text(settings, reply_markup=main_menu())

    elif data == "help":
        await query.edit_message_text(
            "ℹ️ *Help*\n\n"
            "/makevcf NAME numbers... → Create VCF\n"
            "/merge + /done → Merge files\n"
            "/txt2vcf → Convert TXT file to VCF\n"
            "/vcf2txt → Convert VCF file to TXT\n"
            "/reset → Reset settings\n"
            "/mysettings → Show settings",
            parse_mode="Markdown", reply_markup=main_menu()
        )

# ========== COMMANDS ==========
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name number1 number2 ...")
        return
    contact_name = context.args[0]
    numbers = context.args[1:]
    file_path = generate_vcf(numbers, contact_name, contact_name)
    await update.message.reply_document(document=open(file_path, "rb"))
    os.remove(file_path)

async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    merge_data[update.effective_user.id] = []
    await update.message.reply_text("📂 Send me files to merge. When done, use /done")

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in merge_data or not merge_data[user_id]:
        await update.message.reply_text("❌ No files queued for merge.")
        return
    all_numbers = set()
    for file_path in merge_data[user_id]:
        if file_path.endswith(".vcf"):
            all_numbers.update(extract_numbers_from_vcf(file_path))
        elif file_path.endswith(".txt"):
            all_numbers.update(extract_numbers_from_txt(file_path))
    vcf_path = generate_vcf(list(all_numbers), "Merged")
    await update.message.reply_document(document=open(vcf_path, "rb"))
    os.remove(vcf_path)
    for file_path in merge_data[user_id]:
        if os.path.exists(file_path): os.remove(file_path)
    merge_data[user_id] = []
    await update.message.reply_text("✅ Merge completed.")

# ========== SETTINGS ==========
def reset_user_settings(user_id):
    user_file_names.pop(user_id, None)
    user_contact_names.pop(user_id, None)
    user_limits.pop(user_id, None)
    user_start_indexes.pop(user_id, None)
    user_vcf_start_numbers.pop(user_id, None)
    user_country_codes.pop(user_id, None)
    user_group_start_numbers.pop(user_id, None)

def get_user_settings(user_id):
    return (
        f"📂 File name: {user_file_names.get(user_id, default_vcf_name)}\n"
        f"👤 Contact name: {user_contact_names.get(user_id, default_contact_name)}\n"
        f"📊 Limit: {user_limits.get(user_id, default_limit)}\n"
        f"🔢 Start index: {user_start_indexes.get(user_id, 'Not set')}\n"
        f"📄 VCF start: {user_vcf_start_numbers.get(user_id, 'Not set')}\n"
        f"🌍 Country code: {user_country_codes.get(user_id, 'None')}\n"
        f"📑 Group start: {user_group_start_numbers.get(user_id, 'Not set')}"
    )

async def reset_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_user_settings(update.effective_user.id)
    await update.message.reply_text("✅ All settings reset.")

async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_user_settings(update.effective_user.id))

# ========== FILE HANDLER ==========
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return

    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)

    if user_id in merge_data:
        merge_data[user_id].append(path)
        await update.message.reply_text(f"📥 File added for merge: {file.file_name}")
        return

    if user_id in conversion_mode:
        mode = conversion_mode.pop(user_id)
        if mode == "txt2vcf" and path.endswith(".txt"):
            numbers = extract_numbers_from_txt(path)
            if numbers:
                vcf_path = generate_vcf(list(numbers), "Converted", "Contact")
                await update.message.reply_document(document=open(vcf_path, "rb"))
                os.remove(vcf_path)
        elif mode == "vcf2txt" and path.endswith(".vcf"):
            numbers = extract_numbers_from_vcf(path)
            if numbers:
                txt_path = "Converted.txt"
                with open(txt_path, "w") as f:
                    f.write("\n".join(numbers))
                await update.message.reply_document(document=open(txt_path, "rb"))
                os.remove(txt_path)
        if os.path.exists(path): os.remove(path)
        return

    if path.endswith(".csv"):
        df = pd.read_csv(path, encoding="utf-8")
    elif path.endswith(".xlsx"):
        df = pd.read_excel(path)
    elif path.endswith(".txt"):
        numbers = extract_numbers_from_txt(path)
        df = pd.DataFrame({"Numbers": list(numbers)})
    elif path.endswith(".vcf"):
        numbers = extract_numbers_from_vcf(path)
        df = pd.DataFrame({"Numbers": list(numbers)})
    else:
        await update.message.reply_text("❌ Unsupported file type.")
        return

    await process_numbers(update, context, df["Numbers"].dropna().astype(str).tolist())
    if os.path.exists(path): os.remove(path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    numbers = re.findall(r"\d{7,}", update.message.text)
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    numbers = list(dict.fromkeys([n.strip() for n in numbers if n.strip().isdigit()]))
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]
    for idx, chunk in enumerate(chunks):
        file_path = generate_vcf(chunk, f"{file_base}_{idx+1}", contact_name)
        await update.message.reply_document(document=open(file_path, "rb"))
        os.remove(file_path)

# ========== MAIN ==========
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("makevcf", make_vcf_command))
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("done", done_merge))
    app.add_handler(CommandHandler("reset", reset_settings))
    app.add_handler(CommandHandler("mysettings", my_settings))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🚀 Bot with inline menu running...")
    app.run_polling()
        
