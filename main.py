# imports
import os, threading, sqlite3, datetime, time, psutil, platform, smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template_string, request, redirect, session, send_file, jsonify
from telegram import Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    handle_document, handle_text
)

# environment
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("FLASK_SECRET", "secretkey123")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

# email config
EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM")
EMAIL_TO = os.environ.get("ALERT_EMAIL_TO")
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))

# manual access
ALLOWED_USERS = [7440440924, 7669357884, 7640327597, 5849079477, 2114352076, 8128934569, 7950732287, 5998603010, 7983528757]
DB_FILE = "bot_stats.db"

# auth
def is_authorized(user_id):
    return user_id in ALLOWED_USERS or is_authorized_in_db(user_id)

def is_authorized_in_db(user_id):
    now = datetime.datetime.now()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM access WHERE type='temporary' AND expires_at IS NOT NULL AND datetime(expires_at) < ?", (now,))
        c.execute("SELECT * FROM access WHERE user_id=?", (user_id,))
        return bool(c.fetchone())

# duration
def parse_duration(duration_str):
    n = int(duration_str[:-1])
    unit = duration_str[-1]
    if unit == "m": return datetime.datetime.now() + datetime.timedelta(minutes=n)
    if unit == "h": return datetime.datetime.now() + datetime.timedelta(hours=n)
    if unit == "d": return datetime.datetime.now() + datetime.timedelta(days=n)

# init
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS logs (user_id INTEGER, username TEXT, action TEXT, timestamp TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS access (user_id INTEGER, username TEXT, type TEXT, expires_at TEXT)''')
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
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
    except Exception as e:
        print("Email error:", e)

# flask app
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
    return render_template_string(\"\"\"\n    <h2>✅ Telegram Bot Live</h2>\n    <p>🕒 Uptime: {{ uptime }}</p>\n    <p>👥 Users: {{ users }} | 📁 Files: {{ files }}</p>\n    <p><a href='/admin'>🔐 Admin Panel</a> | <a href='/admin/health'>❤️ Bot Health</a> | <a href='/admin/broadcast'>📢 Broadcast</a></p>\n    <div id=\"live-clock\" style=\"font-size:18px;font-weight:bold;color:green;\"></div>\n    <script>setInterval(() => {\n        const now = new Date();\n        document.getElementById(\"live-clock\").innerText = \"🕑 Server Time: \" + now.toLocaleTimeString();\n    }, 1000);</script>\n    <table border=1><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr>\n    {% for row in logs %}<tr><td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td></tr>{% endfor %}\n    </table>\n    \"\"\", uptime=uptime, users=total_users, files=total_files, logs=logs)

@flask_app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    error = ""
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin/dashboard")
        error = "❌ Wrong password"
    return render_template_string(\"\"\"\n    <h2>🔐 Admin Login</h2>\n    <form method='post'>\n        <input type='password' name='password' placeholder='Password'>\n        <button type='submit'>Login</button>\n    </form>\n    <p style='color:red;'>{{error}}</p>\n    \"\"\", error=error)

@flask_app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'): return redirect('/admin')
    return render_template_string(\"\"\"\n    <h2>🛠 Admin Dashboard</h2>\n    <ul>\n        <li><a href='/admin/health'>❤️ Bot Health</a></li>\n        <li><a href='/admin/broadcast'>📢 Broadcast</a></li>\n        <li><a href='/admin/logout'>🚪 Logout</a></li>\n    </ul>\n    \"\"\")

@flask_app.route('/admin/logout')
def logout():
    session.pop('admin', None)
    return redirect('/')

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
    memory = f\"{mem.used // (1024**2)} MB / {mem.total // (1024**2)} MB ({mem.percent}%)\"
    sysinfo = platform.platform()
    if not ok:
        send_email_alert('🚨 Bot Down Alert', status)
    return render_template_string(\"\"\"\n    <h2>❤️ Bot Health Monitor</h2>\n    <p>{{ status }}</p>\n    <p>⏱ Uptime: {{ uptime }}</p>\n    <p>🧠 CPU Usage: {{ cpu }}%</p>\n    <p>💾 Memory Usage: {{ memory }}</p>\n    <p>🖥 OS: {{ sysinfo }}</p>\n    <a href='/admin'>🔙 Back</a>\n    \"\"\", status=status, uptime=uptime, cpu=cpu, memory=memory, sysinfo=sysinfo)

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
    return render_template_string(\"\"\"\n    <h3>📢 Broadcast Message</h3>\n    <form method=post>\n        <textarea name=text rows=4 cols=50 placeholder='Your message'></textarea><br>\n        <input type=submit value=Send>\n    </form>\n    <p>{{msg}}</p>\n    <a href='/admin'>🔙 Back</a>\n    \"\"\", msg=message)

# bot
application = Application.builder().token(BOT_TOKEN).build()
def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        if not is_authorized(user.id):
            await update.message.reply_text("❌ You don't have access.")
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

# start
def run_flask(): flask_app.run(host='0.0.0.0', port=8080)
if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask).start()
    application.run_polling()
