import os
import threading
import sqlite3
import datetime
import traceback
from flask import Flask, render_template_string, request, redirect, session, jsonify
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, set_country_code, set_group_number,
    make_vcf_command, merge_command, done_merge,
    handle_document, handle_text, OWNER_ID
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("FLASK_SECRET", "secretkey123")

# ✅ Access Control
ALLOWED_USERS = [8047407478,7043391463,7440046924,7118726445,7492026653,5989680310,
                 7440046924,7669357884,7640327597,5849097477,8128934569,7950732287,
                 5989680310,7983528757,5564571047]

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
        c.execute("SELECT COUNT(*) FROM logs")
        total_actions = c.fetchone()[0]
        c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC LIMIT 50")
        logs = c.fetchall()

    # Read error logs
    error_lines = []
    if os.path.exists("bot_errors.log"):
        with open("bot_errors.log", "r") as f:
            error_lines = f.readlines()[-10:]

    return render_template_string("""
    <html>
    <head>
      <title>🤖 Bot Dashboard</title>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body class="bg-dark text-white">
    <div class="container py-4">

      <h2 class="mb-4">📊 Telegram Bot Dashboard</h2>

      <!-- Stats Cards -->
      <div class="row mb-4">
        <div class="col-md-3"><div class="card bg-primary text-white p-3"><h4>🕒 Uptime</h4><p id="uptime">{{ uptime }}</p></div></div>
        <div class="col-md-3"><div class="card bg-success text-white p-3"><h4>👥 Users</h4><p>{{ users }}</p></div></div>
        <div class="col-md-3"><div class="card bg-info text-white p-3"><h4>📁 Files</h4><p>{{ files }}</p></div></div>
        <div class="col-md-3"><div class="card bg-warning text-dark p-3"><h4>⚡ Actions</h4><p>{{ actions }}</p></div></div>
      </div>

      <!-- Logs -->
      <h4>📜 Recent Activity</h4>
      <table class="table table-dark table-striped">
        <tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr>
        {% for row in logs %}
          <tr><td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td></tr>
        {% endfor %}
      </table>

      <!-- Error Logs -->
      <h4 class="mt-4 text-danger">⚠️ Recent Errors</h4>
      <pre class="bg-dark text-danger p-2" style="max-height:200px; overflow:auto;">{{ errors|join('') }}</pre>
    </div>

    <script>
    // uptime auto update
    function toSeconds(str){ let p=str.split(":").map(Number); return p[0]*3600+p[1]*60+p[2]; }
    let uptimeElem=document.getElementById("uptime");
    let seconds=toSeconds(uptimeElem.innerText);
    setInterval(()=>{ seconds++; let h=String(Math.floor(seconds/3600)).padStart(2,'0');
      let m=String(Math.floor((seconds%3600)/60)).padStart(2,'0');
      let s=String(seconds%60).padStart(2,'0'); uptimeElem.innerText=`${h}:${m}:${s}`; },1000);
    </script>

    </body></html>
    """, uptime=uptime, users=total_users, files=total_files, actions=total_actions, logs=logs, errors=error_lines)

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
    if not session.get('admin'):
        return redirect('/admin')
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
    if not session.get('admin'):
        return redirect('/admin')
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
    if not session.get('admin'):
        return redirect('/admin')
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
    if not session.get('admin'):
        return redirect('/admin')
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

# ✅ ERROR HANDLER
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    with open("bot_errors.log", "a") as f:
        f.write(f"{datetime.datetime.utcnow()} - {error_text}\n\n")
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}"
        )
    except Exception as e:
        print("Failed to send error notification:", e)

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
application.add_handler(CommandHandler("setcountrycode", protected(set_country_code, "setcountrycode")))
application.add_handler(CommandHandler("setgroup", protected(set_group_number, "setgroup")))
application.add_handler(CommandHandler("makevcf", protected(make_vcf_command, "makevcf")))
application.add_handler(CommandHandler("merge", protected(merge_command, "merge")))
application.add_handler(CommandHandler("done", protected(done_merge, "done")))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT, handle_text))
application.add_error_handler(error_handler)

# ========== Run ==========
def run_flask():
    try:
        flask_app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        with open("bot_errors.log", "a") as f:
            f.write(f"{datetime.datetime.utcnow()} - Flask Error: {e}\n")
        import telegram
        bot = telegram.Bot(token=BOT_TOKEN)
        bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Flask Crash Alert ⚠️\n\n{str(e)}")

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask).start()
    application.run_polling()
