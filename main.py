import os
import threading
from flask import Flask
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    handle_document, handle_text
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ✅ 1. Create Flask App for website route
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Telegram Bot is Running on Render!"

# Run Flask in background thread
def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# ✅ 2. Create Telegram Bot Application
application = Application.builder().token(BOT_TOKEN).build()

# ✅ 3. Add Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("setfilename", set_filename))
application.add_handler(CommandHandler("setcontactname", set_contact_name))
application.add_handler(CommandHandler("setlimit", set_limit))
application.add_handler(CommandHandler("setstart", set_start))
application.add_handler(CommandHandler("setvcfstart", set_vcf_start))
application.add_handler(CommandHandler("makevcf", make_vcf_command))
application.add_handler(CommandHandler("merge", merge_command))
application.add_handler(CommandHandler("done", done_merge))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT, handle_text))

# ✅ 4. Run both Flask and Bot Polling
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    application.run_polling()
