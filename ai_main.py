import os
import threading
import datetime
import sqlite3
from flask import Flask
from telegram.ext import Application, MessageHandler, filters
from ai_script import handle_text, handle_document
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "ai_bot_logs.db"

# Init DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS logs (user_id INTEGER, username TEXT, action TEXT, timestamp TEXT)")
    conn.commit()
    conn.close()

def log_action(user_id, username, action):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, username or 'N/A', action, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

init_db()
start_time = datetime.datetime.now()

app = Flask(__name__)
@app.route('/')
def status():
    uptime = str(datetime.datetime.now() - start_time).split('.')[0]
    return f"<h2>🤖 AI VCF Bot Running</h2><p>Uptime: {uptime}</p>"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

telegram_app = Application.builder().token(BOT_TOKEN).build()
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    telegram_app.run_polling()
