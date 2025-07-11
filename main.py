import os
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from aiohttp import web
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    handle_document, handle_text
)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
RENDER_URL = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
WEBHOOK_URL = f"https://{RENDER_URL}/{BOT_USERNAME}"

# ✅ Custom route for "/"
async def homepage(request):
    return web.Response(text="✅ Telegram Bot is Running on Render!")

# ✅ Create the app
application = Application.builder().token(BOT_TOKEN).build()

# ✅ Set aiohttp app
aio_app = application.web_app
aio_app.router.add_get("/", homepage)

# ✅ Add Handlers
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

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_USERNAME,
        webhook_url=WEBHOOK_URL
    )
