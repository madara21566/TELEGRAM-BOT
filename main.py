import os
import re
import pandas as pd
import secrets
from datetime import datetime, timedelta, timezone
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
OWNER_ID = 7640327597  # Your Telegram ID

BOT_START_TIME = datetime.now(timezone.utc)

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
conversion_mode = {}  # 🔥 for txt2vcf / vcf2txt

# ✅ KEY MANAGEMENT
valid_keys = {}   # key -> expiry datetime (None = permanent)
user_keys = {}    # user_id -> key mapping

import json

KEYS_FILE = "keys.json"

def save_keys():
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump({
                "valid_keys": {k: (v.isoformat() if v else None) for k, v in valid_keys.items()},
                "user_keys": user_keys
            }, f)
    except Exception as e:
        print("Error saving keys:", e)

def load_keys():
    global valid_keys, user_keys
    try:
        with open(KEYS_FILE, "r") as f:
            data = json.load(f)
            valid_keys = {k: (datetime.fromisoformat(v) if v else None) for k, v in data.get("valid_keys", {}).items()}
            user_keys = data.get("user_keys", {})
    except FileNotFoundError:
        valid_keys = {}
        user_keys = {}
    except Exception as e:
        print("Error loading keys:", e)
        valid_keys = {}
        user_keys = {}


def generate_random_key(length=16):
    return secrets.token_hex(length // 2)  # e.g. 16-char hex

async def check_key(update: Update):
    user_id = update.effective_user.id
    key = user_keys.get(user_id)
    if not key or key not in valid_keys:
        msg = (
            "📂💾 VCF Bot Access\n\n"
            "Just DM me anytime — I’ll reply to you fast!\n\n"
            "📩 Direct Message here: @MADARAXHEREE\n\n"
            "/usekey ** [ Only the owner will give the key.]\n\n"
            "⚡ Convert TXT ⇄ VCF instantly | 🪄 Easy & Quick | 🔒 Trusted"
        )
        await update.message.reply_text(msg)
        return False

    expiry = valid_keys.get(key)
    if expiry and datetime.now(timezone.utc) > expiry:
        # expired - remove
        valid_keys.pop(key, None)
        user_keys.pop(user_id, None)
        await update.message.reply_text("❌ Your key expired. Contact @MADARAXHEREE")
        return False

    return True

# ✅ USER COMMANDS

async def use_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /usekey YOUR_KEY")
        return
    key = context.args[0]
    if key in valid_keys:
        user_keys[update.effective_user.id] = key
        await update.message.reply_text("✅ Key activated! All features unlocked.")
        save_keys()
    else:
        await update.message.reply_text("❌ Invalid key. Contact @MADARAXHEREE")


async def my_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    key = user_keys.get(user_id)
    if not key:
        await update.message.reply_text("❌ You have not activated any key yet.")
        return
    expiry = valid_keys.get(key)
    exp_text = "♾ Permanent" if expiry is None else expiry.strftime("%Y-%m-%d %H:%M:%S UTC")
    await update.message.reply_text(f"🔑 Your active key: {key}\n⏳ Expires: {exp_text}")

# ✅ OWNER COMMANDS

async def gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /genkey [1d/7d/1m/12h/permanent]")
        return

    duration = context.args[0].lower()
    now = datetime.now(timezone.utc)
    expiry = None

    try:
        if duration.endswith("d"):
            days = int(duration[:-1])
            expiry = now + timedelta(days=days)
        elif duration.endswith("h"):
            hours = int(duration[:-1])
            expiry = now + timedelta(hours=hours)
        elif duration.endswith("m"):
            months = int(duration[:-1])
            expiry = now + timedelta(days=30*months)
        elif duration == "permanent":
            expiry = None
        else:
            await update.message.reply_text("❌ Invalid format. Use 1d, 7d, 12h, 1m, permanent")
            return
    except Exception:
        await update.message.reply_text("❌ Invalid number in duration.")
        return

    key = generate_random_key(16)
    valid_keys[key] = expiry
    exp_text = "♾ Permanent" if expiry is None else expiry.strftime("%Y-%m-%d %H:%M:%S UTC")
    await update.message.reply_text(f"✅ New key generated:\n\n🔑 `{key}`\n⏳ Expires: {exp_text}", parse_mode="Markdown")
    save_keys()


async def add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /addkey NEW_KEY")
        return
    new_key = context.args[0]
    valid_keys[new_key] = None
    await update.message.reply_text(f"✅ Key added: {new_key}")
    save_keys()


async def remove_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /removekey KEY")
        return
    key = context.args[0]
    if key in valid_keys:
        valid_keys.pop(key, None)
        await update.message.reply_text(f"✅ Key removed: {key}")
        save_keys()
    else:
        await update.message.reply_text("❌ Key not found.")

async def list_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not valid_keys:
        await update.message.reply_text("⚠️ No keys available.")
        return
    lines = []
    for k, exp in valid_keys.items():
        exp_text = "♾ Permanent" if exp is None else exp.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"{k} → {exp_text}")
    await update.message.reply_text("🔑 Active Keys:\n" + "\n".join(lines))

