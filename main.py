# ✅ FINAL SCRIPT: main.py

import os
import threading
import sqlite3
import datetime
import psutil
import shutil
from flask import Flask, render_template_string, request, redirect, session, send_file, jsonify
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    handle_document, handle_text, vcftotxt
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("FLASK_SECRET", "secretkey123")

ALLOWED_USERS = [7440440924, 7669357884, 7640327597, 5849079477, 2114352076, 8128934569, 7950732287, 5998603010, 7983528757]

DB_FILE = "bot_stats.db"
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            user_id INTEGER, username TEXT, action TEXT, timestamp TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS access (
            user_id INTEGER, username TEXT, type TEXT, expires_at TEXT
        )''')
        conn.commit()

def is_authorized(user_id):
    return user_id in ALLOWED_USERS or is_authorized_in_db(user_id)

def is_authorized_in_db(user_id):
    now = datetime.datetime.now()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM access WHERE type='temporary' AND expires_at IS NOT NULL AND datetime(expires_at) < ?", (now,))
        c.execute("SELECT * FROM access WHERE user_id=?", (user_id,))
        return bool(c.fetchone())

def parse_duration(duration_str):
    n = int(duration_str[:-1])
    unit = duration_str[-1]
    if unit == "m": return datetime.datetime.now() + datetime.timedelta(minutes=n)
    if unit == "h": return datetime.datetime.now() + datetime.timedelta(hours=n)
    if unit == "d": return datetime.datetime.now() + datetime.timedelta(days=n)
    return None

def log_action(user_id, username, action):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
                  (user_id, username or 'N/A', action, now))
        conn.commit()

flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY
start_time = datetime.datetime.now()

@flask_app.route('/')
def home():
    uptime = str(datetime.datetime.now() - start_time).split('.')[0]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
        users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
        files = c.fetchone()[0]
        c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC LIMIT 100")
        logs = c.fetchall()
    return render_template_string("""
    <h2>✅ Telegram Bot Live</h2>
    <p>🕒 Uptime: {{ uptime }}</p>
    <p>👥 Users: {{ users }} | 📁 Files: {{ files }}</p>
    <p><a href='/admin'>🔐 Admin Panel</a></p>
    <table border=1><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr>
    {% for row in logs %}<tr><td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td></tr>{% endfor %}
    </table>
    """, uptime=uptime, users=users, files=files, logs=logs)

@flask_app.route('/status')
def status():
    uptime = str(datetime.datetime.now() - start_time).split('.')[0]
    ram = psutil.virtual_memory()
    disk = shutil.disk_usage(".")
    return render_template_string("""
    <h2>📊 Bot Status</h2>
    <p>🕒 Uptime: {{ uptime }}</p>
    <p>💾 RAM Usage: {{ ram.used // (1024*1024) }} MB / {{ ram.total // (1024*1024) }} MB</p>
    <p>📂 Disk: {{ disk.used // (1024*1024) }} MB used of {{ disk.total // (1024*1024) }} MB</p>
    <p><a href='/'>⬅️ Back</a></p>
    """, uptime=uptime, ram=ram, disk=disk)

@flask_app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin/dashboard')
        return "❌ Wrong password"
    return '''<form method=post><h3>🔐 Admin Login</h3>Password: <input type=password name=password><input type=submit value=Login></form>'''

@flask_app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'): return redirect('/admin')
    return '''
    <h2>📊 Admin Dashboard</h2>
    <ul>
        <li><a href="/admin/live-logs">📺 Live Logs</a></li>
        <li><a href="/admin/access">🔐 Access Control</a></li>
        <li><a href="/admin/broadcast">📢 Broadcast</a></li>
        <li><a href="/admin/system">🛠 System Info</a></li>
        <li><a href="/admin/logout">🚪 Logout</a></li>
    </ul>
    '''

@flask_app.route('/admin/broadcast', methods=['GET', 'POST'])
def broadcast():
    if not session.get('admin'): return redirect('/admin')
    message = ""
    if request.method == 'POST':
        text = request.form.get('message')
        if text:
            for uid in ALLOWED_USERS:
                try:
                    application.bot.send_message(chat_id=uid, text=text)
                except Exception as e:
                    print(f"Broadcast error: {e}")
            message = "✅ Broadcast sent!"
    return render_template_string("""
    <h3>📢 Broadcast Message</h3>
    <form method=post>
        <textarea name=message rows=6 cols=60></textarea><br>
        <input type=submit value='Send Broadcast'>
    </form>
    <p>{{msg}}</p>
    <p><a href='/admin/dashboard'>⬅️ Back</a></p>
    """, msg=message)

@flask_app.route('/admin/system')
def system():
    if not session.get('admin'): return redirect('/admin')
    ram = psutil.virtual_memory()
    disk = shutil.disk_usage(".")
    file_count = len([f for f in os.listdir('.') if os.path.isfile(f)])
    return render_template_string("""
    <h3>🛠 System Monitor</h3>
    <ul>
        <li>RAM: {{ ram.used // (1024*1024) }} MB / {{ ram.total // (1024*1024) }} MB</li>
        <li>Disk: {{ disk.used // (1024*1024) }} MB used of {{ disk.total // (1024*1024) }} MB</li>
        <li>Files in working dir: {{ file_count }}</li>
    </ul>
    <p><a href='/admin/dashboard'>⬅️ Back</a></p>
    """, ram=ram, disk=disk, file_count=file_count)

@flask_app.route('/admin/logout')
def logout():
    session.clear()
    return redirect('/admin')

application = Application.builder().token(BOT_TOKEN).build()

def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        if not is_authorized(user.id):
            await update.message.reply_text("❌ You don't have access to use this bot.")
            return
        log_action(user.id, user.username, command_name)
        return await handler_func(update, context)
    return wrapper

application.add_handler(CommandHandler("start", protected(start, "start")))
application.add_handler(CommandHandler("setfilename", protected(set_filename, "setfilename")))
application.add_handler(CommandHandler("setcontactname", protected(set_contact_name, "setcontactname")))
application.add_handler(CommandHandler("setlimit", protected(set_limit, "setlimit")))
application.add_handler(CommandHandler("setstart", protected(set_start, "setstart")))
application.add_handler(CommandHandler("setvcfstart", protected(set_vcf_start, "setvcfstart")))
application.add_handler(CommandHandler("makevcf", protected(make_vcf_command, "makevcf")))
application.add_handler(CommandHandler("merge", protected(merge_command, "merge")))
application.add_handler(CommandHandler("done", protected(done_merge, "done")))
application.add_handler(CommandHandler("vcftotxt", protected(vcftotxt, "vcftotxt")))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT, handle_text))

# Run Flask and Telegram together

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask).start()
    application.run_polling()
    
