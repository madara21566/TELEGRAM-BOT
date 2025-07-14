import os
import threading
import sqlite3
import datetime
import time
import psutil
import platform
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template_string, request, redirect, session, send_file, jsonify
from telegram import Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    handle_document, handle_text
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("FLASK_SECRET", "secretkey123")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

ALLOWED_USERS = [7440440924, 7669357884, 7640327597, 5849079477, 2114352076, 8128934569, 7950732287, 5998603010, 7983528757]

DB_FILE = "bot_stats.db"

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

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            user_id INTEGER,
            username TEXT,
            action TEXT,
            timestamp TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS access (
            user_id INTEGER,
            username TEXT,
            type TEXT,
            expires_at TEXT
        )''')
        conn.commit()

def log_action(user_id, username, action):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)", (user_id, username or 'N/A', action, now))
        conn.commit()

    if action == 'start':
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM logs WHERE user_id = ? AND timestamp > datetime('now', '-1 minute')", (user_id,))
            if c.fetchone()[0] > 20 and ADMIN_CHAT_ID:
                Bot(BOT_TOKEN).send_message(chat_id=ADMIN_CHAT_ID, text=f"⚠️ Suspicious: {username} ({user_id}) used /start over 20 times in 1 min.")

def send_email_alert(subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = os.environ.get("ALERT_EMAIL_FROM")
    msg['To'] = os.environ.get("ALERT_EMAIL_TO")
    try:
        with smtplib.SMTP(os.environ.get("SMTP_HOST"), int(os.environ.get("SMTP_PORT", 587))) as server:
            server.starttls()
            server.login(os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS"))
            server.send_message(msg)
    except Exception as e:
        print("Email error:", e)

start_time = datetime.datetime.now()
flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY

@flask_app.route('/')
def home():
    uptime = str(datetime.datetime.now() - start_time).split('.')[0]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
        total_files = c.fetchone()[0]
        c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC LIMIT 100")
        logs = c.fetchall()
    return render_template_string("""
    <h2>✅ Telegram Bot Live</h2>
    <p>🕒 Uptime: {{ uptime }}</p>
    <p>👥 Users: {{ users }} | 📁 Files: {{ files }}</p>
    <p><a href='/admin'>🔐 Admin Panel</a> | <a href='/admin/health'>❤️ Bot Health</a> | <a href='/admin/broadcast'>📢 Broadcast</a></p>
    <div id="live-clock" style="font-size:18px;font-weight:bold;color:green;"></div>
    <script>setInterval(() => {
        const now = new Date();
        document.getElementById("live-clock").innerText = "🕑 Server Time: " + now.toLocaleTimeString();
    }, 1000);</script>
    <table border=1><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr>
    {% for row in logs %}<tr><td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td></tr>{% endfor %}
    </table>
    """, uptime=uptime, users=total_users, files=total_files, logs=logs)

@flask_app.route('/admin/health')
def health():
    try:
        Bot(BOT_TOKEN).get_me()
        status = "🟢 Bot is online and responsive."
        ok = True
    except Exception as e:
        status = f"🔴 Bot is down. Error: {str(e)}"
        ok = False
    uptime = str(datetime.datetime.now() - start_time).split('.')[0]
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    memory = f"{mem.used // (1024**2)} MB / {mem.total // (1024**2)} MB ({mem.percent}%)"
    sysinfo = platform.platform()
    if not ok:
        send_email_alert('🚨 Bot Down Alert', status)
    return render_template_string("""
    <h2>❤️ Bot Health Monitor</h2>
    <p>{{ status }}</p>
    <p>⏱ Uptime: {{ uptime }}</p>
    <p>🧠 CPU Usage: {{ cpu }}%</p>
    <p>💾 Memory Usage: {{ memory }}</p>
    <p>🖥 OS: {{ sysinfo }}</p>
    <a href='/admin'>🔙 Back</a>
    """, status=status, uptime=uptime, cpu=cpu, memory=memory, sysinfo=sysinfo)

@flask_app.route('/admin/broadcast', methods=['GET', 'POST'])
def broadcast():
    if not session.get('admin'): return redirect('/admin')
    message = ""
    if request.method == 'POST':
        text = request.form['text']
        sent = 0
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT DISTINCT user_id FROM logs")
            users = c.fetchall()
        bot = Bot(BOT_TOKEN)
        for (uid,) in users:
            try:
                bot.send_message(chat_id=uid, text=text)
                sent += 1
            except Exception as e:
                print(f"❌ Failed to send to {uid}: {e}")
        message = f"✅ Broadcast sent to {sent} users."
    return render_template_string("""
    <h3>📢 Broadcast Message</h3>
    <form method=post>
        <textarea name=text rows=4 cols=50 placeholder='Your message'></textarea><br>
        <input type=submit value=Send>
    </form>
    <p>{{msg}}</p>
    <a href='/admin'>🔙 Back</a>
    """, msg=message)

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
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT, handle_text))

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask).start()
    application.run_polling()
    
