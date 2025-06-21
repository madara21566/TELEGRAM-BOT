
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import telegram.ext as tg_ext
import asyncio
import os

from last import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge, owner_panel,
    export_users, handle_callback, handle_owner_input, handle_document,
    handle_text, TELEGRAM_BOT_TOKEN, OWNER_ID, GROUP_ADMINS
)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

application = Application.builder().bot(bot).build()
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('setfilename', set_filename))
application.add_handler(CommandHandler('setcontactname', set_contact_name))
application.add_handler(CommandHandler('setlimit', set_limit))
application.add_handler(CommandHandler('setstart', set_start))
application.add_handler(CommandHandler('setvcfstart', set_vcf_start))
application.add_handler(CommandHandler('makevcf', make_vcf_command))
application.add_handler(CommandHandler('merge', merge_command))
application.add_handler(CommandHandler('done', done_merge))
application.add_handler(CommandHandler('panel', owner_panel))
application.add_handler(CommandHandler('exportusers', export_users))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & (filters.User(user_id=OWNER_ID) | filters.User(user_id=GROUP_ADMINS)), handle_owner_input))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

@app.route('/')
def home():
    return 'Bot is running!'

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    await application.process_update(update)
    return 'ok'

if __name__ == "__main__":
    app.run(debug=True, port=5000)
