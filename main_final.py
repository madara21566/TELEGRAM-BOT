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

def get_access_text():
    return (
        "📂💾 *VCF Bot Access*\n"
        "Want my *VCF Converter Bot*?\n"
        "Just DM me anytime — I’ll reply to you fast!\n\n"
        "📩 *Direct Message here:* @MADARAXHEREE\n\n"
        "⚡ Convert TXT ⇄ VCF instantly | 🪄 Easy & Quick | 🔒 Trusted"
    )

def protected(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        try:
            if not is_authorized(user.id):
                # replaced old ❌ message with premium access text (no other code changed)
                await update.message.reply_text(get_access_text(), parse_mode="Markdown")
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
    return render_template_string("""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>GOD MADARA — Animated Dashboard</title>

  <!-- Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

  <style>
    /* ====== Palette & Reset ====== */
    :root{
      --bg:#07060b; --panel:rgba(255,255,255,0.03); --glass:rgba(255,255,255,0.04);
      --neon1:#ff4fd8; --neon2:#6b21ff; --accent:#38bdf8; --muted:#98a6b3; --glass-border:rgba(255,255,255,0.06);
    }
    *{box-sizing:border-box} body{margin:0;font-family:Inter,ui-sans-serif,system-ui,Segoe UI,Roboto,"Helvetica Neue",Arial;background:linear-gradient(180deg,#05050a 0%, #071022 60%), radial-gradient(circle at 10% 20%, rgba(107,33,255,0.06), transparent 6%); color:#e6eef6; -webkit-font-smoothing:antialiased}

    /* ====== Layout ====== */
    .wrap{max-width:1200px;margin:28px auto;padding:16px}
    .topbar{display:flex;align-items:center;gap:16px}
    .logo{width:64px;height:64px;border-radius:14px;display:grid;place-items:center;font-weight:900;font-size:22px;background:linear-gradient(135deg,var(--neon1),var(--neon2));box-shadow:0 10px 40px rgba(107,33,255,0.12);border:1px solid rgba(255,255,255,0.06)}
    .hdr-title{line-height:1}
    .hdr-title h1{margin:0;font-size:18px;letter-spacing:0.2px}
    .hdr-title p{margin:2px 0 0 0;font-size:12px;color:var(--muted)}

    .controls{margin-left:auto;display:flex;gap:10px}
    .btn{background:linear-gradient(90deg,var(--neon1),var(--neon2));border:none;color:white;padding:9px 12px;border-radius:10px;font-weight:700;cursor:pointer;box-shadow:0 8px 30px rgba(107,33,255,0.12);transform:translateY(0);transition:transform .18s ease}
    .btn:active{transform:translateY(2px)}
    .ghost{background:transparent;border:1px solid rgba(255,255,255,0.06);padding:8px 10px;border-radius:10px;color:var(--muted)}

    /* ====== Grid ====== */
    .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;margin-top:18px}
    .card{background:linear-gradient(180deg,var(--panel), transparent);padding:14px;border-radius:14px;border:1px solid var(--glass-border);box-shadow:0 6px 30px rgba(3,6,20,0.5);backdrop-filter:blur(6px)}

    .stat{grid-column:span 3;padding:14px;display:flex;flex-direction:column;gap:8px}
    .muted{color:var(--muted);font-size:12px}
    .num{font-size:20px;font-weight:800;letter-spacing:0.6px}
    .upt{font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, monospace}

    .chart{grid-column:span 8}
    .side{grid-column:span 4}
    .logs{grid-column:span 8}
    .errors{grid-column:span 4}

    /* ====== Recent logs/errors styling ====== */
    pre.logsbox{max-height:340px;overflow:auto;background:linear-gradient(180deg,rgba(255,255,255,0.01),transparent);padding:12px;border-radius:10px;color:#bfe7ff;font-size:13px}
    pre.errbox{max-height:340px;overflow:auto;background:linear-gradient(180deg,rgba(255,255,255,0.01),transparent);padding:12px;border-radius:10px;color:#ffd6e8;font-size:13px}

    /* ====== small UI flourishes ====== */
    .spark{height:10px;width:10px;border-radius:50%;box-shadow:0 6px 18px rgba(255,79,216,0.25);background:linear-gradient(90deg,var(--neon1),var(--neon2));display:inline-block;margin-right:8px;vertical-align:middle}

    /* card headers */
    .card h3{margin:0 0 8px 0;font-size:14px}

    /* Responsive */
    @media (max-width:980px){.stat{grid-column:span 6}.chart{grid-column:span 12}.side{grid-column:span 12}.logs, .errors{grid-column:span 12}}

    /* ====== subtle animation ====== */
    .glow{animation:glow 2.6s ease-in-out infinite}
    @keyframes glow{0%{filter:drop-shadow(0 6px 14px rgba(107,33,255,0.06))}50%{filter:drop-shadow(0 12px 34px rgba(107,33,255,0.12))}100%{filter:drop-shadow(0 6px 14px rgba(107,33,255,0.06))}}

    /* floating orb background */
    #bgcanvas{position:fixed;right:-10%;top:-12%;width:720px;height:720px;pointer-events:none;opacity:0.12;mix-blend-mode:screen}

    /* tiny animated counters */
    .count{font-weight:900;font-size:20px}
  </style>
</head>
<body>
  <!-- decorative canvas for soft neon orb -->
  <canvas id="bgcanvas"></canvas>

  <div class="wrap">
    <div class="topbar">
      <div class="logo glow">G</div>
      <div class="hdr-title">
        <h1 style="color:var(--neon1)">GOD MADARA BOT</h1>
        <p>Anime-style monitoring · Neon dashboard</p>
      </div>

      <div class="controls">
        <button class="ghost" id="download-logs">Download Errors</button>
        <button class="btn" id="restart-btn">Restart Bot</button>
      </div>
    </div>

    <div class="grid">
      <div class="card stat">
        <div class="muted">👥 Users</div>
        <div id="stat-users" class="num count">0</div>
        <div class="muted">Unique users</div>
      </div>

      <div class="card stat">
        <div class="muted">📁 Files</div>
        <div id="stat-files" class="num count">0</div>
        <div class="muted">VCF generated</div>
      </div>

      <div class="card stat">
        <div class="muted">⚡ Actions</div>
        <div id="stat-actions" class="num count">0</div>
        <div class="muted">Commands executed</div>
      </div>

      <div class="card stat">
        <div class="muted">⏱ Uptime</div>
        <div id="stat-uptime" class="num upt">--:--:--</div>
        <div class="muted">Backend</div>
      </div>

      <div class="card chart">
        <h3><span class="spark"></span>Activity (last 7 days)</h3>
        <canvas id="chartMain" height="140"></canvas>
      </div>

      <div class="card side">
        <h3><span class="spark" style="box-shadow:0 6px 18px rgba(56,189,248,0.14);background:var(--accent)"></span>Peak Hours Today</h3>
        <canvas id="chartHours" height="140"></canvas>
        <div style="height:10px"></div>
        <div class="muted" id="sysinfo">System: -</div>
      </div>

      <div class="card logs" style="grid-column:span 8">
        <h3>Recent Activity</h3>
        <pre id="recent-logs" class="logsbox">{{logs_text}}</pre>
      </div>

      <div class="card errors" style="grid-column:span 4">
        <h3>Recent Errors</h3>
        <pre id="recent-errors" class="errbox">{{errors_text}}</pre>
      </div>
    </div>
  </div>

<script>
/* ====== Neon orb background (simple particle gradient) ====== */
(function(){const c=document.getElementById('bgcanvas');const d=c.getContext('2d');function resize(){c.width=720;c.height=720;c.style.right='-8%';}resize();window.addEventListener('resize', resize);
function draw(){d.clearRect(0,0,c.width,c.height);
// soft gradient blobs
const g=d.createRadialGradient(200,180,0,200,180,380);
g.addColorStop(0,'rgba(107,33,255,0.55)');g.addColorStop(0.4,'rgba(124,58,237,0.08)');g.addColorStop(1,'rgba(6,182,212,0)');
d.fillStyle=g;d.fillRect(0,0,c.width,c.height);
}
let t=setInterval(draw, 1200);draw();})();

/* ====== Utilities ====== */
function pad(n){return String(n).padStart(2,'0')}
function secToHMS(s){const d=Math.floor(s/86400);s%=86400;const h=Math.floor(s/3600);const m=Math.floor((s%3600)/60);const ss=s%60;return (d?d+'d ':'')+pad(h)+':'+pad(m)+':'+pad(ss)}

/* ====== Animated counter helper ====== */
function animateValue(el, start, end, duration=800){const range=end-start;let startTime=null;function step(ts){if(!startTime)startTime=ts;const progress=Math.min((ts-startTime)/duration,1);const val=Math.floor(start + range*easeOutCubic(progress));el.innerText=val; if(progress<1)requestAnimationFrame(step);}requestAnimationFrame(step);
}
function easeOutCubic(t){return 1-Math.pow(1-t,3)}

/* ====== Charts setup ====== */
const mainCtx = document.getElementById('chartMain').getContext('2d');
const mainChart = new Chart(mainCtx,{
  type:'line',
  data:{labels:[],datasets:[{label:'Users',data:[],borderColor:'rgba(255,79,216,0.95)',tension:0.35,pointRadius:3,fill:false},{label:'Files',data:[],borderColor:'rgba(56,189,248,0.95)',tension:0.35,pointRadius:3,fill:false}]},
  options:{plugins:{legend:{display:true,labels:{color:'#cfeefc'}}},scales:{x:{ticks:{color:'#9fbcd1'}},y:{beginAtZero:true,ticks:{color:'#9fbcd1'}}},elements:{line:{borderWidth:3}}}
});

const hoursCtx = document.getElementById('chartHours').getContext('2d');
const hourChart = new Chart(hoursCtx,{type:'bar',data:{labels:[],datasets:[{label:'Events',data:[],backgroundColor:'rgba(107,33,255,0.7)'}]},options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#9fbcd1'}},y:{ticks:{color:'#9fbcd1'},beginAtZero:true}}}});

/* ====== Fetch & update functions ====== */
let uptime_sec = {{uptime_seconds}};
function updateStatsDOM(data){ const usersEl=document.getElementById('stat-users'); const filesEl=document.getElementById('stat-files'); const actsEl=document.getElementById('stat-actions');
  animateValue(usersEl, parseInt(usersEl.innerText||0), data.users||0, 700);
  animateValue(filesEl, parseInt(filesEl.innerText||0), data.files||0, 700);
  animateValue(actsEl, parseInt(actsEl.innerText||0), data.actions||0, 700);
  uptime_sec = data.uptime_seconds || uptime_sec; document.getElementById('stat-uptime').innerText = data.uptime_str || secToHMS(uptime_sec);
  const sys = data.system || {}; document.getElementById('sysinfo').innerText = (sys.cpu?sys.cpu+'% CPU':'-') + ' / ' + (sys.ram?sys.ram+'% RAM':'-') + ' / ' + (sys.disk||'-');
}

async function fetchStats(){ try{ const res=await fetch('/api/stats'); const d=await res.json(); updateStatsDOM(d);}catch(e){console.warn('stats',e)} }
async function fetchCharts(){ try{ const r=await fetch('/api/chart-data'); const d=await r.json(); mainChart.data.labels=d.labels; mainChart.data.datasets[0].data=d.daily_users; mainChart.data.datasets[1].data=d.daily_files; mainChart.update(); }catch(e){console.warn('chart',e)} }
async function fetchHourly(){ try{ const r=await fetch('/api/hourly-data'); const d=await r.json(); hourChart.data.labels=d.labels; hourChart.data.datasets[0].data=d.values; hourChart.update(); }catch(e){console.warn('hourly',e)} }
async function fetchLogsAndErrors(){ try{ const r=await fetch('/api/logs?limit=200'); const rows = await r.json(); document.getElementById('recent-logs').innerText = rows.map(r=>`${r[4]} | ${r[1]}(${r[2]}) -> ${r[3]}`).join('\\n'); }catch(e){}
 try{ const r2=await fetch('/api/errors-tail'); const errs = await r2.json(); document.getElementById('recent-errors').innerText = errs.join(''); }catch(e){} }

/* refresh loop */
setInterval(()=>{ fetchStats(); fetchCharts(); fetchHourly(); fetchLogsAndErrors(); }, 5000);
fetchStats(); fetchCharts(); fetchHourly(); fetchLogsAndErrors();

/* uptime ticking */
setInterval(()=>{ uptime_sec++; document.getElementById('stat-uptime').innerText = secToHMS(uptime_sec); }, 1000);

/* ====== Buttons ====== */
document.getElementById('download-logs').addEventListener('click', ()=>{ window.location.href='/api/errors-tail'; });
document.getElementById('restart-btn').addEventListener('click', async ()=>{ if(!confirm('Restart the bot?')) return; try{ const r = await fetch('/api/restart', {method:'POST'}); const j = await r.json(); alert(j.message||'Restarting'); }catch(e){alert('Restart failed');} });

</script>
</body>
</html>""",
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
