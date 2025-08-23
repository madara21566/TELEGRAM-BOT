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

# ================== ENV / CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("FLASK_SECRET", "secretkey123")

# Allow list (plus DB-based access)
ALLOWED_USERS = [8047407478,7043391463,7440046924,7118726445,7492026653,5989680310,7440046924,7669357884,7640327597,5849097477,8128934569,7950732287,5989680310,7983528757,5564571047]

# ================== ACCESS HELPERS ==================
def is_authorized(user_id):
    return user_id in ALLOWED_USERS or is_authorized_in_db(user_id)

DB_FILE = "bot_stats.db"

def is_authorized_in_db(user_id):
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

def parse_duration(duration_str):
    n = int(duration_str[:-1])
    unit = duration_str[-1]
    if unit == "m": return datetime.datetime.now() + datetime.timedelta(minutes=n)
    if unit == "h": return datetime.datetime.now() + datetime.timedelta(hours=n)
    if unit == "d": return datetime.datetime.now() + datetime.timedelta(days=n)
    return None

# ================== DB SETUP / LOGGING ==================
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            user_id INTEGER,
            username TEXT,
            action  TEXT,
            timestamp TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS access (
            user_id   INTEGER,
            username  TEXT,
            type      TEXT,
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

# ================== FLASK APP ==================
start_time = datetime.datetime.now()
flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY

# ---------- Advanced Dashboard (Home) ----------
@flask_app.route('/')
def dashboard():
    # Top stats
    uptime = str(datetime.datetime.now() - start_time).split('.')[0]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
        total_users = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
        total_files = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs")
        total_actions = c.fetchone()[0] or 0
        c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC LIMIT 100")
        logs = c.fetchall()

    # Error tail
    errors = []
    if os.path.exists("bot_errors.log"):
        try:
            with open("bot_errors.log", "r", encoding="utf-8", errors="ignore") as f:
                errors = f.readlines()[-12:]
        except Exception:
            errors = ["(unable to read bot_errors.log)"]

    # HTML (Bootstrap 5 + Chart.js + Live API)
    return render_template_string("""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>🤖 Bot Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- Bootstrap + Icons + Chart.js -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body{ background:#0b0f14; color:#e5e7eb; }
    .card{ border:none; border-radius:1rem; box-shadow:0 10px 30px rgba(0,0,0,.25); }
    .card h4{ margin:0; font-weight:600; }
    .stat-num{ font-size:1.8rem; font-weight:700; }
    .table thead th{ position:sticky; top:0; background:#0f172a; }
    .badge-dot{ width:10px; height:10px; border-radius:50%; display:inline-block; }
    .bg-soft{ background:rgba(255,255,255,.05); }
    .link { color:#93c5fd; text-decoration:none; }
    .link:hover { text-decoration:underline; }
    .chip { background:rgba(255,255,255,.08); border-radius:999px; padding:.25rem .6rem; }
    .footer { opacity:.7; font-size:.9rem; }
  </style>
</head>
<body>
<div class="container py-4">

  <div class="d-flex align-items-center justify-content-between mb-4">
    <h2 class="fw-bold">📊 Telegram Bot Dashboard</h2>
    <div><span class="chip">Uptime: <b id="uptime">{{ uptime }}</b></span></div>
  </div>

  <!-- Stats -->
  <div class="row g-3 mb-4">
    <div class="col-12 col-md-3">
      <div class="card bg-primary text-white p-3">
        <div class="d-flex justify-content-between align-items-center">
          <h4>👥 Users</h4><span class="badge-dot bg-light"></span>
        </div>
        <div class="stat-num mt-2">{{ users }}</div>
        <div class="small opacity-75">Unique users ever</div>
      </div>
    </div>
    <div class="col-12 col-md-3">
      <div class="card bg-success text-white p-3">
        <div class="d-flex justify-content-between align-items-center">
          <h4>📁 Files</h4><span class="badge-dot bg-light"></span>
        </div>
        <div class="stat-num mt-2">{{ files }}</div>
        <div class="small opacity-75">VCF generated</div>
      </div>
    </div>
    <div class="col-12 col-md-3">
      <div class="card bg-info text-white p-3">
        <div class="d-flex justify-content-between align-items-center">
          <h4>⚡ Actions</h4><span class="badge-dot bg-light"></span>
        </div>
        <div class="stat-num mt-2">{{ actions }}</div>
        <div class="small opacity-75">All commands</div>
      </div>
    </div>
    <div class="col-12 col-md-3">
      <div class="card bg-warning text-dark p-3">
        <div class="d-flex justify-content-between align-items-center">
          <h4>🛡 Status</h4><span class="badge-dot bg-dark"></span>
        </div>
        <div id="statusBadge" class="stat-num mt-2">OK</div>
        <div class="small">Errors monitor</div>
      </div>
    </div>
  </div>

  <!-- Charts -->
  <div class="row g-3 mb-4">
    <div class="col-12 col-lg-6">
      <div class="card p-3 bg-soft">
        <h5 class="fw-semibold mb-3">Daily Active Users (7d)</h5>
        <canvas id="usersChart" height="150"></canvas>
      </div>
    </div>
    <div class="col-12 col-lg-6">
      <div class="card p-3 bg-soft">
        <h5 class="fw-semibold mb-3">Files Generated per Day (7d)</h5>
        <canvas id="filesChart" height="150"></canvas>
      </div>
    </div>
  </div>

  <!-- Logs + Errors -->
  <div class="row g-3">
    <div class="col-12 col-lg-8">
      <div class="card p-3 bg-soft">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h5 class="fw-semibold m-0">Recent Activity</h5>
          <a class="link" href="/admin">Admin Panel →</a>
        </div>
        <div style="max-height:360px; overflow:auto;">
          <table class="table table-dark table-striped table-sm align-middle">
            <thead><tr><th>#</th><th>User</th><th>ID</th><th>Action</th><th>Time</th></tr></thead>
            <tbody id="logTable">
              {% for row in logs %}
                <tr>
                  <td>{{ loop.index }}</td>
                  <td>{{ row[0] }}</td>
                  <td>{{ row[1] }}</td>
                  <td>{{ row[2] }}</td>
                  <td>{{ row[3] }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="col-12 col-lg-4">
      <div class="card p-3 bg-soft">
        <h5 class="fw-semibold">Recent Errors</h5>
        <pre id="errorBox" class="p-2" style="max-height:360px; overflow:auto; background:#0f172a; color:#fca5a5;">{{ errors|join('') }}</pre>
      </div>
    </div>
  </div>

  <div class="mt-4 footer">Made with ❤️ | Live updates every few seconds</div>
</div>

<script>
  // Uptime auto-increment
  function toSeconds(str){ let p=str.split(":").map(Number); return p[0]*3600+p[1]*60+p[2]; }
  let uptimeElem=document.getElementById("uptime");
  let seconds=toSeconds(uptimeElem.innerText||"0:0:0");
  setInterval(()=>{ seconds++; let h=String(Math.floor(seconds/3600)).padStart(2,'0');
    let m=String(Math.floor((seconds%3600)/60)).padStart(2,'0');
    let s=String(seconds%60).padStart(2,'0'); uptimeElem.innerText=`${h}:${m}:${s}`; },1000);

  // Charts (fetch from API)
  let usersChart, filesChart;
  function renderCharts(payload){
    const labels = payload.labels;
    const ctxU = document.getElementById('usersChart').getContext('2d');
    const ctxF = document.getElementById('filesChart').getContext('2d');
    if(usersChart) usersChart.destroy();
    if(filesChart) filesChart.destroy();
    usersChart = new Chart(ctxU, {
      type:'line',
      data:{ labels, datasets:[{ label:'Active Users', data:payload.daily_users, tension:.3 }] },
      options:{ plugins:{ legend:{ display:true } }, scales:{ y:{ beginAtZero:true } } }
    });
    filesChart = new Chart(ctxF, {
      type:'bar',
      data:{ labels, datasets:[{ label:'Files (makevcf)', data:payload.daily_files }] },
      options:{ plugins:{ legend:{ display:true } }, scales:{ y:{ beginAtZero:true } } }
    });
  }

  async function refreshCharts(){
    const res = await fetch('/api/chart-data');
    const data = await res.json();
    renderCharts(data);
  }

  async function refreshLogs(){
    const res = await fetch('/admin/log-feed');
    const rows = await res.json();
    const body = document.getElementById('logTable');
    body.innerHTML = rows.map((r,i)=>(
      `<tr><td>${i+1}</td><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td></tr>`
    )).join('');
  }

  async function refreshErrors(){
    const res = await fetch('/api/errors-tail');
    const data = await res.json();
    const box = document.getElementById('errorBox');
    box.textContent = data.join('');
    document.getElementById('statusBadge').innerText = data.length ? 'ISSUES' : 'OK';
  }

  refreshCharts(); refreshLogs(); refreshErrors();
  setInterval(refreshCharts, 15000);
  setInterval(refreshLogs,   5000);
  setInterval(refreshErrors, 5000);
</script>
</body>
</html>
    """, uptime=uptime, users=total_users, files=total_files, actions=total_actions, logs=logs, errors=errors)

# ---------- Chart/Errors APIs ----------
@flask_app.route('/api/chart-data')
def api_chart_data():
    """Return last 7 days labels + daily active users + daily makevcf counts."""
    today = datetime.datetime.now().date()
    days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
    labels = [d.strftime('%d %b') for d in days]

    # Pre-fill dicts
    daily_users = {d.strftime('%Y-%m-%d'): set() for d in days}
    daily_files = {d.strftime('%Y-%m-%d'): 0 for d in days}

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # Pull last 7 days logs
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

    return jsonify({
        "labels": labels,
        "daily_users": users_counts,
        "daily_files": files_counts
    })

@flask_app.route('/api/errors-tail')
def api_errors_tail():
    lines = []
    try:
        if os.path.exists("bot_errors.log"):
            with open("bot_errors.log", "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-12:]
    except Exception as e:
        lines = [f"(error reading log: {e})"]
    return jsonify(lines)

# ---------- Admin (same as before, with access mgmt + live logs) ----------
@flask_app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin/dashboard')
        return "❌ Wrong password"
    return '''
    <form method=post style="font-family:system-ui">
      <h3>🔐 Admin Login</h3>
      Password: <input type=password name=password autofocus>
      <input type=submit value=Login>
    </form>'''

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
    msg = ""
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
        msg = "✅ Access granted!"
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            DELETE FROM access
            WHERE type='temporary' AND expires_at IS NOT NULL AND datetime(expires_at) < datetime(?)
        """, (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
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
    """, rows=rows, msg=msg)

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

# ================== TELEGRAM BOT ==================
application = Application.builder().token(BOT_TOKEN).build()

# Bot-side error -> DM Owner + log file
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    try:
        with open("bot_errors.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.utcnow()} - {error_text}\n\n")
    except Exception:
        pass
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        if not is_authorized(user.id):
            await update.message.reply_text("❌ You don't have access to use this bot.")
            return
        log_action(user.id, user.username, command_name)
        return await handler_func(update, context)
    return wrapper

# Handlers
application.add_handler(CommandHandler("start",          protected(start, "start")))
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

# ================== RUN ==================
def run_flask():
    try:
        flask_app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        # Flask crash -> DM Owner + log
        try:
            with open("bot_errors.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.utcnow()} - Flask Error: {e}\n")
        except Exception:
            pass
        try:
            import telegram
            telegram.Bot(token=BOT_TOKEN).send_message(chat_id=OWNER_ID, text=f"⚠️ Flask Crash Alert ⚠️\n\n{str(e)}")
        except Exception:
            pass
        if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    application.run_polling()
