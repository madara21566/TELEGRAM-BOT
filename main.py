import os
import sys
import io
import time
import threading
import sqlite3
import datetime
import traceback
from typing import Optional, List, Tuple

from flask import Flask, render_template_string, jsonify, send_file, request
from telegram import Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# optional system info
try:
    import psutil
except Exception:
    psutil = None

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
APP_PORT = int(os.environ.get("PORT", "8080"))
DB_FILE = os.environ.get("DB_FILE", "bot_stats.db")
ERROR_LOG = os.environ.get("ERROR_LOG", "bot_errors.log")
MADARA_URL = os.environ.get("MADARA_URL", "")  # optional remote URL for background
REQUIRE_RESTART_TOKEN = os.environ.get("REQUIRE_RESTART_TOKEN", "0") == "1"  # if "1", restart requires token
RESTART_TOKEN = os.environ.get("RESTART_TOKEN", "secret-token")  # keep safe if REQUIRE_RESTART_TOKEN==1

# ---------------- UPTIME ----------------
START_TIME = datetime.datetime.now()

def format_uptime_seconds():
    delta = datetime.datetime.now() - START_TIME
    return int(delta.total_seconds())

def format_uptime_str():
    delta = datetime.datetime.now() - START_TIME
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# ---------------- DB helpers ----------------
def init_db():
    os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)
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
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
                  (user_id, username or "N/A", action, ts))
        conn.commit()

# ---------------- Telegram bot skeleton ----------------
# Replace these stubs by importing your real bot module if present.
async def stub_start(update, context):
    await update.message.reply_text("AnimeBot connected ✅")

async def stub_text(update, context):
    await update.message.reply_text("Message received. Dashboard is watching ✨")

application = None
tg_bot = None
if BOT_TOKEN:
    application = Application.builder().token(BOT_TOKEN).build()
    tg_bot = Bot(BOT_TOKEN)
    application.add_handler(CommandHandler("start", stub_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, stub_text))

# ---------------- Flask app ----------------
app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET", "anime-super-secret")

