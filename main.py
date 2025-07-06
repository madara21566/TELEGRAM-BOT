import os
import traceback
import sys
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from NIKALLLLLLL import (
    start,
    set_filename,
    set_contact_name,
    set_limit,
    set_start,
    set_vcf_start,
    make_vcf_command,
    merge_command,
    done_merge,
    handle_document,
    handle_text,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{BOT_USERNAME}"

# ✅ Create Application
application = Application.builder().token(BOT_TOKEN).build()

# ✅ Error Handler
async def error_handler(update, context):
    print("=== Exception Occurred ===")
    traceback.print_exception(
        type(context.error),
        context.error,
        context.error.__traceback__,
        file=sys.stdout
    )

# ✅ Handlers
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
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_error_handler(error_handler)

if __name__ == "__main__":
    # Get port from Render env variable or default to 10000
    PORT = int(os.environ.get("PORT", 10000))
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_USERNAME,
        webhook_url=WEBHOOK_URL
    )
