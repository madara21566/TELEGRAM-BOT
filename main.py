import os
import asyncio
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes
)

from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    export_users, owner_panel, handle_callback, handle_owner_input,
    handle_document, handle_text
)

# Logging setup
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")  # e.g. godmadarafile_bot

app = Flask(__name__)
telegram_app = None  # Global variable for reuse


@app.route(f"/{BOT_USERNAME}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)

    async def process():
        await telegram_app.process_update(update)

    asyncio.run(process())
    return "ok"


@app.route("/")
def home():
    return "✅ Bot is running on Render with Webhook!"


async def build_app():
    global telegram_app
    telegram_app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Handlers
    telegram_app.add_handler(CommandHandler('start', start))
    telegram_app.add_handler(CommandHandler('setfilename', set_filename))
    telegram_app.add_handler(CommandHandler('setcontactname', set_contact_name))
    telegram_app.add_handler(CommandHandler('setlimit', set_limit))
    telegram_app.add_handler(CommandHandler('setstart', set_start))
    telegram_app.add_handler(CommandHandler('setvcfstart', set_vcf_start))
    telegram_app.add_handler(CommandHandler('makevcf', make_vcf_command))
    telegram_app.add_handler(CommandHandler('merge', merge_command))
    telegram_app.add_handler(CommandHandler('done', done_merge))
    telegram_app.add_handler(CommandHandler('exportusers', export_users))
    telegram_app.add_handler(CommandHandler('panel', owner_panel))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))
    telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_owner_input))
    telegram_app.add_handler(MessageHandler(filters.TEXT & filters.COMMAND, handle_text))


if __name__ == "__main__":
    asyncio.run(build_app())
    app.run(host="0.0.0.0", port=5000)
