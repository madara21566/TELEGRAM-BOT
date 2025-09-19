import os
import io
import sys
import time
import threading
import traceback
import sqlite3
import datetime
from typing import Optional, List, Tuple

# ------------- Replace with your actual bot logic module (must be present) -------------
import NIKALLLLLLL

from flask import Flask, render_template_string, request, jsonify, send_file
from telegram import Bot, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============ UPTIME (single source) ============
START_TIME = datetime.datetime.now()

def format_uptime():
    delta = datetime.datetime.now() - START_TIME
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
    else:
        return f"{hours:02}:{minutes:02}:{seconds:02}"

def uptime_seconds():
    return int((datetime.datetime.now() - START_TIME).total_seconds())

# ============ ENV / CONFIG ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
APP_PORT = int(os.environ.get("PORT", "8080"))
DB_FILE = os.environ.get("DB_FILE", "bot_stats.db")
ERROR_LOG = os.environ.get("ERROR_LOG", "bot_errors.log")

# ============ DB (minimal) ============
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            timestamp TEXT
        )''')
        conn.commit()

def log_action(user_id: int, username: Optional[str], action: str):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
                      (user_id, username or 'N/A', action, now))
            conn.commit()
    except Exception:
        # swallowing DB errors to not crash bot
        pass

# ============ Import handlers from NIKALLLLLLL (user's bot logic) ============
# Ensure NIKALLLLLLL provides the functions and constants below
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, set_country_code, set_group_number,
    make_vcf_command, merge_command, done_merge,
    handle_document, handle_text, OWNER_ID, ALLOWED_USERS, reset_settings, my_settings,txt2vcf, vcf2txt
)

# ============ TELEGRAM BOT SETUP ============
if not BOT_TOKEN:
    print("WARNING: BOT_TOKEN not set. Telegram bot will not start. Set BOT_TOKEN env to run bot.")
application = Application.builder().token(BOT_TOKEN).build() if BOT_TOKEN else None
tg_bot = Bot(BOT_TOKEN) if BOT_TOKEN else None

# error handler -> file + DM owner (if OWNER_ID set)
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error_text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.utcnow()} - {error_text}\n\n")
    except Exception:
        pass
    try:
        if OWNER_ID:
            await context.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot Error Alert ⚠️\n\n{error_text[:4000]}")
    except Exception:
        pass

# Access guard (keeps original behavior)
def is_authorized_in_db(user_id: int) -> bool:
    now = datetime.datetime.now()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                DELETE FROM logs WHERE 1=0
            """)  # no-op but keeps pattern similar if you later add access table
    except Exception:
        pass
    # we keep simple ALLOWED_USERS logic from NIKALLLLLLL module
    return user_id in getattr(NIKALLLLLLL, "ALLOWED_USERS", [])  # fallback

def is_authorized(user_id: int) -> bool:
    # original allowed users (module) OR local DB-based check
    return (user_id in getattr(NIKALLLLLLL, "ALLOWED_USERS", [])) or is_authorized_in_db(user_id)

def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        try:
            if not is_authorized(user.id):
                await update.message.reply_text("❌ You don't have access to use this bot.")
                return
            log_action(user.id, user.username, command_name)
            return await handler_func(update, context)
        except Exception as e:
            # fallback: try calling handler anyway
            try:
                return await handler_func(update, context)
            except Exception:
                # bubble up to application handler
                raise
    return wrapper

# Register handlers only if application available
if application:
    application.add_handler(CommandHandler("start",          protected(start, "start")))
    application.add_handler(CommandHandler('mysettings',     protected(my_settings, 'mysettings')))
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
    application.add_handler(CommandHandler("txt2vcf",        protected(txt2vcf, "txt2vcf")))
    application.add_handler(CommandHandler("vcf2txt",        protected(vcf2txt, "vcf2txt")))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)

# ============ FLASK DASHBOARD (anime-style GOD MADARA BOT) ============
flask_app = Flask(__name__)
flask_app.secret_key = os.environ.get("FLASK_SECRET", "super-secret-key")

# Helper charts data (derived from logs)
def chart_data_last_7_days() -> Tuple[List[str], List[int], List[int]]:
    today = datetime.datetime.now().date()
    days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
    labels = [d.strftime('%d %b') for d in days]

    daily_users = {d.strftime('%Y-%m-%d'): set() for d in days}
    daily_files = {d.strftime('%Y-%m-%d'): 0 for d in days}

    try:
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
    except Exception:
        pass

    users_counts = [len(daily_users[d.strftime('%Y-%m-%d')]) for d in days]
    files_counts = [daily_files[d.strftime('%Y-%m-%d')] for d in days]
    return labels, users_counts, files_counts

def hourly_distribution_today() -> Tuple[List[str], List[int]]:
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    buckets = {f"{h:02d}:00": 0 for h in range(24)}
    try:
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
    except Exception:
        pass
    labels = list(buckets.keys())
    values = [buckets[k] for k in labels]
    return labels, values

# Public Dashboard route
@flask_app.route('/')
def dashboard():
    uptime = format_uptime()
    total_users = total_files = total_actions = 0
    logs = []
    try:
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
    except Exception:
        logs = []

    errors_tail = []
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, "r", encoding="utf-8", errors="ignore") as f:
                errors_tail = f.readlines()[-10:]
        except Exception:
            errors_tail = ["(unable to read error log)"]

    # Anime-style dashboard HTML (GOD MADARA BOT)
    return render_template_string("""
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>GOD MADARA BOT — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{--bg:#05060a;--accent1:#ff4fd8;--accent2:#6b21ff;--muted:#9aa4b2}
*{box-sizing:border-box}body{margin:0;font-family:Inter,Arial;background:
 radial-gradient(circle at 10% 10%, rgba(124,58,237,0.06), transparent 6%),
 radial-gradient(circle at 90% 90%, rgba(6,182,212,0.04), transparent 8%), #0a0c14;color:#e6eef6}
.header{display:flex;align-items:center;gap:12px;padding:18px 22px}
.logo{width:64px;height:64px;border-radius:12px;background:linear-gradient(135deg,var(--accent1),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:900;font-size:20px;box-shadow:0 10px 40px rgba(107,33,255,0.12)}
.title{font-size:20px;font-weight:800;color:var(--accent1);text-shadow:0 4px 20px rgba(124,58,237,0.08)}
.subtitle{color:var(--muted);font-size:12px}
.controls{margin-left:auto;display:flex;gap:8px}
.btn{padding:8px 12px;border-radius:10px;border:none;background:linear-gradient(90deg,var(--accent1),var(--accent2));color:white;cursor:pointer;font-weight:700}
.container{max-width:1100px;margin:18px auto;padding:0 16px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px}
.card{background:linear-gradient(180deg,rgba(255,255,255,0.02),transparent);padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,0.03)}
.stat{grid-column:span 3;display:flex;flex-direction:column;gap:6px}
.stat .num{font-size:20px;font-weight:800}
@media (max-width:900px){.stat{grid-column:span 6}.chart{grid-column:span 12}.side{grid-column:span 12}}
.chart{grid-column:span 8}
.side{grid-column:span 4}
.logs pre{max-height:320px;overflow:auto;background:#041025;padding:12px;border-radius:8px;color:#bfe7ff}
.uptime{font-family:monospace;font-weight:700}
.muted{color:var(--muted);font-size:12px}
</style>
</head><body>
  <div class="header">
    <div class="logo">G</div>
    <div>
      <div class="title">GOD MADARA BOT</div>
      <div class="subtitle">Anime-style monitoring · Always-on uptime</div>
    </div>
    <div class="controls">
      <button class="btn" id="download-logs">Download Errors</button>
      <button class="btn" id="restart-btn">Restart Bot</button>
    </div>
  </div>

  <div class="container">
    <div class="grid">
      <div class="card stat"><div class="muted">👥 Users</div><div id="stat-users" class="num">0</div><div class="muted">Unique</div></div>
      <div class="card stat"><div class="muted">📁 Files</div><div id="stat-files" class="num">0</div><div class="muted">VCF generated</div></div>
      <div class="card stat"><div class="muted">⚡ Actions</div><div id="stat-actions" class="num">0</div><div class="muted">Commands</div></div>
      <div class="card stat"><div class="muted">⏱ Uptime</div><div id="stat-uptime" class="num uptime">--:--:--</div><div class="muted">Backend</div></div>

      <div class="card chart"><strong>Activity (last 7 days)</strong><canvas id="chartMain" height="120" style="margin-top:12px"></canvas></div>
      <div class="card side"><strong>Peak Hours Today</strong><canvas id="chartHours" height="160" style="margin-top:12px"></canvas><div style="height:12px"></div><div id="sysinfo" class="muted">System: -</div></div>

      <div class="card" style="grid-column:span 8"><strong>Recent Activity</strong><div class="logs"><pre id="recent-logs">{{logs_text}}</pre></div></div>
      <div class="card" style="grid-column:span 4"><strong>Recent Errors</strong><pre id="recent-errors">{{errors_text}}</pre></div>
    </div>
  </div>

<script>
let uptime_sec = {{uptime_seconds}};
function pad(n){return String(n).padStart(2,'0')}
function secToHMS(s){const d=Math.floor(s/86400);s%=86400;const h=Math.floor(s/3600);const m=Math.floor((s%3600)/60);const ss=s%60;return (d?d+'d ':'')+pad(h)+':'+pad(m)+':'+pad(ss)}
setInterval(()=>{uptime_sec++;document.getElementById('stat-uptime').innerText = secToHMS(uptime_sec)},1000);

async function fetchStats(){
  try{
    const res = await fetch('/api/stats'); const data = await res.json();
    document.getElementById('stat-users').innerText = data.users;
    document.getElementById('stat-files').innerText = data.files;
    document.getElementById('stat-actions').innerText = data.actions;
    uptime_sec = data.uptime_seconds || uptime_sec;
    document.getElementById('stat-uptime').innerText = data.uptime_str || secToHMS(uptime_sec);
    document.getElementById('sysinfo').innerText = (data.system.cpu||'-') + "% CPU / " + (data.system.ram||'-') + "% RAM / " + (data.system.disk||'-');
  }catch(e){console.error(e)}
}

async function fetchCharts(){
  try{ const r=await fetch('/api/chart-data'); const d=await r.json(); updateMainChart(d.labels,d.daily_users,d.daily_files);}catch(e){console.error(e)}
}
async function fetchHourly(){ try{ const r=await fetch('/api/hourly-data'); const d=await r.json(); updateHourChart(d.labels,d.values);}catch(e){console.error(e)} }
async function fetchLogsAndErrors(){
  try{ const r=await fetch('/api/logs?limit=200'); const rows = await r.json(); document.getElementById('recent-logs').innerText = rows.map(r=>`${r[4]} | ${r[1]}(${r[2]}) -> ${r[3]}`).join('\\n'); }catch(e){}
  try{ const r2=await fetch('/api/errors-tail'); const errs = await r2.json(); document.getElementById('recent-errors').innerText = errs.join('') }catch(e){}
}

setInterval(()=>{ fetchStats(); fetchCharts(); fetchHourly(); fetchLogsAndErrors(); }, 5000);
fetchStats(); fetchCharts(); fetchHourly(); fetchLogsAndErrors();

/* Charts */
const ctx = document.getElementById('chartMain').getContext('2d');
const mainChart = new Chart(ctx,{type:'line',data:{labels:[],datasets:[{label:'Users',data:[],borderColor:'#ff4fd8'},{label:'Files',data:[],borderColor:'#38bdf8'}]},options:{scales:{y:{beginAtZero:true}}}});
function updateMainChart(labels, users, files){ mainChart.data.labels = labels; mainChart.data.datasets[0].data = users; mainChart.data.datasets[1].data = files; mainChart.update(); }
const ctx2 = document.getElementById('chartHours').getContext('2d');
const hourChart = new Chart(ctx2,{type:'bar',data:{labels:[],datasets:[{label:'Events',data:[]}]}});
function updateHourChart(labels, vals){ hourChart.data.labels = labels; hourChart.data.datasets[0].data = vals; hourChart.update(); }

/* buttons */
document.getElementById('download-logs').addEventListener('click', ()=>{ window.location.href='/api/errors-tail'; });
document.getElementById('restart-btn').addEventListener('click', async ()=>{ if(!confirm('Restart the bot?')) return; try{ const r = await fetch('/api/restart', {method:'POST'}); const j = await r.json(); alert(j.message||'Restarting'); }catch(e){alert('Restart failed');} });
</script></body></html>
    """,
    uptime_seconds=uptime_seconds(),
    logs_text="\n".join([f"{r[3]} | {r[0]}({r[1]}) -> {r[2]}" for r in logs]) if logs else "(no logs)",
    errors_text="".join(errors_tail) if errors_tail else "(no errors)"
    )

# API endpoints for dashboard charts/logs/errors
@flask_app.route('/api/stats')
def api_stats():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
        total_users = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
        total_files = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs")
        total_actions = c.fetchone()[0] or 0

    sys_info = {"cpu": None, "ram": None, "disk": None}
    try:
        import psutil
        sys_info["cpu"] = round(psutil.cpu_percent(interval=0.1), 1)
        sys_info["ram"] = round(psutil.virtual_memory().percent, 1)
        disk = psutil.disk_usage("/")
        sys_info["disk"] = f"{disk.free / (1024**3):.1f} GB free"
    except Exception:
        pass

    return jsonify({
        "users": total_users,
        "files": total_files,
        "actions": total_actions,
        "uptime_seconds": uptime_seconds(),
        "uptime_str": format_uptime(),
        "system": sys_info
    })

@flask_app.route('/api/chart-data')
def api_chart():
    labels, daily_users, daily_files = chart_data_last_7_days()
    return jsonify({"labels": labels, "daily_users": daily_users, "daily_files": daily_files})

@flask_app.route('/api/hourly-data')
def api_hourly():
    labels, values = hourly_distribution_today()
    return jsonify({"labels": labels, "values": values})

@flask_app.route('/api/logs')
def api_logs():
    limit = int(request.args.get("limit", "200"))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, user_id, action, timestamp FROM logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
    return jsonify(rows)

@flask_app.route('/api/errors-tail')
def api_errors_tail():
    lines = []
    try:
        if os.path.exists(ERROR_LOG):
            with open(ERROR_LOG, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-200:]
    except Exception as e:
        lines = [f"(error reading log: {e})"]
    return jsonify(lines)

@flask_app.route('/api/restart', methods=['POST'])
def api_restart():
    # logs and restart
    log_action(0, "dashboard", "restart_requested")
    def do_restart():
        time.sleep(0.9)
        try:
            python = sys.executable
            os.execv(python, [python] + sys.argv)
        except Exception:
            os._exit(0)
    threading.Thread(target=do_restart, daemon=True).start()
    return jsonify({"status":"ok","message":"restarting"}), 200

# ============ RUN ============

def run_flask():
    try:
        flask_app.run(host='0.0.0.0', port=APP_PORT)
    except Exception as e:
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.utcnow()} - Flask Error: {e}\n")
        except Exception:
            pass
        if tg_bot and OWNER_ID:
            try:
                tg_bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Flask Crash Alert ⚠️\n\n{str(e)}")
            except Exception:
                pass

if __name__ == "__main__":
    init_db()
    # start Flask in background thread
    threading.Thread(target=run_flask, daemon=True).start()

    # start telegram bot polling (blocking) if token provided
    if application:
        try:
            print("Starting Telegram bot polling...")
            application.run_polling()
        except Exception as e:
            print("Bot crashed:", e)
    else:
        print("BOT_TOKEN not set — dashboard running only.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("Stopping.")
