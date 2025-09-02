# main_god_madara_dashboard.py
# Anime-style dashboard + Telegram bot runner
# Save, set BOT_TOKEN (optional) and run: python main_god_madara_dashboard.py

import os
import sys
import time
import threading
import datetime
import sqlite3
from flask import Flask, jsonify, render_template_string, request
try:
    import psutil
except:
    psutil = None

# telegram
from telegram import Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------- CONFIG -------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
APP_PORT = int(os.environ.get("PORT", "8080"))
DB_FILE = os.environ.get("DB_FILE", "bot_stats.db")
START_TIME = datetime.datetime.now()

# ------------- DB helpers -------------
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            timestamp TEXT
        )""")
        conn.commit()

def log_action(uid, username, action):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("INSERT INTO logs(user_id,username,action,timestamp) VALUES(?,?,?,?)",
                         (uid, username or "N/A", action, ts))
            conn.commit()
    except Exception:
        pass

# ------------- UPTIME helpers -------------
def uptime_seconds():
    return int((datetime.datetime.now() - START_TIME).total_seconds())

def uptime_str():
    delta = datetime.datetime.now() - START_TIME
    days = delta.days
    h, rem = divmod(delta.seconds, 3600)
    m, s = divmod(rem, 60)
    if days:
        return f"{days}d {h:02}:{m:02}:{s:02}"
    return f"{h:02}:{m:02}:{s:02}"

# ------------- Flask app (dashboard) -------------
app = Flask(__name__)

@app.route("/")
def dashboard():
    # simple anime theme, title = GOD MADARA BOT
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/stats")
def api_stats():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
        users = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
        files = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs")
        actions = c.fetchone()[0] or 0

    sysinfo = {"cpu": None, "ram": None, "disk": None}
    if psutil:
        try:
            sysinfo["cpu"] = round(psutil.cpu_percent(interval=0.1), 1)
            sysinfo["ram"] = round(psutil.virtual_memory().percent, 1)
            disk = psutil.disk_usage("/")
            free_gb = disk.free / (1024 ** 3)
            sysinfo["disk"] = f"{free_gb:.1f} GB free"
        except Exception:
            pass

    return jsonify({
        "users": users,
        "files": files,
        "actions": actions,
        "uptime_seconds": uptime_seconds(),
        "uptime_str": uptime_str(),
        "system": sysinfo
    })

@app.route("/api/logs")
def api_logs():
    limit = int(request.args.get("limit", "200"))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, user_id, action, timestamp FROM logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
    return jsonify(rows)

@app.route("/api/errors-tail")
def api_errors_tail():
    # return last 200 lines of error log if exists
    errfile = os.environ.get("ERROR_LOG", "bot_errors.log")
    lines = []
    try:
        if os.path.exists(errfile):
            with open(errfile, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-200:]
    except Exception as e:
        lines = [f"(error reading log: {e})"]
    return jsonify(lines)

@app.route("/api/restart", methods=["POST"])
def api_restart():
    # restart server (unprotected). If you deploy publicly, protect this endpoint.
    log_action(0, "dashboard", "restart_requested")
    def do_restart():
        time.sleep(0.9)
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception:
            os._exit(0)
    threading.Thread(target=do_restart, daemon=True).start()
    return jsonify({"status": "ok", "message": "restarting"})

# ------------- Dashboard HTML (anime-style) -------------
DASHBOARD_HTML = r"""
<!doctype html><html><head>
<meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GOD MADARA BOT — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{--bg:#05060a;--accent1:#ff4fd8;--accent2:#6b21ff;--muted:#9aa4b2}
*{box-sizing:border-box}body{margin:0;font-family:Inter,Arial,Helvetica;background:
 radial-gradient(circle at 10% 10%, rgba(124,58,237,0.06), transparent 6%),
 radial-gradient(circle at 90% 90%, rgba(6,182,212,0.04), transparent 8%), #0a0c14;color:#e6eef6}
.header{display:flex;align-items:center;gap:12px;padding:18px 22px}
.logo{width:64px;height:64px;border-radius:12px;background:linear-gradient(135deg,var(--accent1),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:900;font-size:20px;box-shadow:0 10px 40px rgba(107,33,255,0.12)}
.title{font-size:20px;font-weight:800;font-family:Roboto,serif;color:var(--accent1);text-shadow:0 4px 20px rgba(124,58,237,0.08)}
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

      <div class="card" style="grid-column:span 8"><strong>Recent Activity</strong><div class="logs"><pre id="recent-logs">Loading...</pre></div></div>
      <div class="card" style="grid-column:span 4"><strong>Recent Errors</strong><pre id="recent-errors">Loading...</pre></div>
    </div>
  </div>

<script>
let uptime_sec = 0;
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
  try{ const r=await fetch('/api/logs?limit=200'); const rows = await r.json(); document.getElementById('recent-logs').innerText = rows.map(r=>`${r[4]} | ${r[1]}(${r[2]}) -> ${r[3]}`).join('\\n'); }catch(e){document.getElementById('recent-logs').innerText='(no logs)'}
  try{ const r2=await fetch('/api/errors-tail'); const errs = await r2.json(); document.getElementById('recent-errors').innerText = errs.join('') }catch(e){document.getElementById('recent-errors').innerText='(no errors)'}
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
"""

# ------------- Telegram Bot: basic handlers -------------
async def start_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_action(user.id if user else 0, user.username if user else "N/A", "start")
    await update.message.reply_text("GOD MADARA BOT is online ✅")

async def text_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_action(user.id if user else 0, user.username if user else "N/A", "text")
    await update.message.reply_text("Message received. Dashboard active.")

# ------------- Run helpers -------------
def run_flask():
    app.run(host="0.0.0.0", port=APP_PORT)

def run_bot_polling():
    # starts telegram polling (blocking)
    app_builder = Application.builder().token(BOT_TOKEN).build()
    app_builder.add_handler(CommandHandler("start", start_handler))
    app_builder.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    # error handler could be added here
    app_builder.run_polling()

if __name__ == "__main__":
    init_db()
    # start Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    if BOT_TOKEN:
        print("BOT_TOKEN found — starting Telegram polling (bot).")
        try:
            run_bot_polling()  # blocking: bot runs in main thread
        except Exception as e:
            print("Bot crashed:", e)
    else:
        print("BOT_TOKEN not set — running dashboard only. Set BOT_TOKEN to run Telegram bot.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("Stopping.")
