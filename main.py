import os
import threading
import sqlite3
import datetime
from flask import Flask, render_template_string
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

# ✅ Database Setup
DB_FILE = "bot_stats.db"

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

# ✅ Uptime Tracking
start_time = datetime.datetime.now()

# ✅ Flask App
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
    total_files = c.fetchone()[0]

    c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC")
    logs = c.fetchall()
    conn.close()

    uptime = str(datetime.datetime.now() - start_time).split('.')[0]

    return render_template_string("""
    <html><head><title>Bot Status</title></head><body>
    <h2>✅ Telegram Bot Live Status</h2>
    <p>🕒 <b>Uptime:</b> {{ uptime }}</p>
    <p>👥 <b>Total Users:</b> {{ total_users }}</p>
    <p>📁 <b>Total Files Generated:</b> {{ total_files }}</p>
    <hr>
    <h3>📋 Full User History</h3>
    <table border="1" cellpadding="5">
        <tr><th>No.</th><th>Username</th><th>User ID</th><th>Action</th><th>Time</th></tr>
        {% for row in logs %}
        <tr>
            <td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td>
        </tr>
        {% endfor %}
    </table>
    </body></html>
    """, uptime=uptime, total_users=total_users, total_files=total_files, logs=logs)

# ✅ Wrapper for handlers to auto-log usage
def track_usage(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        log_action(user.id, user.username, command_name)
        return await handler_func(update, context)
    return wrapper

# ✅ Init DB
init_db()

# ✅ Run Flask in background

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

# ✅ Telegram Bot Setup
application = Application.builder().token(BOT_TOKEN).build()

application.app.add_handler(CommandHandler("start", start))
application.app.add_handler(CommandHandler("rename", rename))
application.app.add_handler(CommandHandler("setgroup", setgroup))
application.app.add_handler(CommandHandler("setfilename", setfilename))
application.app.add_handler(CommandHandler("txttovcf", txttovcf))
application.app.add_handler(CommandHandler("vcftotxt", vcftotxt))
application.app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    application.run_polling()

    
