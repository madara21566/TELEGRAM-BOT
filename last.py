
from telegram import Update
from telegram.ext import ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is alive!")

OWNER_ID = 123456789  # replace with your ID
GROUP_ADMINS = set()