# ---------------- Data functions ----------------
def chart_data_last_7_days() -> Tuple[List[str], List[int], List[int]]:
    today = datetime.datetime.now().date()
    days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
    labels = [d.strftime("%d %b") for d in days]
    daily_users = {d.strftime("%Y-%m-%d"): set() for d in days}
    daily_files = {d.strftime("%Y-%m-%d"): 0 for d in days}
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT user_id, action, date(timestamp)
            FROM logs
            WHERE date(timestamp) >= date(?)
        """, ((today - datetime.timedelta(days=6)).strftime("%Y-%m-%d"),))
        for uid, action, dt in c.fetchall():
            if dt in daily_users:
                daily_users[dt].add(uid)
            if dt in daily_files and action == 'makevcf':
                daily_files[dt] += 1
    users_counts = [len(daily_users[d.strftime("%Y-%m-%d")]) for d in days]
    files_counts = [daily_files[d.strftime("%Y-%m-%d")] for d in days]
    return labels, users_counts, files_counts

def hourly_distribution_today() -> Tuple[List[str], List[int]]:
    today = datetime.datetime.now().strftime("%Y-%m-%d")
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
            if hh in buckets:
                buckets[hh] = cnt
    labels = list(buckets.keys())
    values = [buckets[k] for k in labels]
    return labels, values

# ---------------- API endpoints ----------------
@app.route("/api/stats")
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
    if psutil:
        try:
            sys_info["cpu"] = round(psutil.cpu_percent(interval=0.1), 1)
            mem = psutil.virtual_memory()
            sys_info["ram"] = round(mem.percent, 1)
            disk = psutil.disk_usage("/")
            free_gb = (disk.free / (1024**3))
            sys_info["disk"] = f"{free_gb:.1f} GB free"
        except Exception:
            pass

    return jsonify({
        "users": total_users,
        "files": total_files,
        "actions": total_actions,
        "uptime_seconds": format_uptime_seconds(),
        "uptime_str": format_uptime_str(),
        "system": sys_info
    })

@app.route("/api/chart-data")
def api_chart():
    labels, users, files = chart_data_last_7_days()
    return jsonify({"labels": labels, "daily_users": users, "daily_files": files})

@app.route("/api/hourly-data")
def api_hour():
    labels, values = hourly_distribution_today()
    return jsonify({"labels": labels, "values": values})

@app.route("/api/errors-tail")
def api_errors_tail():
    lines = []
    try:
        if os.path.exists(ERROR_LOG):
            with open(ERROR_LOG, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-200:]
    except Exception as e:
        lines = [f"(error reading log: {e})"]
    return jsonify(lines)

@app.route("/api/logs")
def api_logs():
    # returns last N logs (public). You can restrict or remove this if sensitive.
    limit = int(request.args.get("limit", "200"))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, user_id, action, timestamp FROM logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
    return jsonify(rows)

# Restart endpoint
@app.route("/api/restart", methods=["POST"])
def api_restart():
    # optional token-based protection
    if REQUIRE_RESTART_TOKEN:
        token = request.json.get("token") if request.is_json else request.form.get("token")
        if not token or token != RESTART_TOKEN:
            return jsonify({"status":"error","reason":"invalid token"}), 403

    # log restart action
    log_action(0, "dashboard", "restart_requested")
    # respond quickly then restart in background
    def do_restart():
        time.sleep(0.9)
        try:
            python = sys.executable
            os.execv(python, [python] + sys.argv)
        except Exception:
            # fallback: exit (supervisor should restart)
            os._exit(0)

    threading.Thread(target=do_restart, daemon=True).start()
    return jsonify({"status":"ok","message":"restarting"}), 200

# ---------------- Anime-styled Dashboard (Madara) ----------------
# Template uses MADARA_URL or local static/madara.jpg as background.
DASHBOARD_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>🌸 Madara — AnimeBot Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;700;800&family=Roboto+Slab:wght@300;400;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{
  --bg:#05060a;
  --glass: rgba(255,255,255,0.03);
  --accent1: #7c3aed;
  --accent2: #06b6d4;
  --muted:#9aa4b2;
}
*{box-sizing:border-box}
body{
  margin:0; min-height:100vh; font-family:Inter,system-ui,Arial;
  color:#e6eef6;
  background: radial-gradient(1200px 600px at 10% 10%, rgba(124,58,237,0.06), transparent 6%),
              radial-gradient(1000px 500px at 90% 90%, rgba(6,182,212,0.04), transparent 8%),
              var(--bg);
}
/* background artwork layer */
.bg-art {
  position: fixed; inset:0; z-index:0; background-size:cover; background-position:center; filter:brightness(0.5) contrast(1.06);
  opacity:0.95;
}
/* glass container */
.wrap{position:relative; z-index:5; max-width:1200px;margin:28px auto;padding:18px}
.header{display:flex;align-items:center;gap:16px}
.logo{width:64px;height:64px;border-radius:12px;background:linear-gradient(135deg,var(--accent1),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:800;font-size:28px;box-shadow:0 12px 40px rgba(12,12,20,0.6)}
.title{font-family:"Roboto Slab",serif;font-weight:700;font-size:20px}
.subtitle{color:var(--muted);font-size:13px}
.controls{margin-left:auto;display:flex;gap:8px;align-items:center}
.btn{padding:8px 12px;border-radius:10px;border:none;background:linear-gradient(90deg,var(--accent1),var(--accent2));color:white;font-weight:700;cursor:pointer}
.btn.ghost{background:transparent;border:1px solid rgba(255,255,255,0.05)}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin-top:18px}
.card{background:linear-gradient(180deg,rgba(255,255,255,0.02),transparent);border-radius:12px;padding:14px;border:1px solid rgba(255,255,255,0.03);backdrop-filter:blur(6px)}
.stat{grid-column:span 3;display:flex;flex-direction:column;gap:6px}
.stat .num{font-size:22px;font-weight:800}
.stat .muted{color:var(--muted);font-size:12px}
@media (max-width:900px){.stat{grid-column:span 6}.chart{grid-column:span 12}.side{grid-column:span 12}}
.chart{grid-column:span 8}
.side{grid-column:span 4}
.logs pre{max-height:300px;overflow:auto;background:#041229;padding:12px;border-radius:8px;color:#bfe7ff}
.uptime{font-family:monospace;font-weight:700}
.notice{color:var(--muted);font-size:12px;margin-top:8px}
</style>
</head>
<body>
  <div id="bg" class="bg-art"></div>
  <div class="wrap">
    <div class="header">
      <div class="logo">M</div>
      <div>
        <div class="title">🌑 Madara — AnimeBot Dashboard</div>
        <div class="subtitle">Realistic anime background · Live uptime · Restart control</div>
      </div>
      <div class="controls">
        <button class="btn ghost" id="download-logs">Download Errors</button>
        <button class="btn" id="restart-btn">Restart Bot</button>
      </div>
    </div>

    <div class="grid" style="margin-top:14px">
      <div class="card stat">
        <div class="muted">👥 Users</div>
        <div class="num" id="stat-users">0</div>
        <div class="muted">Unique users</div>
      </div>

      <div class="card stat">
        <div class="muted">📁 Files</div>
        <div class="num" id="stat-files">0</div>
        <div class="muted">VCF generated</div>
      </div>

      <div class="card stat">
        <div class="muted">⚡ Actions</div>
        <div class="num" id="stat-actions">0</div>
        <div class="muted">Commands & events</div>
      </div>

      <div class="card stat">
        <div class="muted">⏱ Uptime</div>
        <div class="num uptime" id="uptime">--:--:--</div>
        <div class="muted">Backend uptime</div>
      </div>

      <div class="card chart">
        <strong>Activity (last 7 days)</strong>
        <canvas id="chartMain" height="120" style="margin-top:10px"></canvas>
        <div class="notice">Data refreshes automatically.</div>
      </div>

      <div class="card side">
        <strong>Peak Hours Today</strong>
        <canvas id="chartHours" height="180" style="margin-top:12px"></canvas>
        <div style="height:12px"></div>
        <div class="muted">System</div>
        <div id="sysinfo" class="muted">Loading...</div>
      </div>

      <div class="card" style="grid-column:span 8">
        <strong>Recent Activity</strong>
        <div class="logs"><pre id="recent-logs">Loading logs...</pre></div>
      </div>

      <div class="card" style="grid-column:span 4">
        <strong>Recent Errors</strong>
        <pre id="recent-errors">Loading errors...</pre>
      </div>
    </div>
  </div>

<script>
const MADARA_URL = "{{ madara_url }}";
const REQUIRE_TOKEN = {{ require_token|lower }};
const RESTART_TOKEN = "{{ restart_token }}";

(function setBg(){
  const el = document.getElementById('bg');
  if(MADARA_URL && MADARA_URL.length>5){
    el.style.backgroundImage = `url('${MADARA_URL}')`;
    return;
  }
  // fallback to local static file if exists
  el.style.backgroundImage = "url('/static/madara.jpg')";
})();

function pad(n){return String(n).padStart(2,'0')}
function secToHMS(sec){
  const d = Math.floor(sec / 86400);
  sec = sec % 86400;
  const h = Math.floor(sec/3600);
  const m = Math.floor((sec%3600)/60);
  const s = sec%60;
  return (d>0? d+'d ':'') + pad(h)+':'+pad(m)+':'+pad(s);
}

let uptime_seconds = 0;
async function fetchStats(){
  try{
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('stat-users').innerText = data.users;
    document.getElementById('stat-files').innerText = data.files;
    document.getElementById('stat-actions').innerText = data.actions;
    uptime_seconds = data.uptime_seconds || 0;
    document.getElementById('uptime').innerText = data.uptime_str || secToHMS(uptime_seconds);
    let sys = data.system || {};
    document.getElementById('sysinfo').innerText = (sys.cpu!==null? sys.cpu+'% CPU / ':'') + (sys.ram!==null? sys.ram+'% RAM / ':'') + (sys.disk||'');
    window.updateChartsFromStats && window.updateChartsFromStats(data);
  }catch(e){ console.error(e) }
}

async function fetchCharts(){
  try{
    const res = await fetch('/api/chart-data');
    const d = await res.json();
    updateMainChart(d.labels, d.daily_users, d.daily_files);
  }catch(e){console.error(e)}
}
async function fetchHourly(){
  try{
    const res = await fetch('/api/hourly-data');
    const d = await res.json();
    updateHourChart(d.labels, d.values);
  }catch(e){console.error(e)}
}
async function fetchLogs(){
  try{
    const res = await fetch('/api/logs?limit=200');
    const rows = await res.json();
    const text = rows.map(r => `${r[4]} | ${r[1]}(${r[2]}) → ${r[3]}`).join('\\n');
    document.getElementById('recent-logs').innerText = text || "(no logs)";
  }catch(e){ document.getElementById('recent-logs').innerText = "(unable to fetch logs)"; }
  try{
    const res2 = await fetch('/api/errors-tail');
    const errs = await res2.json();
    document.getElementById('recent-errors').innerText = errs.join('').slice(-6000) || "(no errors)";
  }catch(e){ document.getElementById('recent-errors').innerText="(unable to fetch errors)"; }
}

/* charts */
let mainChart=null, hourChart=null;
function createCharts(){
  const ctx = document.getElementById('chartMain').getContext('2d');
  mainChart = new Chart(ctx, {
    type:'line',
    data:{labels:[], datasets:[
      {label:'Active Users', data:[], tension:0.3, borderWidth:2, pointRadius:3},
      {label:'Files Generated', data:[], tension:0.3, fill:true, borderWidth:0}
    ]},
    options:{responsive:true, scales:{y:{beginAtZero:true}}}
  });
  const ctx2 = document.getElementById('chartHours').getContext('2d');
  hourChart = new Chart(ctx2, {type:'bar', data:{labels:[], datasets:[{label:'Events', data:[]}]}, options:{responsive:true, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true}}}});
}
function updateMainChart(labels, users, files){
  if(!mainChart) return;
  mainChart.data.labels = labels;
  mainChart.data.datasets[0].data = users;
  mainChart.data.datasets[1].data = files;
  mainChart.update();
}
function updateHourChart(labels, vals){
  if(!hourChart) return;
  hourChart.data.labels = labels;
  hourChart.data.datasets[0].data = vals;
  hourChart.update();
}

/* uptime tick */
setInterval(()=>{ uptime_seconds++; document.getElementById('uptime').innerText = secToHMS(uptime_seconds); }, 1000);

/* init */
createCharts();
fetchStats(); fetchCharts(); fetchHourly(); fetchLogs();
setInterval(()=>{ fetchStats(); fetchCharts(); fetchHourly(); fetchLogs(); }, 5000);

/* buttons */
document.getElementById('download-logs').addEventListener('click', ()=>{ window.location.href='/api/errors-tail'; });

document.getElementById('restart-btn').addEventListener('click', async () => {
  if(!confirm('Restart the bot now?')) return;
  let payload = {};
  if(REQUIRE_TOKEN){
    const token = prompt('Enter restart token:');
    if(!token) return alert('Token required.');
    payload.token = token;
  }
  try{
    const res = await fetch('/api/restart', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const resp = await res.json();
    if(res.ok){
      alert('Restarting... page will become unresponsive briefly.');
    } else {
      alert('Restart failed: ' + (resp.reason || resp.message || JSON.stringify(resp)));
    }
  }catch(e){ alert('Restart request failed'); console.error(e) }
});
</script>
</body>
</html>
'''

from flask import render_template_string as _rts

@app.route("/")
def dashboard():
    # pass madara url and restart token config into template
    return _rts(DASHBOARD_HTML, madara_url=(MADARA_URL or ""), require_token=str(REQUIRE_RESTART_TOKEN), restart_token=RESTART_TOKEN)

# ---------------- Run helpers ----------------
def run_flask():
    try:
        app.run(host="0.0.0.0", port=APP_PORT)
    except Exception as e:
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.utcnow()} - Flask Error: {e}\n")
        except Exception:
            pass
        try:
            if tg_bot:
                tg_bot.send_message(chat_id=0, text=f"⚠️ Flask Crash: {e}")
        except Exception:
            pass

# ---------------- Entrypoint ----------------
if __name__ == "__main__":
    init_db()
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    if application:
        application.run_polling()
    else:
        print("BOT_TOKEN not set — Flask dashboard running only.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("Stopping.")
    
