# ✅ Updated main.py with All Command Handlers and Usage Logging

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
    handle_document, handle_text,
    fix_vcf, info_command, rename_command, vcf_to_txt, set_group
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = "bot_stats.db"

# ✅ DB Setup
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

# ✅ Flask for Web Status
flask_app = Flask(__name__)
start_time = datetime.datetime.now()

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

# ✅ Usage Tracking Wrapper
def track_usage(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        log_action(user.id, user.username, command_name)
        return await handler_func(update, context)
    return wrapper

# ✅ Init DB
init_db()

# ✅ Flask Thread

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# ✅ Telegram Bot Setup
application = Application.builder().token(BOT_TOKEN).build()

# ▶️ Old Commands
application.add_handler(CommandHandler("start", track_usage(start, "start")))
application.add_handler(CommandHandler("setfilename", track_usage(set_filename, "setfilename")))
application.add_handler(CommandHandler("setcontactname", track_usage(set_contact_name, "setcontactname")))
application.add_handler(CommandHandler("setlimit", track_usage(set_limit, "setlimit")))
application.add_handler(CommandHandler("setstart", track_usage(set_start, "setstart")))
application.add_handler(CommandHandler("setvcfstart", track_usage(set_vcf_start, "setvcfstart")))
application.add_handler(CommandHandler("makevcf", track_usage(make_vcf_command, "makevcf")))
application.add_handler(CommandHandler("merge", track_usage(merge_command, "merge")))
application.add_handler(CommandHandler("done", track_usage(done_merge, "done")))

# ▶️ New Feature Commands
application.add_handler(CommandHandler("fixvcf", track_usage(fix_vcf, "fixvcf")))
application.add_handler(CommandHandler("info", track_usage(info_command, "info")))
application.add_handler(CommandHandler("rename", track_usage(rename_command, "rename")))
application.add_handler(CommandHandler("vcftotxt", track_usage(vcf_to_txt, "vcftotxt")))
application.add_handler(CommandHandler("setgroup", track_usage(set_group, "setgroup")))

# ▶️ File & Text Handlers
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ✅ Run Both Flask and Bot
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    application.run_polling()
    
