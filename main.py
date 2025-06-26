import os
import asyncio
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    export_users, owner_panel, handle_callback, handle_owner_input,
    handle_document, handle_text
)

# Token & Bot username from environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")  # godmadarafile_bot

# Bot and Application setup
bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

telegram_app = Application.builder().token(BOT_TOKEN).build()

# Handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("setfilename", set_filename))
telegram_app.add_handler(CommandHandler("setcontactname", set_contact_name))
telegram_app.add_handler(CommandHandler("setlimit", set_limit))
telegram_app.add_handler(CommandHandler("setstart", set_start))
telegram_app.add_handler(CommandHandler("setvcfstart", set_vcf_start))
telegram_app.add_handler(CommandHandler("makevcf", make_vcf_command))
telegram_app.add_handler(CommandHandler("merge", merge_command))
telegram_app.add_handler(CommandHandler("done", done_merge))
telegram_app.add_handler(CommandHandler("exportusers", export_users))
telegram_app.add_handler(CommandHandler("panel", owner_panel))
telegram_app.add_handler(CallbackQueryHandler(handle_callback))
telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_owner_input))
telegram_app.add_handler(MessageHandler(filters.TEXT & filters.COMMAND, handle_text))


@app.route(f"/{BOT_USERNAME}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)

    async def process():
        await telegram_app.process_update(update)

    asyncio.run(process())
    return "ok"


@app.route("/")
def home():
    return "✅ Bot is running on Render with Webhook!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
