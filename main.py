import os
import re
import threading
import traceback
from datetime import datetime

import pandas as pd
from flask import Flask
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ================= IMPORT CORE =================
from database_and_access import (
    init_db,
    ensure_user,
    has_access,
    show_access_denied,
    redeem_key_for_user
)

from admin_panel import (
    show_admin_panel,
    admin_genkey_btn,
    admin_genkey_text,
    admin_key_list,
    admin_expired_keys,
    admin_users_list,
    admin_block_prompt,
    admin_unblock_prompt,
    admin_block_text,
    admin_remove_prompt,
    admin_remove_text,
    admin_broadcast_prompt,
    admin_broadcast_send
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 7640327597

# ================= FLASK (RENDER SAFE) =================
PORT = int(os.environ.get("PORT", 10000))
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "VCF Bot Running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# ================= BOT START TIME =================
BOT_START_TIME = datetime.utcnow()

# ================= VCF HELPERS =================
def generate_vcf(numbers, filename="Contacts", contact_name="Contact"):
    out = ""
    for i, n in enumerate(numbers, start=1):
        out += (
            "BEGIN:VCARD\n"
            "VERSION:3.0\n"
            f"FN:{contact_name}{str(i).zfill(3)}\n"
            f"TEL;TYPE=CELL:{n}\n"
            "END:VCARD\n"
        )
    with open(f"{filename}.vcf", "w") as f:
        f.write(out)
    return f"{filename}.vcf"

def extract_numbers_from_vcf(path):
    nums = set()
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("TEL"):
                nums.add(re.sub(r"\D", "", line))
    return list(nums)

# ================= ERROR HANDLER =================
async def error_handler(update, context):
    err = "".join(traceback.format_exception(
        None, context.error, context.error.__traceback__
    ))
    print(err)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    ensure_user(user.id, user.username)

    if not has_access(user.id):
        await show_access_denied(update)
        return

    uptime = datetime.utcnow() - BOT_START_TIME
    text = (
        "☠️ Welcome to VCF Bot ☠️\n\n"
        f"⏱ Uptime: {uptime}\n\n"
        "📂 Send TXT / CSV / XLSX / VCF or numbers"
    )

    buttons = []
    if user.id == OWNER_ID:
        buttons.append(
            [InlineKeyboardButton("👑 Admin Panel", callback_data="admin")]
        )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
    )

# ================= REDEEM =================
async def redeem_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["redeem"] = True
    await update.callback_query.message.reply_text("🔑 Send your premium key")

async def redeem_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("redeem"):
        return

    ok, msg = redeem_key_for_user(
        update.effective_user.id,
        update.message.text.strip()
    )
    context.user_data["redeem"] = False
    await update.message.reply_text(msg)

# ================= FILE HANDLER =================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access(update.effective_user.id):
        await show_access_denied(update)
        return

    doc = update.message.document
    path = doc.file_name
    await (await context.bot.get_file(doc.file_id)).download_to_drive(path)

    nums = []
    if path.endswith(".txt"):
        nums = re.findall(r"\d{7,}", open(path).read())
    elif path.endswith(".vcf"):
        nums = extract_numbers_from_vcf(path)
    elif path.endswith(".csv"):
        nums = pd.read_csv(path).iloc[:, 0].astype(str).tolist()
    elif path.endswith(".xlsx"):
        nums = pd.read_excel(path).iloc[:, 0].astype(str).tolist()

    nums = list(dict.fromkeys(nums))
    vcf = generate_vcf(nums)

    await update.message.reply_document(open(vcf, "rb"))
    os.remove(path)
    os.remove(vcf)

# ================= MAIN =================
if __name__ == "__main__":
    init_db()

    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(redeem_btn, pattern="redeem"))
    app.add_handler(CallbackQueryHandler(show_admin_panel, pattern="admin"))

    app.add_handler(CallbackQueryHandler(admin_genkey_btn, pattern="admin_genkey"))
    app.add_handler(CallbackQueryHandler(admin_key_list, pattern="admin_keylist"))
    app.add_handler(CallbackQueryHandler(admin_expired_keys, pattern="admin_expired"))
    app.add_handler(CallbackQueryHandler(admin_users_list, pattern="admin_users"))
    app.add_handler(CallbackQueryHandler(admin_block_prompt, pattern="admin_block"))
    app.add_handler(CallbackQueryHandler(admin_unblock_prompt, pattern="admin_unblock"))
    app.add_handler(CallbackQueryHandler(admin_remove_prompt, pattern="admin_remove"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_prompt, pattern="admin_broadcast"))

    # Text handlers (ORDER IS IMPORTANT)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_genkey_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_block_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_remove_text))

    # Broadcast LAST
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
            admin_broadcast_send
        )
    )

    # Documents
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    app.add_error_handler(error_handler)

    print("🚀 VCF Bot Running")
    app.run_polling()
