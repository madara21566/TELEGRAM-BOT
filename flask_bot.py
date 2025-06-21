
import os
import logging
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("7727685861:AAE_tR7qsTx-_NlxfwQ-JgqeJDkpvnXEYkg")
bot = Bot(token=TOKEN)

app = Flask(__name__)

application = ApplicationBuilder().token(TOKEN).build()

# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is live on Render using Webhook!")

# Add command handler
application.add_handler(CommandHandler("start", start))

# Webhook route
@app.route("/", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    await application.process_update(update)
    return "ok"

# Root route
@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
