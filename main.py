from telegram.ext import ApplicationBuilder
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    export_users, owner_panel, handle_callback, handle_owner_input,
    handle_document, handle_text
)
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters

TOKEN = "7869581039:AAGWWs3d75a0PXjCwG59JFDtqkkPicuRPWQ"

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("setfilename", set_filename))
app.add_handler(CommandHandler("setcontactname", set_contact_name))
app.add_handler(CommandHandler("setlimit", set_limit))
app.add_handler(CommandHandler("setstart", set_start))
app.add_handler(CommandHandler("setvcfstart", set_vcf_start))
app.add_handler(CommandHandler("makevcf", make_vcf_command))
app.add_handler(CommandHandler("merge", merge_command))
app.add_handler(CommandHandler("done", done_merge))
app.add_handler(CommandHandler("exportusers", export_users))
app.add_handler(CommandHandler("panel", owner_panel))
app.add_handler(CallbackQueryHandler(handle_callback))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_owner_input))
app.add_handler(MessageHandler(filters.TEXT, handle_text))

if __name__ == "__main__":
    app.run_polling()
