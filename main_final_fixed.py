import os
import io
import threading
import sqlite3
import datetime
import traceback
from typing import Optional, List, Tuple

from flask import (
    Flask, render_template_string, request, redirect, session, jsonify, send_file, url_for
)
from werkzeug.security import generate_password_hash, check_password_hash

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Bot, InputFile

# ====== Import your VCF/bot command logic (already provided by you) ======
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, set_country_code, set_group_number,
    make_vcf_command, merge_command, done_merge,
    handle_document, handle_text, OWNER_ID
, ALLOWED_USERS, reset_settings, my_settings)

# ================== ENV / CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # initial owner password
SECRET_KEY = os.environ.get("FLASK_SECRET", "super-secret-key")
APP_PORT = int(os.environ.get("PORT", "8080"))

DB_FILE = "bot_stats.db"
ERROR_LOG = "bot_errors.log"

# ================== DB SETUP ==================
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # activity logs
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            user_id INTEGER,
            username TEXT,
            action  TEXT,
            timestamp TEXT
        )''')
        # bot access list
        c.execute('''CREATE TABLE IF NOT EXISTS access (
            user_id   INTEGER,
            username  TEXT,
            type      TEXT,          -- permanent / temporary
            expires_at TEXT
        )''')
        # admin users (for web panel)
        c.execute('''CREATE TABLE IF NOT EXISTS admins (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL           -- owner / editor / viewer
        )''')
        # broadcast history
        c.execute('''CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin TEXT,
            kind TEXT,                   -- text/photo/document
            content TEXT,                -- text message or filename
            created_at TEXT
        )''')
        conn.commit()

        # bootstrap owner admin if table empty
        c.execute("SELECT COUNT(*) FROM admins")
        if (c.fetchone() or [0])[0] == 0:
            c.execute(
                "INSERT INTO admins (username, password_hash, role) VALUES (?, ?, ?)",
                ("owner", generate_password_hash(ADMIN_PASSWORD), "owner")
            )
            conn.commit()

def log_action(user_id: int, username: Optional[str], action: str):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
                  (user_id, username or 'N/A', action, now))
        conn.commit()

def is_authorized_in_db(user_id: int) -> bool:
    now = datetime.datetime.now()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # clear expired temporary access
        c.execute("""
            DELETE FROM access
            WHERE type='temporary'
              AND expires_at IS NOT NULL
              AND datetime(expires_at) < datetime(?)
        """, (now.strftime("%Y-%m-%d %H:%M:%S"),))
        c.execute("SELECT 1 FROM access WHERE user_id=?", (user_id,))
        row = c.fetchone()
        return bool(row)

def parse_duration(duration_str: str) -> Optional[datetime.datetime]:
    try:
        n = int(duration_str[:-1])
        unit = duration_str[-1]
        if unit == "m": return datetime.datetime.now() + datetime.timedelta(minutes=n)
        if unit == "h": return datetime.datetime.now() + datetime.timedelta(hours=n)
        if unit == "d": return datetime.datetime.now() + datetime.timedelta(days=n)
    except Exception:
        pass
    return None

# ================== TELEGRAM BOT ==================
application = Application.builder().token(BOT_TOKEN).build()
tg_bot = Bot(BOT_TOKEN)

# error handler -> file + DM owner
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.utcnow()} - {error_text}\n\n")
    except Exception:
        pass
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# Access guard for Telegram commands
ALLOWED_USERS: List[int] = []  # optional hardlist
def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_USERS or is_authorized_in_db(user_id)

def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        if not is_authorized(user.id):
            await update.message.reply_text("❌ You don't have access to use this bot.")
            return
        log_action(user.id, user.username, command_name)
        return await handler_func(update, context)
    return wrapper

# register handlers (your command functions come from NIKALLLLLLL.py)
application.add_handler(CommandHandler("start",          protected(start, "start")))
application.add_handler(CommandHandler('mysettings',          protected(my_settings, 'mysettings')))
application.add_handler(CommandHandler('reset',          protected(reset_settings, 'reset')))
application.add_handler(CommandHandler("setfilename",    protected(set_filename, "setfilename")))
application.add_handler(CommandHandler("setcontactname", protected(set_contact_name, "setcontactname")))
application.add_handler(CommandHandler("setlimit",       protected(set_limit, "setlimit")))
application.add_handler(CommandHandler("setstart",       protected(set_start, "setstart")))
application.add_handler(CommandHandler("setvcfstart",    protected(set_vcf_start, "setvcfstart")))
application.add_handler(CommandHandler("setcountrycode", protected(set_country_code, "setcountrycode")))
application.add_handler(CommandHandler("setgroup",       protected(set_group_number, "setgroup")))
application.add_handler(CommandHandler("makevcf",        protected(make_vcf_command, "makevcf")))
application.add_handler(CommandHandler("merge",          protected(merge_command, "merge")))
application.add_handler(CommandHandler("done",           protected(done_merge, "done")))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_error_handler(error_handler)
# ================== FLASK APP (ADMIN PANEL) ==================
start_time = datetime.datetime.now()
flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY

# ---- Helpers (web) ----
def admin_required(roles: Optional[List[str]] = None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not session.get("admin_user"):
                return redirect("/admin")
            if roles:
                user_role = session.get("admin_role", "viewer")
                if user_role not in roles:
                    return "🚫 Permission denied", 403
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

def chart_data_last_7_days() -> Tuple[List[str], List[int], List[int]]:
    today = datetime.datetime.now().date()
    days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
    labels = [d.strftime('%d %b') for d in days]

    daily_users = {d.strftime('%Y-%m-%d'): set() for d in days}
    daily_files = {d.strftime('%Y-%m-%d'): 0 for d in days}

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT user_id, action, date(timestamp)
            FROM logs
            WHERE date(timestamp) >= date(?)
        """, ((today - datetime.timedelta(days=6)).strftime('%Y-%m-%d'),))
        for uid, action, dt in c.fetchall():
            if dt in daily_users: daily_users[dt].add(uid)
            if dt in daily_files and action == 'makevcf': daily_files[dt] += 1

    users_counts = [len(daily_users[d.strftime('%Y-%m-%d')]) for d in days]
    files_counts = [daily_files[d.strftime('%Y-%m-%d')] for d in days]
    return labels, users_counts, files_counts

def hourly_distribution_today() -> Tuple[List[str], List[int]]:
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    buckets = {f"{h:02d}:00": 0 for h in range(24)}
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT strftime('%H:00', timestamp) AS hh, COUNT(*)
            FROM logs
            WHERE date(timestamp) = date(?)
            GROUP BY 1
        """, (today,))
        for hh, cnt in c.fetchall():
            if hh in buckets: buckets[hh] = cnt
    labels = list(buckets.keys())
    values = [buckets[k] for k in labels]
    return labels, values

# ---------- Public Dashboard ----------
@flask_app.route('/')
def dashboard():
    uptime = str(datetime.datetime.now() - start_time).split('.')[0]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
        total_users = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
        total_files = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs")
        total_actions = c.fetchone()[0] or 0
        c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC LIMIT 50")
        logs = c.fetchall()

    errors_tail = []
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, "r", encoding="utf-8", errors="ignore") as f:
                errors_tail = f.readlines()[-10:]
        except Exception:
            errors_tail = ["(unable to read error log)"]

    return render_template_string("""
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Bot Dashboard</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{background:#0b0f14;color:#e5e7eb}
.card{border:none;border-radius:1rem;box-shadow:0 10px 30px rgba(0,0,0,.25)}
.table thead th{position:sticky;top:0;background:#0f172a}
.link{color:#93c5fd}
</style>
</head>
<body>
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h3 class="fw-bold">🤖 Telegram Bot Dashboard</h3>
    <a class="btn btn-sm btn-light" href="/admin">Admin Login</a>
  </div>
  <div class="row g-3 mb-3">
    <div class="col-md-3"><div class="card p-3 bg-primary text-white"><div>👥 Users</div><div class="fs-3 fw-bold">{{users}}</div></div></div>
    <div class="col-md-3"><div class="card p-3 bg-success text-white"><div>📁 Files</div><div class="fs-3 fw-bold">{{files}}</div></div></div>
    <div class="col-md-3"><div class="card p-3 bg-info text-white"><div>⚡ Actions</div><div class="fs-3 fw-bold">{{actions}}</div></div></div>
    <div class="col-md-3"><div class="card p-3 bg-warning"><div>⏱ Uptime</div><div class="fs-3 fw-bold" id="uptime">{{uptime}}</div></div></div>
  </div>

  <div class="row g-3 mb-4">
    <div class="col-lg-6"><div class="card p-3"><h6>Daily Active Users (7d)</h6><canvas id="usersChart" height="160"></canvas></div></div>
    <div class="col-lg-6"><div class="card p-3"><h6>Files Generated per Day (7d)</h6><canvas id="filesChart" height="160"></canvas></div></div>
  </div>
  <div class="row g-3 mb-4">
    <div class="col-lg-12"><div class="card p-3"><h6>⏰ Peak Usage Today (by hour)</h6><canvas id="hourChart" height="120"></canvas></div></div>
  </div>

  <div class="row g-3">
    <div class="col-lg-8">
      <div class="card p-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h6 class="m-0">Recent Activity</h6>
          <a class="link" href="/admin">Go to Admin →</a>
        </div>
        <div style="max-height:360px;overflow:auto">
          <table class="table table-dark table-striped table-sm align-middle">
            <thead><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr></thead>
            <tbody>
              {% for row in logs %}
                <tr><td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="col-lg-4">
      <div class="card p-3"><h6>Recent Errors</h6>
        <pre style="max-height:360px;overflow:auto;background:#0f172a;color:#fca5a5">{{errors|join('')}}</pre>
      </div>
    </div>
  </div>
</div>

<script>
function toSeconds(str){let p=str.split(":").map(Number);return p[0]*3600+p[1]*60+p[2]}
let seconds = toSeconds(document.getElementById("uptime").innerText||"0:0:0");
setInterval(()=>{seconds++;let h=String(Math.floor(seconds/3600)).padStart(2,'0');let m=String(Math.floor((seconds%3600)/60)).padStart(2,'0');let s=String(seconds%60).padStart(2,'0');document.getElementById("uptime").innerText=`${h}:${m}:${s}`;},1000);
    async function refreshCharts(){
  const res = await fetch('/api/chart-data'); const data = await res.json();
  const ctxU = document.getElementById('usersChart').getContext('2d');
  const ctxF = document.getElementById('filesChart').getContext('2d');
  const ctxH = document.getElementById('hourChart').getContext('2d');
  new Chart(ctxU,{type:'line',data:{labels:data.labels,datasets:[{label:'Active Users',data:data.daily_users,tension:.3}]}, options:{scales:{y:{beginAtZero:true}}}});
  new Chart(ctxF,{type:'bar', data:{labels:data.labels,datasets:[{label:'Files',data:data.daily_files}]}, options:{scales:{y:{beginAtZero:true}}}});
  const hres = await fetch('/api/hourly-data'); const h = await hres.json();
  new Chart(ctxH,{type:'bar', data:{labels:h.labels, datasets:[{label:'Events', data:h.values}]}, options:{scales:{y:{beginAtZero:true}}}});
}
refreshCharts();
</script>
</body></html>
    """, uptime=uptime, users=total_users, files=total_files, actions=total_actions, logs=logs, errors=errors_tail)

# ---------- Chart APIs ----------
@flask_app.route('/api/chart-data')
def api_chart():
    labels, daily_users, daily_files = chart_data_last_7_days()
    return jsonify({"labels": labels, "daily_users": daily_users, "daily_files": daily_files})

@flask_app.route('/api/hourly-data')
def api_hourly():
    labels, values = hourly_distribution_today()
    return jsonify({"labels": labels, "values": values})

# ---------- Admin: Auth ----------
@flask_app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT password_hash, role FROM admins WHERE username=?", (username,))
            row = c.fetchone()
        if row and check_password_hash(row[0], password):
            session['admin_user'] = username
            session['admin_role'] = row[1]
            return redirect('/admin/dashboard')
        error = "❌ Wrong username or password"

    return render_template_string("""
    <html><head><title>Admin Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-dark text-light">
      <div class="container" style="max-width:420px">
        <div class="card mt-5 p-4 bg-secondary">
          <h4 class="mb-3">🔐 Admin Login</h4>
          {% if error %}<div class="alert alert-danger py-2">{{error}}</div>{% endif %}
          <form method="post">
            <div class="mb-2"><input class="form-control" name="username" placeholder="Username" required value="owner"></div>
            <div class="mb-3"><input class="form-control" type="password" name="password" placeholder="Password" required></div>
            <button class="btn btn-light w-100">Login</button>
          </form>
        </div>
        <div class="text-muted small mt-2">Default owner user: <b>owner</b> (password = ADMIN_PASSWORD env)</div>
      </div>
    </body></html>
    """, error=error)

@flask_app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin')

@flask_app.route('/admin/dashboard')
@admin_required()
def admin_dashboard():
    return render_template_string("""
    <html><head><title>Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-dark text-light">
    <div class="container py-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h4 class="m-0">📊 Admin Dashboard</h4>
        <div>
          <a class="btn btn-sm btn-outline-light" href="/">Public</a>
          <a class="btn btn-sm btn-warning" href="/admin/logout">Logout</a>
        </div>
      </div>
      <div class="row g-2">
        <div class="col-md-4"><a class="btn btn-primary w-100" href="/admin/live-logs">📺 Live Logs</a></div>
        <div class="col-md-4"><a class="btn btn-primary w-100" href="/admin/logs">🔎 Logs (Filter)</a></div>
        <div class="col-md-4"><a class="btn btn-primary w-100" href="/admin/access">🔐 Access Control</a></div>
        <div class="col-md-4"><a class="btn btn-success w-100" href="/admin/broadcast">📢 Broadcast</a></div>
        <div class="col-md-4"><a class="btn btn-info w-100" href="/admin/errors">⚠️ Errors</a></div>
        <div class="col-md-4"><a class="btn btn-secondary w-100" href="/admin/admins">👤 Admins</a></div>
      </div>
    </div></body></html>
    """)

# ---------- Admin: Live Logs ----------
@flask_app.route('/admin/live-logs')
@admin_required()
def live_logs():
    return render_template_string("""
    <html><head><title>Live Logs</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-dark text-light">
    <div class="container py-3">
      <h5>📺 Live Logs</h5>
      <div id="logbox" class="table-responsive"></div>
    </div>
    <script>
      async function refresh(){
        const res = await fetch('/admin/log-feed'); const data = await res.json();
        document.getElementById('logbox').innerHTML = `
          <table class="table table-dark table-striped table-sm">
            <thead><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr></thead>
            <tbody>${data.map((r,i)=>`<tr><td>${i+1}</td><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td></tr>`).join('')}</tbody>
          </table>`;
      }
      refresh(); setInterval(refresh, 3000);
    </script>
    </body></html>
    """)

@flask_app.route('/admin/log-feed')
@admin_required()
def log_feed():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC LIMIT 100")
        return jsonify(c.fetchall())

# ---------- Admin: Logs with Filters ----------
@flask_app.route('/admin/logs')
@admin_required()
def logs_filter():
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    user_q = request.args.get('user')
    action_q = request.args.get('action')

    query = "SELECT username, user_id, action, timestamp FROM logs WHERE 1=1"
    params: List[str] = []
    if date_from:
        query += " AND date(timestamp) >= date(?)"; params.append(date_from)
    if date_to:
        query += " AND date(timestamp) <= date(?)"; params.append(date_to)
    if user_q:
        query += " AND (username LIKE ? OR user_id=?)"; params.extend([f"%{user_q}%", user_q if user_q.isdigit() else -1])
    if action_q:
        query += " AND action LIKE ?"; params.append(f"%{action_q}%")
    query += " ORDER BY timestamp DESC LIMIT 500"

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(query, tuple(params))
        rows = c.fetchall()
        return render_template_string("""
    <html><head><title>Logs</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-dark text-light">
    <div class="container py-3">
      <h5>🔎 Logs (Filter)</h5>
      <form class="row g-2 mb-3">
        <div class="col-md-2"><input class="form-control" type="date" name="from" value="{{request.args.get('from','')}}"></div>
        <div class="col-md-2"><input class="form-control" type="date" name="to" value="{{request.args.get('to','')}}"></div>
        <div class="col-md-3"><input class="form-control" name="user" placeholder="username or user_id" value="{{request.args.get('user','')}}"></div>
        <div class="col-md-3"><input class="form-control" name="action" placeholder="action" value="{{request.args.get('action','')}}"></div>
        <div class="col-md-2 d-grid"><button class="btn btn-primary">Search</button></div>
      </form>
      <div class="table-responsive">
        <table class="table table-dark table-striped table-sm">
          <thead><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr></thead>
          <tbody>
            {% for r in rows %}
              <tr><td>{{loop.index}}</td><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3]}}</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      <a class="btn btn-outline-danger" href="/admin/clear-logs" onclick="return confirm('Delete ALL logs?')">🗑 Clear All Logs</a>
    </div></body></html>
    """, rows=rows)

@flask_app.route('/admin/clear-logs')
@admin_required(roles=["owner"])
def clear_logs():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM logs")
        conn.commit()
    return redirect('/admin/logs')

# ---------- Admin: Access Control ----------
@flask_app.route('/admin/access', methods=['GET', 'POST'])
@admin_required(roles=["owner","editor"])
def access_panel():
    msg = ""
    if request.method == 'POST':
        uid = int(request.form['user_id'])
        uname = request.form['username']
        atype = request.form['type']
        expires_at = None
        if atype == 'temporary':
            exp = parse_duration(request.form.get('duration', ''))
            if exp: expires_at = exp.strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO access (user_id, username, type, expires_at) VALUES (?, ?, ?, ?)",
                      (uid, uname, atype, expires_at))
            conn.commit()
        # Notify user on Telegram
        try:
            tg_bot.send_message(chat_id=uid, text=f"✅ You have been granted *{atype}* access to the bot.", parse_mode="Markdown")
        except Exception:
            pass
        msg = "✅ Access granted!"
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            DELETE FROM access
            WHERE type='temporary' AND expires_at IS NOT NULL AND datetime(expires_at) < datetime(?)
        """, (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
        c.execute("SELECT * FROM access ORDER BY type DESC, user_id ASC")
        rows = c.fetchall()
    return render_template_string("""
    <html><head><title>Access Control</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-dark text-light">
    <div class="container py-3">
      <h5>🔐 Manage Access</h5>
      {% if msg %}<div class="alert alert-success py-2">{{msg}}</div>{% endif %}
      <form method="post" class="row g-2 mb-3">
        <div class="col-md-2"><input class="form-control" name="user_id" placeholder="User ID" required></div>
        <div class="col-md-3"><input class="form-control" name="username" placeholder="Username"></div>
        <div class="col-md-3">
          <select class="form-select" name="type">
            <option value="permanent">Permanent</option>
            <option value="temporary">Temporary</option>
          </select>
        </div>
        <div class="col-md-2"><input class="form-control" name="duration" placeholder="e.g. 2h or 3d"></div>
        <div class="col-md-2 d-grid"><button class="btn btn-primary">Add / Update</button></div>
      </form>
      <div class="table-responsive">
        <table class="table table-dark table-striped table-sm">
          <thead><tr><th>User ID</th><th>Username</th><th>Type</th><th>Expires</th><th>Delete</th></tr></thead>
          <tbody>
            {% for r in rows %}
              <tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3] or '∞'}}</td>
              <td><a class="btn btn-sm btn-danger" href="/admin/delaccess?uid={{r[0]}}">❌</a></td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div></body></html>
    """, rows=rows, msg=msg)

@flask_app.route('/admin/delaccess')
@admin_required(roles=["owner","editor"])
def del_access():
    uid = request.args.get('uid')
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM access WHERE user_id=?", (uid,))
        conn.commit()
    return redirect('/admin/access')

# ---------- Admin: Broadcast ----------
@flask_app.route('/admin/broadcast', methods=['GET', 'POST'])
@admin_required(roles=["owner","editor"])
def broadcast():
    note = None
    if request.method == 'POST':
        kind = request.form.get('kind', 'text')
        text = request.form.get('text', '')
        file = request.files.get('file')
        sent = 0

        # audience = distinct user_ids who used the bot or have access
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT DISTINCT user_id FROM logs")
            ids1 = {r[0] for r in c.fetchall()}
            c.execute("SELECT DISTINCT user_id FROM access")
            ids2 = {r[0] for r in c.fetchall()}
        audience = sorted(list(ids1.union(ids2)))

        for uid in audience:
            try:
                if kind == 'text':
                    tg_bot.send_message(chat_id=uid, text=text)
                elif kind == 'photo' and file:
                    file.stream.seek(0)
                    tg_bot.send_photo(chat_id=uid, photo=InputFile(file.stream, filename=file.filename), caption=text or None)
                elif kind == 'document' and file:
                    file.stream.seek(0)
                    tg_bot.send_document(chat_id=uid, document=InputFile(file.stream, filename=file.filename), caption=text or None)
                sent += 1
            except Exception:
                # ignore user blocks/errors
                pass

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO broadcasts (admin, kind, content, created_at) VALUES (?, ?, ?, ?)",
                      (session.get("admin_user"), kind, text if kind=='text' else (file.filename if file else ''),
                       datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
        note = f"✅ Broadcast queued to {len(audience)} users. Sent attempts: {sent}"
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, admin, kind, content, created_at FROM broadcasts ORDER BY id DESC LIMIT 50")
        hist = c.fetchall()

    return render_template_string("""
    <html><head><title>Broadcast</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-dark text-light">
    <div class="container py-3">
      <h5>📢 Broadcast</h5>
      {% if note %}<div class="alert alert-success py-2">{{note}}</div>{% endif %}
      <form method="post" enctype="multipart/form-data" class="row g-2 mb-3">
        <div class="col-md-2">
          <select class="form-select" name="kind">
            <option value="text">Text</option>
            <option value="photo">Photo</option>
            <option value="document">Document</option>
          </select>
        </div>
        <div class="col-md-6"><input class="form-control" name="text" placeholder="Message (optional for photo/document)"></div>
        <div class="col-md-3"><input class="form-control" type="file" name="file"></div>
        <div class="col-md-1 d-grid"><button class="btn btn-success">Send</button></div>
      </form>
      <h6>History</h6>
      <div class="table-responsive"><table class="table table-dark table-striped table-sm">
        <thead><tr><th>ID</th><th>Admin</th><th>Kind</th><th>Content</th><th>Time</th></tr></thead>
        <tbody>
          {% for r in hist %}<tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3][:60]}}</td><td>{{r[4]}}</td></tr>{% endfor %}
        </tbody></table></div>
    </div></body></html>
    """, note=note, hist=hist)

# ---------- Admin: Errors ----------
@flask_app.route('/admin/errors')
@admin_required()
def errors_page():
    lines = []
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-500:]
        except Exception as e:
            lines = [f"(error reading log: {e})"]
    return render_template_string("""
    <html><head><title>Errors</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-dark text-light">
    <div class="container py-3">
      <h5>⚠️ Errors</h5>
      <div class="mb-2">
        <a class="btn btn-sm btn-outline-danger" href="/admin/errors/clear" onclick="return confirm('Clear error log?')">Clear Errors</a>
        <a class="btn btn-sm btn-outline-light" href="/admin/errors/download">Download</a>
      </div>
      <pre style="max-height:70vh;overflow:auto;background:#0f172a;color:#fca5a5">{{lines|join('')}}</pre>
    </div></body></html>
    """, lines=lines)

@flask_app.route('/admin/errors/clear')
@admin_required(roles=["owner","editor"])
def errors_clear():
    if os.path.exists(ERROR_LOG):
        try:
            open(ERROR_LOG, "w").close()
        except Exception:
            pass
    return redirect('/admin/errors')

@flask_app.route('/admin/errors/download')
@admin_required()
def errors_download():
    data = ""
    if os.path.exists(ERROR_LOG):
        with open(ERROR_LOG, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
    return send_file(io.BytesIO(data.encode('utf-8')), as_attachment=True, download_name="bot_errors.log", mimetype="text/plain")

# ---------- Admin: Admins Management (multi-admin) ----------
@flask_app.route('/admin/admins', methods=['GET', 'POST'])
@admin_required(roles=["owner"])
def admins_panel():
    note = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            uname = request.form.get('username').strip()
            pwd = request.form.get('password')
            role = request.form.get('role', 'editor')
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO admins (username, password_hash, role) VALUES (?, ?, ?)",
                              (uname, generate_password_hash(pwd), role))
                    conn.commit()
                    note = "✅ Admin added"
                except sqlite3.IntegrityError:
                    note = "❌ Username already exists"
        elif action == 'del':
            uname = request.form.get('username')
            if uname == 'owner':
                note = "❌ Cannot delete default owner"
            else:
                with sqlite3.connect(DB_FILE) as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM admins WHERE username=?", (uname,))
                    conn.commit()
                    note = "✅ Admin removed"
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT username, role FROM admins ORDER BY role DESC, username ASC")
        rows = c.fetchall()
    return render_template_string("""
    <html><head><title>Admins</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-dark text-light">
    <div class="container py-3">
      <h5>👤 Admins (Owner only)</h5>
      {% if note %}<div class="alert alert-info py-2">{{note}}</div>{% endif %}
      <form method="post" class="row g-2 mb-3">
        <input type="hidden" name="action" value="add">
        <div class="col-md-3"><input class="form-control" name="username" placeholder="username" required></div>
        <div class="col-md-3"><input class="form-control" name="password" type="password" placeholder="password" required></div>
        <div class="col-md-3">
          <select class="form-select" name="role">
            <option value="editor">editor</option>
            <option value="viewer">viewer</option>
            <option value="owner">owner</option>
          </select>
        </div>
        <div class="col-md-3 d-grid"><button class="btn btn.success">Add Admin</button></div>
      </form>
      <div class="table-responsive">
        <table class="table table-dark table-striped table-sm">
          <thead><tr><th>Username</th><th>Role</th><th>Delete</th></tr></thead>
          <tbody>
            {% for r in rows %}
              <tr><td>{{r[0]}}</td><td>{{r[1]}}</td>
              <td>
                <form method="post" style="display:inline" onsubmit="return confirm('Delete admin {{r[0]}}?')">
                  <input type="hidden" name="action" value="del">
                  <input type="hidden" name="username" value="{{r[0]}}">
                  <button class="btn btn-sm btn-danger" {% if r[0]=='owner' %}disabled{% endif %}>❌</button>
                </form>
              </td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div></body></html>
    """, rows=rows, note=note)

# ---------- Flask APIs used above ----------
@flask_app.route('/api/errors-tail')
def api_errors_tail():
    lines = []
    try:
        if os.path.exists(ERROR_LOG):
            with open(ERROR_LOG, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-12:]
    except Exception as e:
        lines = [f"(error reading log: {e})"]
    return jsonify(lines)

# ================== RUN ==================
def run_flask():
    try:
        flask_app.run(host='0.0.0.0', port=APP_PORT)
    except Exception as e:
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.utcnow()} - Flask Error: {e}\n")
        except Exception:
            pass
        try:
            tg_bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Flask Crash Alert ⚠️\n\n{str(e)}")
        except Exception:
            pass

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    application.run_polling()
