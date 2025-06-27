import os
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

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{BOT_USERNAME}"

# Create Application
application = Application.builder().token(BOT_TOKEN).build()

# Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("setfilename", set_filename))
application.add_handler(CommandHandler("setcontactname", set_contact_name))
application.add_handler(CommandHandler("setlimit", set_limit))
application.add_handler(CommandHandler("setstart", set_start))
application.add_handler(CommandHandler("setvcfstart", set_vcf_start))
application.add_handler(CommandHandler("makevcf", make_vcf_command))
application.add_handler(CommandHandler("merge", merge_command))
application.add_handler(CommandHandler("done", done_merge))
application.add_handler(CommandHandler("exportusers", export_users))
application.add_handler(CommandHandler("panel", owner_panel))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_owner_input))
application.add_handler(MessageHandler(filters.TEXT, handle_text))

if __name__ == "__main__":
    # Start webhook directly (No Flask needed)
    application.run_webhook(
        listen="0.0.0.0",
        port=5000,
        url_path=BOT_USERNAME,
        webhook_url=WEBHOOK_URL
    )
