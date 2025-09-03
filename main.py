# dashboard_demo.py
# Simple Flask app that serves a modern admin/dashboard page (cards + charts).
# Run: pip install flask
# Then: python dashboard_demo.py
from flask import Flask, render_template_string, jsonify
import random, datetime

app = Flask(__name__)

TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Admin Dashboard — Demo</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{
  --bg:#f6f8fb; --card:#ffffff; --muted:#7b8a99;
  --accent:#6b21ff; --accent2:#06b6d4; --accent-ghost: linear-gradient(90deg,#6b21ff,#06b6d4);
  --shadow: 0 8px 28px rgba(15,23,42,0.08);
}
*{box-sizing:border-box}
body{font-family:Inter,system-ui,Arial;background:var(--bg);margin:0;color:#0f172a}
.app{display:flex;min-height:100vh}
/* sidebar */
.sidebar{width:260px;background:#fff;border-right:1px solid #eef2f6;padding:22px;display:flex;flex-direction:column;gap:18px}
.brand{display:flex;align-items:center;gap:12px}
.logo{width:44px;height:44px;border-radius:10px;background:linear-gradient(135deg,#6b21ff,#06b6d4);display:flex;align-items:center;justify-content:center;color:white;font-weight:800}
.brand h2{margin:0;font-size:16px}
.nav{display:flex;flex-direction:column;gap:8px;margin-top:6px}
.nav a{padding:10px 12px;border-radius:8px;color:#334155;text-decoration:none;display:flex;align-items:center;gap:10px}
.nav a:hover{background:#f1f5f9}
.left-foot{margin-top:auto;font-size:13px;color:var(--muted)}

/* main content */
.main{flex:1;padding:20px 28px}
.header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}
.search{flex:1;margin:0 16px}
.search input{width:100%;padding:10px 12px;border-radius:10px;border:1px solid #e6eef6;background:#fbfdff}
.top-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:18px}
.card{background:var(--card);padding:18px;border-radius:12px;box-shadow:var(--shadow);border:1px solid #f0f4f8}
.card .label{font-size:13px;color:var(--muted);margin-bottom:6px}
.card .value{font-size:22px;font-weight:700}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:16px}

/* charts and lists */
.panel{background:var(--card);padding:18px;border-radius:12px;box-shadow:var(--shadow);border:1px solid #f0f4f8}
.small-grid{display:flex;flex-direction:column;gap:12px}
.row{display:flex;gap:12px;align-items:center}
.kpi{display:flex;flex-direction:column}
.kpi .num{font-weight:700;font-size:18px}
.legend{display:flex;gap:10px;align-items:center}

/* responsive */
@media (max-width:980px){
  .sidebar{display:none}
  .top-cards{grid-template-columns:repeat(2,1fr)}
  .grid{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <div class="logo">H</div>
      <div>
        <h2>H-care</h2>
        <div style="font-size:13px;color:var(--muted)">Admin panel</div>
      </div>
    </div>
    <div class="nav">
      <a href="#">🏠 Overview</a>
      <a href="#">🧾 Patients</a>
      <a href="#">🗺 Map</a>
      <a href="#">🏥 Departments</a>
      <a href="#">🧑‍⚕️ Doctors</a>
      <a href="#">📜 History</a>
      <a href="#">⚙ Settings</a>
    </div>
    <div class="left-foot">© {{year}} • Your Company</div>
  </aside>

  <main class="main">
    <div class="header">
      <div style="display:flex;align-items:center;gap:12px">
        <button style="padding:8px 10px;border-radius:10px;border:none;background:var(--accent);color:white;font-weight:700">Register patient +</button>
        <div class="search"><input placeholder="Search..." /></div>
        <div style="display:flex;gap:10px;align-items:center">
          <div style="text-align:right">
            <div style="font-weight:700">Emma Kwan</div>
            <div style="font-size:12px;color:var(--muted)">Admin</div>
          </div>
        </div>
      </div>
    </div>

    <div class="top-cards">
      <div class="card">
        <div class="label">Total Patients</div>
        <div class="value" id="metric-patients">3,256</div>
      </div>
      <div class="card">
        <div class="label">Available Staff</div>
        <div class="value" id="metric-staff">394</div>
      </div>
      <div class="card">
        <div class="label">Avg. Treat. Costs</div>
        <div class="value" id="metric-cost">$2,536</div>
      </div>
      <div class="card">
        <div class="label">Available Cars</div>
        <div class="value" id="metric-cars">38</div>
      </div>
    </div>

    <div class="grid">
      <div>
        <div class="panel">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <h3 style="margin:0">Outpatients vs. Inpatients Trend</h3>
              <div style="color:var(--muted);font-size:13px">Show by month</div>
            </div>
            <div class="legend">
              <div style="display:flex;align-items:center;gap:8px"><span style="width:10px;height:10px;background:#7c3aed;border-radius:2px;display:inline-block"></span> Inpatients</div>
              <div style="display:flex;align-items:center;gap:8px"><span style="width:10px;height:10px;background:#06b6d4;border-radius:2px;display:inline-block"></span> Outpatients</div>
            </div>
          </div>
          <canvas id="trendChart" style="margin-top:14px" height="160"></canvas>
        </div>

        <div style="height:16px"></div>

        <div class="panel">
          <h3 style="margin:0">Time Admitted — Today</h3>
          <canvas id="lineChart" height="110" style="margin-top:12px"></canvas>
        </div>
      </div>

      <aside>
        <div class="panel">
          <h4 style="margin:0">Patients by Gender</h4>
          <canvas id="pieChart" height="160" style="margin-top:12px"></canvas>
        </div>

        <div style="height:12px"></div>

        <div class="panel small-grid">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div><strong>Patients By Division</strong><div style="color:var(--muted);font-size:12px">Top divisions</div></div>
            <div style="text-align:right"><div style="font-weight:700">3,240</div><div style="font-size:12px;color:var(--muted)">Patients this month</div></div>
          </div>
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between"><div>Cardiology</div><div>247</div></div>
            <div style="display:flex;justify-content:space-between"><div>Neurology</div><div>164</div></div>
            <div style="display:flex;justify-content:space-between"><div>Surgery</div><div>86</div></div>
          </div>
        </div>
      </aside>
    </div>

  </main>
</div>

<script>
// get sample data from backend endpoints
async function fetchStats(){
  const r = await fetch('/api/stats'); const j = await r.json();
  document.getElementById('metric-patients').innerText = j.total_patients.toLocaleString();
  document.getElementById('metric-staff').innerText = j.available_staff;
  document.getElementById('metric-cost').innerText = '$' + j.avg_cost;
  document.getElementById('metric-cars').innerText = j.available_cars;
}

// charts
function makeCharts(data){
  const trend = document.getElementById('trendChart').getContext('2d');
  new Chart(trend, {type:'bar', data:{labels:data.months, datasets:[
    {label:'Inpatients', data:data.inpatients, backgroundColor:'#7c3aed'},
    {label:'Outpatients', data:data.outpatients, backgroundColor:'#06b6d4'}
  ]}, options:{responsive:true, maintainAspectRatio:false}});

  const line = document.getElementById('lineChart').getContext('2d');
  new Chart(line, {type:'line', data:{labels:data.hours, datasets:[
    {label:'Admitted', data:data.hour_counts, borderColor:'#ff7ab6', fill:false}
  ]}, options:{responsive:true, maintainAspectRatio:false}});

  const pie = document.getElementById('pieChart').getContext('2d');
  new Chart(pie, {type:'doughnut', data:{labels:['Female','Male'], datasets:[{data:data.gender, backgroundColor:['#ff7ab6','#7c3aed']}]}, options:{responsive:true, maintainAspectRatio:false}});
}

async function init(){
  await fetchStats();
  const r = await fetch('/api/chart-data'); const j = await r.json();
  makeCharts(j);
}
init();
</script>
</body></html>
"""

@app.route("/")
def index():
    return render_template_string(TEMPLATE, year=datetime.datetime.now().year)

# sample stats endpoint (replace with DB queries)
@app.route("/api/stats")
def api_stats():
    sample = {
        "total_patients": 3256,
        "available_staff": 394,
        "avg_cost": 2536,
        "available_cars": 38
    }
    return jsonify(sample)

# sample chart data (replace with DB queries)
@app.route("/api/chart-data")
def api_chart_data():
    months = ["Oct 2019","Nov 2019","Dec 2019","Jan 2020","Feb 2020","Mar 2020"]
    inpatients = [1200, 1800, 1500, 2100, 1850, 2400]
    outpatients = [800, 1100, 900, 1150, 1250, 1600]
    hours = ["7am","9am","11am","1pm","3pm","5pm","7pm"]
    hour_counts = [20,55,40,70,60,45,30]
    gender = [60,40]  # percentages or counts
    return jsonify({
        "months": months,
        "inpatients": inpatients,
        "outpatients": outpatients,
        "hours": hours,
        "hour_counts": hour_counts,
        "gender": gender
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
