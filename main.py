from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from flask import Flask
import threading

# Telegram Bot Token
TOKEN = "7869581039:AAGWWs3d75a0PXjCwG59JFDtqkkPicuRPWQ"

# Flask app for uptime monitoring
flask_app = Flask(__name__)

@flask_app.route("/")
def health():
    return "Bot is alive!", 200

# Telegram bot handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Bot is working 24/7 🚀")

# Function to run Flask in a separate thread
def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

# Function to run the bot
def run_bot():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    run_bot()