# ✅ ERROR HANDLER
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.now(timezone.utc)} - {error_text}\n\n")
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# ✅ HELPERS
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

# ✅ TXT2VCF & VCF2TXT (with custom name support)
async def txt2vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    conversion_mode[update.effective_user.id] = "txt2vcf"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a TXT file, I’ll convert it into VCF.")

async def vcf2txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    conversion_mode[update.effective_user.id] = "vcf2txt"
    if context.args:
        conversion_mode[f"{update.effective_user.id}_name"] = "_".join(context.args)
    await update.message.reply_text("📂 Send me a VCF file, I’ll extract numbers into TXT.")

# ✅ START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime_duration = datetime.now(timezone.utc) - BOT_START_TIME
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
        "/txt2vcf → [ Convert TXT file to VCF ]\n"
        "/vcf2txt → [ Convert VCF file to TXT ]\n\n"
        "🧹 Reset & Settings:\n"
        "/reset → sab settings default par le aao\n"
        "/mysettings → apne current settings dekho\n\n"
        "/admin [ OWNER ONLY]\n"
        "📤 Send TXT, CSV, XLSX, or VCF files or numbers."
    )

    keyboard = [
        [InlineKeyboardButton("Help 📖", url="https://t.me/GODMADARAVCFMAKER")],
        [InlineKeyboardButton("Bot status 👁️‍🗨️", url="https://telegram-bot-ddhv.onrender.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup)

# ✅ FILE HANDLER
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    file = update.message.document
    path = f"{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(path)
    user_id = update.effective_user.id

    # ✅ Merge mode
    if user_id in merge_data:
        merge_data[user_id]["files"].append(path)
        await update.message.reply_text(f"📥 File added for merge: {file.file_name}")
        return

    # ✅ Conversion modes
    if user_id in conversion_mode:
        mode = conversion_mode[user_id]

        if mode == "txt2vcf" and path.endswith(".txt"):
            numbers = extract_numbers_from_txt(path)
            if numbers:
                filename = conversion_mode.get(f"{user_id}_name", "Converted")
                vcf_path = generate_vcf(list(numbers), filename, "Contact")
                await update.message.reply_document(document=open(vcf_path, "rb"))
                os.remove(vcf_path)
            else:
                await update.message.reply_text("❌ No numbers found in TXT file.")

        elif mode == "vcf2txt" and path.endswith(".vcf"):
            numbers = extract_numbers_from_vcf(path)
            if numbers:
                filename = conversion_mode.get(f"{user_id}_name", "Converted")
                txt_path = f"{filename}.txt"
                with open(txt_path, "w") as f:
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

    # ✅ fallback: normal handling
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8')
        elif path.endswith('.xlsx'):
            df = pd.read_excel(path)
        elif path.endswith('.txt'):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            numbers = [''.join(filter(str.isdigit, w)) for w in content.split() if len(w) >= 7]
            df = pd.DataFrame({'Numbers': numbers})
        elif path.endswith('.vcf'):
            numbers = extract_numbers_from_vcf(path)
            df = pd.DataFrame({'Numbers': list(numbers)})
        else:
            await update.message.reply_text("Unsupported file type.")
            return
        await process_numbers(update, context, df['Numbers'].dropna().astype(str).tolist())
    except Exception as e:
        await update.message.reply_text(f"Error processing file: {str(e)}")
    finally:
        if os.path.exists(path):
            os.remove(path)

# ✅ HANDLE TEXT
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    numbers = [''.join(filter(str.isdigit, w)) for w in update.message.text.split() if len(w) >=7]
    if numbers:
        await process_numbers(update, context, numbers)
    else:
        await update.message.reply_text("No valid numbers found.")

# ✅ PROCESS NUMBERS
async def process_numbers(update, context, numbers):
    user_id = update.effective_user.id
    contact_name = user_contact_names.get(user_id, default_contact_name)
    file_base = user_file_names.get(user_id, default_vcf_name)
    limit = user_limits.get(user_id, default_limit)
    start_index = user_start_indexes.get(user_id, None)
    vcf_num = user_vcf_start_numbers.get(user_id, None)
    country_code = user_country_codes.get(user_id, "")
    custom_group_start = user_group_start_numbers.get(user_id, None)

    numbers = list(dict.fromkeys([n.strip() for n in numbers if n.strip().isdigit()]))
    chunks = [numbers[i:i+limit] for i in range(0, len(numbers), limit)]

    for idx, chunk in enumerate(chunks):
        group_num = (custom_group_start + idx) if custom_group_start else None
        file_suffix = f"{vcf_num+idx}" if vcf_num else f"{idx+1}"
        file_path = generate_vcf(
            chunk,
            f"{file_base}_{file_suffix}",
            contact_name,
            (start_index + idx*limit) if start_index else None,
            country_code,
            group_num
        )
        await update.message.reply_document(document=open(file_path, "rb"))
        os.remove(file_path)

# ✅ SETTINGS COMMANDS
async def set_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    if context.args:
        user_file_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"✅ File name set to: {' '.join(context.args)}")

async def set_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    if context.args:
        user_contact_names[update.effective_user.id] = ' '.join(context.args)
        await update.message.reply_text(f"✅ Contact name set to: {' '.join(context.args)}")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    if context.args and context.args[0].isdigit():
        user_limits[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Limit set to: {context.args[0]}")

async def set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    if context.args and context.args[0].isdigit():
        user_start_indexes[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Contact numbering will start from: {context.args[0]}")

async def set_vcf_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    if context.args and context.args[0].isdigit():
        user_vcf_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ VCF numbering will start from: {context.args[0]}")

async def set_country_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    if context.args:
        user_country_codes[update.effective_user.id] = context.args[0]
        await update.message.reply_text(f"✅ Country code set to: {context.args[0]}")

async def set_group_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    if context.args and context.args[0].isdigit():
        user_group_start_numbers[update.effective_user.id] = int(context.args[0])
        await update.message.reply_text(f"✅ Group numbering will start from: {context.args[0]}")

async def reset_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
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
    if not await check_key(update): return
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

# ✅ MAKEVCF
async def make_vcf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /makevcf Name number1 number2 ...")
        return

    contact_name = context.args[0]
    numbers = context.args[1:]

    file_path = generate_vcf(numbers, contact_name, contact_name)
    await update.message.reply_document(document=open(file_path, "rb"))
    os.remove(file_path)

# ✅ MERGE
async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    user_id = update.effective_user.id
    merge_data[user_id] = {"files": [], "filename": "Merged"}  # default
    if context.args:
        merge_data[user_id]["filename"] = "_".join(context.args)
    await update.message.reply_text(
        f"📂 Send me files to merge. Final file will be: {merge_data[user_id]['filename']}.vcf\n"
        "👉 When done, use /done."
    )

async def done_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_key(update): return
    user_id = update.effective_user.id
    if user_id not in merge_data or not merge_data[user_id]["files"]:
        await update.message.reply_text("❌ No files queued for merge.")
        return

    all_numbers = set()
    for file_path in merge_data[user_id]["files"]:
        if file_path.endswith(".vcf"):
            all_numbers.update(extract_numbers_from_vcf(file_path))
        elif file_path.endswith(".txt"):
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


# ✅ ADMIN PANEL
from telegram.ext import CallbackQueryHandler

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    keyboard = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="genkey_help")],
        [InlineKeyboardButton("➕ Add Key", callback_data="addkey_help")],
        [InlineKeyboardButton("❌ Remove Key", callback_data="removekey_help")],
        [InlineKeyboardButton("📋 List Keys", callback_data="listkeys")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ Admin Panel", reply_markup=reply_markup)

async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("❌ Unauthorized")
        return

    if query.data == "genkey_help":
        await query.edit_message_text("Use command: /genkey [1d/7d/1m/12h/permanent]")
    elif query.data == "addkey_help":
        await query.edit_message_text("Use command: /addkey NEW_KEY")
    elif query.data == "removekey_help":
        await query.edit_message_text("Use command: /removekey KEY")
    elif query.data == "listkeys":
        if not valid_keys:
            await query.edit_message_text("⚠️ No keys available.")
            return
        lines = []
        for k, exp in valid_keys.items():
            exp_text = "♾ Permanent" if exp is None else exp.strftime("%Y-%m-%d %H:%M:%S UTC")
            lines.append(f"{k} → {exp_text}")
        await query.edit_message_text("🔑 Active Keys:\n" + "\n".join(lines))

# ✅ MAIN
if __name__ == "__main__":
    load_keys()
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

    # Admin Panel
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_button_handler))

    # Key commands
    app.add_handler(CommandHandler("usekey", use_key))
    app.add_handler(CommandHandler("mykey", my_key))
    app.add_handler(CommandHandler("genkey", gen_key))
    app.add_handler(CommandHandler("addkey", add_key))
    app.add_handler(CommandHandler("removekey", remove_key))
    app.add_handler(CommandHandler("listkeys", list_keys))

    # Handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("🚀 Bot is running...")
    app.run_polling()
