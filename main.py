import os
import threading
from flask import Flask
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    export_users, owner_panel, handle_callback, handle_owner_input,
    handle_document, handle_text
)

# Flask app
app = Flask(__name__)

@app.route("/")
def index():
    return "✅ Bot is running!"

# Telegram bot setup
BOT_TOKEN = os.environ.get("BOT_TOKEN")
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
telegram_app.add_handler(MessageHandler(filters.TEXT, handle_text))

def start_polling():
    telegram_app.run_polling()

if __name__ == "__main__":
    # Start Telegram polling in background
    polling_thread = threading.Thread(target=start_polling, daemon=True)
    polling_thread.start()

    # Start Flask server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
