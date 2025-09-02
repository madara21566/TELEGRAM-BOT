# main_anime_dashboard.py
import os, sys, time, threading, datetime, sqlite3
from flask import Flask, jsonify, render_template_string, request
try:
    import psutil
except:
    psutil = None

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
APP_PORT = int(os.environ.get("PORT", "8080"))
DB_FILE = "bot_stats.db"
START_TIME = datetime.datetime.now()

def uptime_str():
    delta = datetime.datetime.now() - START_TIME
    d = delta.days
    h,m,s = str(datetime.timedelta(seconds=delta.seconds)).split(":")
    return (f"{d}d " if d else "") + f"{h}:{m}:{s}"

def uptime_seconds():
    return int((datetime.datetime.now()-START_TIME).total_seconds())

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, action TEXT, timestamp TEXT)""")
        conn.commit()

def log_action(uid, user, action):
    ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO logs(user_id,username,action,timestamp) VALUES(?,?,?,?)",
                     (uid,user,action,ts))
        conn.commit()

app=Flask(__name__)

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/stats")
def stats():
    with sqlite3.connect(DB_FILE) as conn:
        c=conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM logs"); users=c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM logs"); actions=c.fetchone()[0] or 0
    sysinfo={"cpu":None,"ram":None,"disk":None}
    if psutil:
        sysinfo["cpu"]=psutil.cpu_percent()
        sysinfo["ram"]=psutil.virtual_memory().percent
        sysinfo["disk"]=f"{psutil.disk_usage('/').free//(1024**3)} GB free"
    return jsonify({"users":users,"files":0,"actions":actions,
                    "uptime_str":uptime_str(),"uptime_seconds":uptime_seconds(),
                    "system":sysinfo})

@app.route("/api/restart",methods=["POST"])
def restart():
    def do():
        time.sleep(1)
        os.execv(sys.executable,[sys.executable]+sys.argv)
    threading.Thread(target=do,daemon=True).start()
    return jsonify({"status":"ok","msg":"restarting"})

DASHBOARD_HTML=r"""
<!doctype html><html><head>
<title>Anime Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{
  margin:0; font-family:Arial,sans-serif; color:#f0f0f0;
  background: radial-gradient(circle at top left,#ff1f8f22,transparent),
              radial-gradient(circle at bottom right,#3b82f622,transparent),
              #0a0c14;
}
.header{padding:20px;display:flex;justify-content:space-between;align-items:center}
.title{font-size:22px;font-weight:bold;color:#ff4fd8;text-shadow:0 0 8px #ff4fd8aa}
.btn{padding:8px 14px;border:none;border-radius:8px;
  background:linear-gradient(90deg,#ff1f8f,#6b21ff);color:white;cursor:pointer}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;padding:0 20px}
.card{background:rgba(255,255,255,0.05);padding:14px;border-radius:12px;text-align:center}
.num{font-size:20px;font-weight:bold}
.chart-box{margin:20px;background:rgba(255,255,255,0.05);padding:12px;border-radius:12px}
</style></head><body>
<div class="header">
  <div class="title">✨ Anime Style Dashboard</div>
  <button class="btn" onclick="restartBot()">Restart Bot</button>
</div>
<div class="stats">
  <div class="card"><div>👥 Users</div><div id="users" class="num">0</div></div>
  <div class="card"><div>⚡ Actions</div><div id="actions" class="num">0</div></div>
  <div class="card"><div>⏱ Uptime</div><div id="uptime" class="num">--:--</div></div>
  <div class="card"><div>💻 System</div><div id="sysinfo" class="num">-</div></div>
</div>
<div class="chart-box"><canvas id="chart" height="100"></canvas></div>
<script>
let sec=0;
function tick(){sec++;document.getElementById('uptime').innerText=toHMS(sec)}
function toHMS(s){let h=Math.floor(s/3600),m=Math.floor((s%3600)/60),ss=s%60;
  return h+":"+String(m).padStart(2,"0")+":"+String(ss).padStart(2,"0")}
setInterval(tick,1000);

async function loadStats(){
 let r=await fetch('/api/stats');let d=await r.json();
 document.getElementById('users').innerText=d.users;
 document.getElementById('actions').innerText=d.actions;
 sec=d.uptime_seconds;
 document.getElementById('uptime').innerText=d.uptime_str;
 document.getElementById('sysinfo').innerText=(d.system.cpu||0)+"% CPU / "+
    (d.system.ram||0)+"% RAM";
}
setInterval(loadStats,5000);loadStats();

function restartBot(){
 if(confirm("Restart bot now?")) fetch('/api/restart',{method:'POST'});
}

const ctx=document.getElementById('chart').getContext('2d');
new Chart(ctx,{type:'line',data:{labels:["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
datasets:[{label:"Users",data:[2,4,3,5,6,7,8],borderColor:"#ff4fd8"},
{label:"Actions",data:[1,2,1,3,4,5,6],borderColor:"#38bdf8"}]}});
</script>
</body></html>
"""

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=APP_PORT)
    
