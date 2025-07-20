import os
import threading
import sqlite3
import datetime
from flask import Flask, render_template_string
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from ai_script import handle_text
from dotenv import load_dotenv

# ✅ Load env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ✅ DB Setup
DB_FILE = "ai_logs.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
                    user_id INTEGER,
                    username TEXT,
                    action TEXT,
                    timestamp TEXT
                )''')
    conn.commit()
    conn.close()

def log_action(user_id, username, action):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, username or 'N/A', action, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

# ✅ Uptime Tracker
start_time = datetime.datetime.now()

# ✅ Flask App
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM logs WHERE action='chat'")
    total_chats = c.fetchone()[0]

    c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC")
    logs = c.fetchall()
    conn.close()

    uptime = str(datetime.datetime.now() - start_time).split('.')[0]

    return render_template_string("""
    <html><head><title>AI Bot Status</title></head><body>
    <h2>🤖 AI Chat + VCF Bot Status</h2>
    <p>🕒 <b>Uptime:</b> {{ uptime }}</p>
    <p>👥 <b>Total Users:</b> {{ total_users }}</p>
    <p>💬 <b>Total Conversations:</b> {{ total_chats }}</p>
    <hr>
    <h3>📋 Recent Activity</h3>
    <table border="1" cellpadding="5">
        <tr><th>#</th><th>Username</th><th>User ID</th><th>Action</th><th>Time</th></tr>
        {% for row in logs %}
        <tr>
            <td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td>
        </tr>
        {% endfor %}
    </table>
    </body></html>
    """, uptime=uptime, total_users=total_users, total_chats=total_chats, logs=logs)

# ✅ Track usage on every message
def track_usage(handler_func):
    async def wrapper(update, context):
        user = update.effective_user
        log_action(user.id, user.username, "chat")
        return await handler_func(update, context)
    return wrapper

# ✅ Init DB
init_db()

# ✅ Run Flask on side
def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# ✅ Telegram Bot Setup
app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_usage(handle_text)))

# ✅ Start everything
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app.run_polling()
