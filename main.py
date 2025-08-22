import os
import threading
import sqlite3
import datetime
from flask import Flask, render_template_string, request, redirect, session, send_file, jsonify
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    handle_document, handle_text
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("FLASK_SECRET", "secretkey123")

# ✅ MANUAL ACCESS CONTROL
ALLOWED_USERS = [8047407478,7043391463,7440046924,7118726445,7492026653,5989680310,7440046924,7669357884,7640327597,5849097477,8128934569,7950732287,5989680310,7983528757,5564571047]

def is_authorized(user_id):
    return user_id in ALLOWED_USERS or is_authorized_in_db(user_id)

def is_authorized_in_db(user_id):
    now = datetime.datetime.now()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM access WHERE type='temporary' AND expires_at IS NOT NULL AND datetime(expires_at) < ?", (now,))
        c.execute("SELECT * FROM access WHERE user_id=?", (user_id,))
        row = c.fetchone()
        return bool(row)

def parse_duration(duration_str):
    n = int(duration_str[:-1])
    unit = duration_str[-1]
    if unit == "m": return datetime.datetime.now() + datetime.timedelta(minutes=n)
    if unit == "h": return datetime.datetime.now() + datetime.timedelta(hours=n)
    if unit == "d": return datetime.datetime.now() + datetime.timedelta(days=n)
    return None

# ========== DB Setup ==========
DB_FILE = "bot_stats.db"
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
        c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
                  (user_id, username or 'N/A', action, now))
        conn.commit()

# ========== Flask App ==========
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
    <p>🕒 Uptime: <span id="uptime">{{ uptime }}</span></p>
    <p>👥 Users: {{ users }} | 📁 Files: {{ files }}</p>
    <p><a href='/admin'>🔐 Admin Panel</a></p>
    <table border=1><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr>
    {% for row in logs %}<tr><td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td></tr>{% endfor %}
    </table>

    <script>
    function toSeconds(str) {
        let parts = str.split(\":\").map(Number);
        return parts[0]*3600 + parts[1]*60 + parts[2];
    }

    let uptimeElem = document.getElementById("uptime");
    let seconds = toSeconds(uptimeElem.innerText);

    setInterval(() => {
        seconds++;
        let h = String(Math.floor(seconds/3600)).padStart(2,'0');
        let m = String(Math.floor((seconds%3600)/60)).padStart(2,'0');
        let s = String(seconds%60).padStart(2,'0');
        uptimeElem.innerText = `${h}:${m}:${s}`;
    }, 1000);
    </script>
    """, uptime=uptime, users=total_users, files=total_files, logs=logs)

# ========== Admin Panel ==========
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
        <li><a href="/admin/logout">🚪 Logout</a></li>
    </ul>
    '''

@flask_app.route('/admin/live-logs')
def live_logs():
    if not session.get('admin'): return redirect('/admin')
    return """
    <h3>📺 Live Logs</h3>
    <div id="logbox"></div>
    <script>
    setInterval(() => {
        fetch('/admin/log-feed').then(res => res.json()).then(data => {
            document.getElementById('logbox').innerHTML = `
            <table border=1><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr>
            ${data.map((r,i)=>`<tr><td>${i+1}</td><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td></tr>`).join('')}
            </table>`;
        });
    }, 3000);
    </script>
    """

@flask_app.route('/admin/log-feed')
def log_feed():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC LIMIT 50")
        return jsonify(c.fetchall())

@flask_app.route('/admin/access', methods=['GET', 'POST'])
def access_panel():
    if not session.get('admin'): return redirect('/admin')
    message = ""
    if request.method == 'POST':
        uid = int(request.form['user_id'])
        uname = request.form['username']
        atype = request.form['type']
        expires_at = None
        if atype == 'temporary':
            expires_at = parse_duration(request.form['duration']).strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO access (user_id, username, type, expires_at) VALUES (?, ?, ?, ?)",
                      (uid, uname, atype, expires_at))
            conn.commit()
        message = "✅ Access granted!"
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM access WHERE type='temporary' AND expires_at IS NOT NULL AND datetime(expires_at) < ?", (datetime.datetime.now(),))
        c.execute("SELECT * FROM access")
        rows = c.fetchall()
    return render_template_string("""
    <h3>🔐 Manage Access</h3>
    <form method=post>
        User ID: <input name=user_id required>
        Username: <input name=username>
        Type: <select name=type><option value=permanent>Permanent</option><option value=temporary>Temporary</option></select>
        Duration (1m,2h,1d): <input name=duration>
        <input type=submit value=Add>
    </form>
    <p>{{msg}}</p>
    <table border=1><tr><th>ID</th><th>User</th><th>Type</th><th>Expires</th><th>Delete</th></tr>
    {% for r in rows %}
        <tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3] or '∞'}}</td>
        <td><a href='/admin/delaccess?uid={{r[0]}}'>❌</a></td></tr>
    {% endfor %}
    </table>
    """, rows=rows, msg=message)

@flask_app.route('/admin/delaccess')
def del_access():
    if not session.get('admin'): return redirect('/admin')
    uid = request.args.get('uid')
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM access WHERE user_id=?", (uid,))
        conn.commit()
    return redirect('/admin/access')

@flask_app.route('/admin/logout')
def logout():
    session.clear()
    return redirect('/admin')

# ========== Telegram Bot ==========
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

# ========== Run ==========
def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask).start()
    application.run_polling()
    
