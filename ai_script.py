import os
import json
import re
import pandas as pd
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 7640327597
ACCESS_FILE = "allowed_users.json"

ALLOWED_USERS = []
TEMP_USERS = {}

def load_allowed_users():
    global ALLOWED_USERS
    if os.path.exists(ACCESS_FILE):
        with open(ACCESS_FILE, "r") as f:
            ALLOWED_USERS[:] = json.load(f)
    else:
        ALLOWED_USERS.append(OWNER_ID)
        save_allowed_users()

def save_allowed_users():
    with open(ACCESS_FILE, "w") as f:
        json.dump(ALLOWED_USERS, f)

load_allowed_users()

def is_authorized(user_id):
    return user_id in ALLOWED_USERS or user_id in TEMP_USERS

# ========= Defaults ============
BOT_START_TIME = datetime.utcnow()
user_file_names = {}
user_contact_names = {}
user_limits = {}
user_start_indexes = {}
user_vcf_start_numbers = {}
merge_data = {}
group_suffix = {}

# ========= Inline Panel ============
async def access_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        chat = update.message.chat
    else:
        chat = update.callback_query.message.chat
    if chat.id != OWNER_ID:
        await update.effective_message.reply_text("❌ You are not the owner.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Grant Access", callback_data="grant_access")],
        [InlineKeyboardButton("🚫 Revoke Access", callback_data="revoke_access")],
        [InlineKeyboardButton("🧾 List Users", callback_data="list_access")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_access")],
        [InlineKeyboardButton("⏳ Temporary Access", callback_data="temp_access")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
    ]
    await update.effective_message.reply_text("🔐 Access Panel", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    match query.data:
        case "open_access":
            await access_command(update, context)
        case "grant_access":
            context.user_data["awaiting_grant"] = True
            await query.edit_message_text("Send user IDs to grant access (comma or space):")
        case "revoke_access":
            context.user_data["awaiting_revoke"] = True
            await query.edit_message_text("Send user IDs to revoke:")
        case "list_access":
            users = ALLOWED_USERS + list(TEMP_USERS.keys())
            msg = "✅ Allowed users:\n" + "\n".join([str(u) for u in users])
            await query.edit_message_text(msg)
        case "broadcast_access":
            context.user_data["awaiting_broadcast"] = True
            await query.edit_message_text("📢 Send the message to broadcast:")
        case "temp_access":
            context.user_data["awaiting_temp"] = True
            await query.edit_message_text("Send ID and minutes (e.g. `123456 30`):")
        case "back_to_start":
            await start(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Handle pending access commands
    if context.user_data.get("awaiting_grant"):
        context.user_data["awaiting_grant"] = False
        ids = re.findall(r'\d+', update.message.text)
        for uid in ids:
            if int(uid) not in ALLOWED_USERS:
                ALLOWED_USERS.append(int(uid))
        save_allowed_users()
        await update.message.reply_text(f"✅ Granted access to: {', '.join(ids)}")
        return

    if context.user_data.get("awaiting_revoke"):
        context.user_data["awaiting_revoke"] = False
        ids = re.findall(r'\d+', update.message.text)
        for uid in ids:
            if int(uid) in ALLOWED_USERS:
                ALLOWED_USERS.remove(int(uid))
        save_allowed_users()
        await update.message.reply_text(f"❌ Revoked access from: {', '.join(ids)}")
        return

    if context.user_data.get("awaiting_broadcast"):
        context.user_data["awaiting_broadcast"] = False
        for uid in ALLOWED_USERS + list(TEMP_USERS.keys()):
            try:
                await context.bot.send_message(uid, update.message.text)
            except:
                continue
        await update.message.reply_text("📢 Broadcast sent.")
        return

    if context.user_data.get("awaiting_temp"):
        context.user_data["awaiting_temp"] = False
        parts = update.message.text.strip().split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            uid = int(parts[0])
            mins = int(parts[1])
            TEMP_USERS[uid] = datetime.utcnow() + timedelta(minutes=mins)
            await update.message.reply_text(f"⏳ Temp access given to {uid} for {mins} min.")
        else:
            await update.message.reply_text("❌ Invalid format.")
        return

    # Fallback to regular number handling
    if not is_authorized(user_id): return
    nums = re.findall(r'\d{7,}', update.message.text)
    await update.message.reply_text(f"Received {len(nums)} numbers.")

# ========= Start Menu ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    h, m = divmod(uptime.seconds // 60, 60)
    text = f"👋 Welcome!\nUptime: {h}h {m}m\n\nUse /access for admin panel."
    buttons = [[InlineKeyboardButton("Access Panel 🔐", callback_data="open_access")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# ========= App Builder ==============
application = ApplicationBuilder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("access", access_command))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
