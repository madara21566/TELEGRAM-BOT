# madara_single_file.py
# Single-file MADARA Hosting Bot V11 (compact)
# Requires: aiogram, Flask, psutil, python-dotenv, requests, aiofiles
# Usage: Set .env or environment variables, then: python madara_single_file.py

import os
import sys
import time
import json
import zipfile
import shutil
import tempfile
import threading
import subprocess
import signal
import secrets
import hmac
import hashlib
from datetime import datetime, timezone

# --- third-party imports ---
try:
    from aiogram import Bot, Dispatcher, types
    from aiogram.utils import executor
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
    from flask import Flask, render_template_string, request, send_file, redirect, url_for, jsonify
    import psutil
    from dotenv import load_dotenv
except Exception as e:
    print("Missing dependencies. Install requirements: aiogram, Flask, psutil, python-dotenv, aiofiles")
    raise

load_dotenv()

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "")
PORT = int(os.getenv("PORT", "10000"))
FILEMANAGER_SECRET = os.getenv("FILEMANAGER_SECRET", "madara_secret_key_786")
AUTO_BACKUP_INTERVAL = int(os.getenv("AUTO_BACKUP_INTERVAL", "600"))  # seconds
STATE_FILE = "data/state.json"
USERS_ROOT = "data/users"
BACKUP_ROOT = "data/backups"

# Create data dirs
os.makedirs(USERS_ROOT, exist_ok=True)
os.makedirs(BACKUP_ROOT, exist_ok=True)
if not os.path.exists(STATE_FILE):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

# ---------------- Helpers ----------------
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(st):
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)

def ensure_user_state(uid):
    st = load_state()
    s = str(uid)
    st.setdefault("users", {}).setdefault(s, {}).setdefault("projects", [])
    st.setdefault("procs", {}).setdefault(s, {})
    st.setdefault("premium_users", {})  # map uid->expiry or None
    st.setdefault("redeem_codes", {})
    save_state(st)
    return st

def generate_code(days):
    st = load_state()
    code = secrets.token_hex(8)
    st.setdefault("redeem_codes", {})[code] = {"days": int(days), "created": int(time.time())}
    save_state(st)
    return code

def redeem_code(code, uid):
    st = load_state()
    codes = st.get("redeem_codes", {})
    data = codes.get(code)
    if not data:
        return False, "Invalid code"
    days = int(data["days"])
    expiry = int(time.time()) + days * 24 * 3600
    st.setdefault("premium_users", {})[str(uid)] = expiry
    del codes[code]
    save_state(st)
    return True, days

def is_premium(uid):
    st = load_state()
    pu = st.get("premium_users", {})
    s = str(uid)
    if s in pu:
        val = pu.get(s)
        if val is None:  # permanent
            return True
        if time.time() < val:
            return True
        # expired
        del pu[s]
        save_state(st)
        return False
    return False

def backup_latest():
    zips = [os.path.join(BACKUP_ROOT, f) for f in os.listdir(BACKUP_ROOT) if f.endswith(".zip")]
    if not zips: return None
    zips.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return zips[0]

def restore_from_zip(zip_path):
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp)
    # copy into current project (merge)
    for rootp, dirs, files in os.walk(tmp):
        for fn in files:
            rel = os.path.relpath(os.path.join(rootp, fn), tmp)
            dest = os.path.join(".", rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(os.path.join(rootp, fn), dest)
    shutil.rmtree(tmp, ignore_errors=True)
    return True

# ---------------- Runner ----------------
processes = {}  # (uid, proj) -> Popen

def project_dir(uid, proj):
    return os.path.join(USERS_ROOT, str(uid), proj)

def pick_entry(base):
    for rootp, dirs, files in os.walk(base):
        if "main.py" in files:
            return os.path.join(rootp, "main.py")
    for rootp, dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".py"):
                return os.path.join(rootp, f)
    return None

def start_project(uid, proj, cmd=None):
    base = project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)
    entry = pick_entry(base)
    if not entry and not cmd:
        raise RuntimeError("No entry .py found")
    if not cmd:
        cmd = f"python3 {os.path.basename(entry)}"
    # stop existing
    stop_project(uid, proj)
    # run in directory of entry
    log_path = os.path.join(base, "logs.txt")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logf = open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore")
    proc = subprocess.Popen(cmd, shell=True, cwd=os.path.dirname(entry) if entry else base,
                            stdout=logf, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    processes[(str(uid), proj)] = proc
    # save to state
    st = load_state()
    s = str(uid)
    st.setdefault("procs", {}).setdefault(s, {})[f"{proj}:entry"] = {
        "pid": proc.pid, "start": int(time.time()), "cmd": cmd
    }
    # expiry for free users
    if s not in st.get("premium_users", {}):
        st["procs"][s][f"{proj}:entry"]["expire"] = int(time.time()) + (12 * 3600)
    else:
        st["procs"][s][f"{proj}:entry"]["expire"] = None
    save_state(st)
    return proc.pid

def stop_project(uid, proj):
    key = (str(uid), proj)
    proc = processes.get(key)
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass
    processes.pop(key, None)
    # remove from state procs (keep record maybe)
    st = load_state()
    s = str(uid)
    procs = st.get("procs", {}).get(s, {})
    kname = None
    for k in list(procs.keys()):
        if k.startswith(f"{proj}:"):
            kname = k
            break
    if kname:
        del procs[kname]
        save_state(st)

def restart_project(uid, proj):
    st = load_state()
    s = str(uid)
    procs = st.get("procs", {}).get(s, {})
    meta = None
    for k, v in procs.items():
        if k.startswith(f"{proj}:"):
            meta = v
            break
    cmd = meta.get("cmd") if meta else None
    stop_project(uid, proj)
    return start_project(uid, proj, cmd)

def project_status(uid, proj):
    st = load_state()
    s = str(uid)
    procs = st.get("procs", {}).get(s, {})
    entry = None
    for k, v in procs.items():
        if k.startswith(f"{proj}:"):
            entry = v; break
    # check runtime
    running = False; pid = None
    proc = processes.get((s, proj))
    if proc and proc.poll() is None:
        running = True; pid = proc.pid
    if entry:
        start_ts = entry.get("start", 0)
        uptime = int(time.time() - start_ts) if start_ts else 0
        hr = uptime // 3600; mn = (uptime % 3600)//60; sc = uptime % 60
        last_run = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        cmd = entry.get("cmd", "python3 main.py")
        return {
            "status": "Running" if running else "Stopped",
            "pid": pid or "N/A",
            "uptime": f"{hr:02d}:{mn:02d}:{sc:02d}" if running else "N/A",
            "last_run": last_run,
            "cmd": cmd
        }
    else:
        return {
            "status": "Running" if running else "Stopped",
            "pid": pid or "N/A",
            "uptime": "N/A",
            "last_run": "Never",
            "cmd": "auto-detected"
        }

def read_logs(uid, proj, lines=500):
    path = os.path.join(project_dir(uid, proj), "logs.txt")
    if not os.path.exists(path):
        return "No logs yet."
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.readlines()
    return "".join(data[-lines:])

# ---------------- Installer (simple) ----------------
import re
def detect_imports(py_path):
    try:
        code = open(py_path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return []
    imports = re.findall(r'^\s*(?:from\s+([\w\.]+)|import\s+([\w\.]+))', code, flags=re.M)
    pkgs = set()
    for a,b in imports:
        mod = (a or b).split(".")[0]
        if mod in {"sys","os","time","json","re","asyncio","logging","subprocess","typing","datetime"}:
            continue
        if len(mod) < 2: continue
        pkgs.add(mod)
    return sorted(pkgs)

def safe_install(pkgs):
    if not pkgs: return []
    try:
        subprocess.call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--prefer-binary", *pkgs])
    except Exception:
        pass
    return pkgs

def install_requirements_if_present(base):
    req = os.path.join(base, "requirements.txt")
    if os.path.exists(req):
        subprocess.call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req])

# ---------------- Backup ----------------
def do_backup():
    ts = int(time.time())
    out = os.path.join(BACKUP_ROOT, f"backup_{ts}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for r, d, fs in os.walk("data"):
            for fn in fs:
                p = os.path.join(r, fn)
                z.write(p, os.path.relpath(p, "data"))
    # keep last 3
    items = sorted([os.path.join(BACKUP_ROOT, f) for f in os.listdir(BACKUP_ROOT) if f.endswith(".zip")],
                   key=lambda p: os.path.getmtime(p), reverse=True)
    for old in items[3:]:
        try: os.remove(old)
        except: pass
    return out

# ---------------- Monitor threads ----------------
def expire_checker_loop():
    while True:
        st = load_state()
        changed = False
        for uid, procs in list(st.get("procs", {}).items()):
            for key, meta in list(procs.items()):
                exp = meta.get("expire")
                if exp and time.time() > exp:
                    # stop process if running
                    proj = key.split(":")[0]
                    try:
                        stop_project(uid, proj)
                    except Exception:
                        pass
                    # meta removed by stop_project; ensure deletion
                    if key in st.get("procs", {}).get(str(uid), {}):
                        del st["procs"][str(uid)][key]
                        changed = True
        if changed:
            save_state(st)
        time.sleep(30)

def backup_loop():
    while True:
        try:
            path = do_backup()
            # send to owner if possible via bot (Bot may be not ready at thread start)
            try:
                if BOT:
                    BOT.send_chat_action(OWNER_ID, "upload_document")
                    with open(path, "rb") as f:
                        BOT.send_document(OWNER_ID, f, caption=f"Automatic backup: {os.path.basename(path)}")
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(AUTO_BACKUP_INTERVAL)

def restart_procs_on_boot():
    st = load_state()
    for uid, procs in st.get("procs", {}).items():
        for key, meta in procs.items():
            proj = key.split(":")[0]
            exp = meta.get("expire")
            if exp and time.time() > exp:
                continue
            cmd = meta.get("cmd")
            try:
                start_project(int(uid), proj, cmd)
            except Exception:
                pass

# ---------------- Web (Flask) ----------------
app = Flask(__name__)
app.secret_key = FILEMANAGER_SECRET

ADMIN_DASH_TEMPLATE = """
<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>MADARA Admin Dashboard</title>
<style>body{font-family:Arial;background:#f5f7fa;color:#222}.card{background:#fff;padding:12px;margin:12px;border-radius:10px}</style>
</head><body>
<h2>⚡ MADARA Hosting - Admin Dashboard</h2>
<div class="card">
Total Users: {{data.total_users}} | Projects: {{data.total_projects}} | Running: {{data.running}} | Last backup: {{data.last_backup}}
</div>
<div class="card">CPU: {{data.cpu}}% | RAM: {{data.ram}}% | Disk: {{data.disk}}%</div>
<div class="card"><h3>Running Projects</h3>
<table border=1 cellpadding=6><tr><th>User</th><th>Project</th><th>PID</th><th>Uptime</th></tr>
{% for r in data.running_list %}
<tr><td>{{r.uid}}</td><td>{{r.proj}}</td><td>{{r.pid}}</td><td>{{r.uptime}}</td></tr>
{% endfor %}
</table></div>
<script>setInterval(()=>location.reload(),5000);</script>
</body></html>
"""

def fm_token(uid, proj, ts=None):
    ts = ts or str(int(time.time())//3600)
    token = hmac.new(FILEMANAGER_SECRET.encode(), f"{uid}:{proj}:{ts}".encode(), hashlib.sha256).hexdigest()
    return token

def verify_fm(uid, proj, token):
    return token == fm_token(uid, proj)

@app.route("/")
def home():
    return "<h3>MADARA Hosting Bot — Running</h3>"

@app.route("/admin/dashboard")
def admin_dashboard():
    key = request.args.get("key")
    if str(key) != str(OWNER_ID):
        return "Unauthorized", 403
    # collect stats
    st = load_state()
    users = st.get("users", {})
    procs = st.get("procs", {})
    total_projects = sum(len(u.get("projects", [])) for u in users.values())
    running = sum(len(v) for v in procs.values())
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    running_list = []
    for uid, pdata in procs.items():
        for k, meta in pdata.items():
            running_list.append({"uid": uid, "proj": k.split(":")[0], "pid": meta.get("pid"), "uptime": format_uptime(meta.get("start"))})
    last = backup_latest()
    last_backup = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(last))) if last else "N/A"
    data = {"total_users": len(users), "total_projects": total_projects, "running": running, "cpu": cpu, "ram": ram, "disk": disk, "running_list": running_list, "last_backup": last_backup}
    return render_template_string(ADMIN_DASH_TEMPLATE, data=data)

@app.route("/fm")
def file_manager():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token")
    if not verify_fm(uid, proj, token):
        return "Unauthorized", 401
    base = project_dir(uid, proj)
    if not os.path.exists(base):
        return "Project not found", 404
    files = []
    for r, d, fs in os.walk(base):
        for f in fs:
            files.append(os.path.relpath(os.path.join(r, f), base))
    files.sort()
    # simple html
    html = "<h3>File Manager - {}/{} </h3>".format(uid, proj)
    html += "<ul>"
    for f in files:
        html += f"<li>{f} - <a href='/fm/download?uid={uid}&proj={proj}&token={token}&path={f}'>Download</a> | <a href='/fm/edit?uid={uid}&proj={proj}&token={token}&path={f}'>Edit</a> | <a href='/fm/delete?uid={uid}&proj={proj}&token={token}&path={f}'>Delete</a></li>"
    html += "</ul>"
    html += f\"\"\"<form action='/fm/upload' method='post' enctype='multipart/form-data'>
    <input type='hidden' name='uid' value='{uid}'><input type='hidden' name='proj' value='{proj}'><input type='hidden' name='token' value='{token}'>
    <input type='file' name='file'><button>Upload</button></form>\"\"\"
    return html

@app.route("/fm/upload", methods=["POST"])
def fm_upload():
    uid = request.form.get("uid"); proj = request.form.get("proj"); token = request.form.get("token")
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = project_dir(uid, proj); os.makedirs(base, exist_ok=True)
    f = request.files.get("file")
    if f:
        name = f.filename
        dest = os.path.join(base, name)
        f.save(dest)
    return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")

@app.route("/fm/download")
def fm_download():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token"); path = request.args.get("path")
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = project_dir(uid, proj); fp = os.path.join(base, path)
    if os.path.exists(fp): return send_file(fp, as_attachment=True)
    return "Not found", 404

@app.route("/fm/delete")
def fm_delete():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token"); path = request.args.get("path")
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = project_dir(uid, proj); fp = os.path.join(base, path)
    if os.path.exists(fp): os.remove(fp)
    return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")

@app.route("/fm/edit", methods=["GET","POST"])
def fm_edit():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token"); path = request.args.get("path")
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = project_dir(uid, proj); fp = os.path.join(base, path)
    if request.method == "POST":
        content = request.form.get("content","")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f: f.write(content)
        return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")
    content = ""
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8", errors="ignore") as f: content = f.read()
    return f"<h3>Edit {path}</h3><form method='post'><textarea name='content' style='width:100%;height:60vh'>{content}</textarea><br><button>Save</button></form>"

@app.route("/logs/<uid>/<proj>")
def web_logs(uid, proj):
    path = os.path.join(project_dir(uid, proj), "logs.txt")
    if os.path.exists(path): return send_file(path, as_attachment=True)
    return "No logs", 404

@app.route("/download/<uid>/<proj>")
def download_project(uid, proj):
    base = project_dir(uid, proj)
    if not os.path.exists(base): return "Not found", 404
    mem = tempfile.TemporaryFile()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for r, d, fs in os.walk(base):
            for f in fs:
                p = os.path.join(r, f)
                z.write(p, os.path.relpath(p, base))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=f"{proj}.zip")

# ---------------- Bot (Aiogram) ----------------
BOT = Bot(token=BOT_TOKEN)
DP = Dispatcher(BOT)

WELCOME = (
"👋 Welcome to MADARA Python Project Hoster!\n\n"
"Upload .py or .zip to host & run Python projects.\n\n"
"Free: 2 projects, 12h runtime each.\nPremium: 10 projects, 24/7 runtime.\n\n"
"Tap options below."
)

def main_menu_kb(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🆕 New Project", callback_data="deploy:start"),
           InlineKeyboardButton("📂 My Projects", callback_data="menu:my_projects"),
           InlineKeyboardButton("💬 Help", callback_data="menu:help"),
           InlineKeyboardButton("⭐ Premium", callback_data="menu:premium"))
    if uid == OWNER_ID and BASE_URL:
        kb.add(InlineKeyboardButton("🌐 Admin Dashboard", url=f"{BASE_URL}/admin/dashboard?key={OWNER_ID}"))
        kb.add(InlineKeyboardButton("🛠 Admin Panel", callback_data="admin:main"))
    return kb

@DP.message_handler(commands=["start"])
async def cmd_start(msg: types.Message):
    ensure_user_state(msg.from_user.id)
    await msg.answer(WELCOME, reply_markup=main_menu_kb(msg.from_user.id))

@DP.callback_query_handler(lambda c: c.data == "menu:help")
async def cb_help(c: types.CallbackQuery):
    await c.message.edit_text("Help:\n1) New Project → send name → upload .py/.zip\n2) My Projects → Run/Stop/Restart/Logs/FileManager/Delete\n3) Contact owner for premium or use /redeem", reply_markup=main_menu_kb(c.from_user.id))
    await c.answer()

@DP.callback_query_handler(lambda c: c.data == "menu:premium")
async def cb_premium(c: types.CallbackQuery):
    await c.message.edit_text("To get premium, contact owner: @MADARAXHEREE\nOr use /redeem <code> if you have a code.", reply_markup=main_menu_kb(c.from_user.id))
    await c.answer()

@DP.message_handler(commands=["generate"])
async def cmd_generate(msg: types.Message):
    if msg.from_user.id != OWNER_ID:
        return await msg.reply("Owner only")
    parts = msg.text.split()
    days = 7
    if len(parts) > 1:
        try: days = int(parts[1])
        except: days = 7
    code = generate_code(days)
    await msg.reply(f"Code `{code}` valid for {days} days", parse_mode="Markdown")

@DP.message_handler(commands=["redeem"])
async def cmd_redeem(msg: types.Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        return await msg.reply("Use: /redeem CODE")
    ok, info = redeem_code(parts[1].strip(), msg.from_user.id)
    if ok:
        await msg.reply(f"✅ Redeemed premium for {info} days.")
    else:
        await msg.reply(f"❌ {info}")

# Project flow state
awaiting_name = {}  # uid -> True when bot expects project name

@DP.callback_query_handler(lambda c: c.data == "deploy:start")
async def cb_deploy_start(c: types.CallbackQuery):
    awaiting_name[c.from_user.id] = True
    await c.message.edit_text("Send your project name (one word, no spaces):", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="menu:my_projects")))
    await c.answer()

@DP.message_handler(content_types=types.ContentType.TEXT)
async def text_handler(msg: types.Message):
    uid = msg.from_user.id
    if awaiting_name.get(uid):
        name = msg.text.strip().replace(" ", "_")
        st = ensure_user_state(uid)
        s = str(uid)
        is_prem = is_premium(uid)
        limit = 10 if is_prem else 2
        projs = st.get("users", {}).get(s, {}).get("projects", [])
        if len(projs) >= limit:
            await msg.reply("⚠️ Project limit reached. Upgrade to premium.")
            awaiting_name.pop(uid, None)
            return
        if name not in projs:
            st["users"][s]["projects"].append(name)
            save_state(st)
        os.makedirs(project_dir(uid, name), exist_ok=True)
        awaiting_name.pop(uid, None)
        await msg.reply(f"✅ Project `{name}` created. Send .py or .zip file as DOCUMENT now.", parse_mode="Markdown")
        return
    # else ignore (other text handled in admin broadcast etc. will be dynamic)
    # Note: some handlers below register dynamic handlers for admin broadcast

@DP.message_handler(content_types=types.ContentType.DOCUMENT)
async def doc_handler(msg: types.Message):
    uid = msg.from_user.id
    st = load_state()
    projs = st.get("users", {}).get(str(uid), {}).get("projects", [])
    if not projs:
        return await msg.reply("Create a project first using New Project.")
    proj = projs[-1]
    base = project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)
    m1 = await msg.reply("📦 Processing upload...")
    fpath = os.path.join(base, msg.document.file_name)
    await msg.document.download(destination_file=fpath)
    m2 = await msg.reply("🔧 Extracting...")
    # if zip flatten
    if fpath.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(fpath, "r") as z:
                z.extractall(base)
            os.remove(fpath)
            # flatten if single folder
            while True:
                items = os.listdir(base)
                if len(items) == 1 and os.path.isdir(os.path.join(base, items[0])):
                    inner = os.path.join(base, items[0])
                    for fn in os.listdir(inner):
                        shutil.move(os.path.join(inner, fn), os.path.join(base, fn))
                    shutil.rmtree(inner, ignore_errors=True)
                else:
                    break
        except Exception as e:
            return await msg.reply(f"Zip error: {e}")
    m3 = await msg.reply("⚙️ Installing requirements (if any)...")
    if os.path.exists(os.path.join(base, "requirements.txt")):
        install_requirements_if_present(base)
    else:
        # try detect first py
        pyfile = None
        for n in os.listdir(base):
            if n.endswith(".py"):
                pyfile = os.path.join(base, n); break
        if pyfile:
            pkgs = detect_imports(pyfile)
            if pkgs:
                safe_install(pkgs)
    # cleanup messages
    for mm in (m1, m2, m3):
        try: await mm.delete()
        except: pass
    await msg.reply("🎉 Upload complete! Open MY PROJECTS to manage.", reply_markup=main_menu_kb(uid))

@DP.callback_query_handler(lambda c: c.data == "menu:my_projects")
async def cb_my_projects(c: types.CallbackQuery):
    st = load_state()
    projs = st.get("users", {}).get(str(c.from_user.id), {}).get("projects", [])
    if not projs:
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="back_home"))
        await c.message.edit_text("No projects. Create a New Project.", reply_markup=kb); await c.answer(); return
    kb = InlineKeyboardMarkup(row_width=1)
    for p in projs:
        kb.add(InlineKeyboardButton(p, callback_data=f"proj:open:{p}"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="back_home"))
    await c.message.edit_text("Your Projects:", reply_markup=kb); await c.answer()

def project_kb(uid, proj):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("▶️ Run", callback_data=f"run::{proj}"),
           InlineKeyboardButton("⏹ Stop", callback_data=f"stop::{proj}"),
           InlineKeyboardButton("🔁 Restart", callback_data=f"restart::{proj}"))
    kb.add(InlineKeyboardButton("📜 Logs", callback_data=f"logs::{proj}"),
           InlineKeyboardButton("📂 File Manager", url=f"{BASE_URL}/fm?uid={uid}&proj={proj}&token="+fm_token(str(uid), proj)),
           InlineKeyboardButton("🔄 Refresh", callback_data=f"status_refresh::{proj}"))
    kb.add(InlineKeyboardButton("⬇️ Download", url=f"{BASE_URL}/download/{uid}/{proj}"),
           InlineKeyboardButton("🗑 Delete", callback_data=f"delete::{proj}"),
           InlineKeyboardButton("🔙 Back", callback_data="menu:my_projects"))
    return kb

@DP.callback_query_handler(lambda c: c.data and c.data.startswith("proj:open:"))
async def cb_proj_open(c: types.CallbackQuery):
    proj = c.data.split(":", 2)[2]
    st = project_status(c.from_user.id, proj)
    text = f"Project Status for {proj}\n\n🔹 Status: {'🟢 Running' if st['status']=='Running' else '🔴 Stopped'}\n🔹 PID: {st['pid']}\n🔹 Uptime: {st['uptime']}\n🔹 Last Run: {st['last_run']}\n🔹 Run Command: {st['cmd']}"
    await c.message.edit_text(text, reply_markup=project_kb(c.from_user.id, proj))
    await c.answer()

@DP.callback_query_handler(lambda c: c.data and c.data.startswith("status_refresh::"))
async def cb_status_refresh(c: types.CallbackQuery):
    proj = c.data.split("::", 1)[1]
    st = project_status(c.from_user.id, proj)
    text = f"Project Status for {proj}\n\n🔹 Status: {'🟢 Running' if st['status']=='Running' else '🔴 Stopped'}\n🔹 PID: {st['pid']}\n🔹 Uptime: {st['uptime']}\n🔹 Last Run: {st['last_run']}\n🔹 Run Command: {st['cmd']}"
    await c.message.edit_text(text, reply_markup=project_kb(c.from_user.id, proj))
    await c.answer("Refreshed")

@DP.callback_query_handler(lambda c: c.data and c.data.startswith("run::"))
async def cb_run(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    await c.message.answer("🚀 Launching project...")
    try:
        pid = start_project(uid, proj, None)
        st = project_status(uid, proj)
        text = f"Project Status for {proj}\n\n🔹 Status: 🟢 Running\n🔹 PID: {st['pid']}\n🔹 Uptime: {st['uptime']}\n🔹 Last Run: {st['last_run']}\n🔹 Run Command: {st['cmd']}"
        await c.message.answer(text, reply_markup=project_kb(uid, proj))
    except Exception as e:
        await c.message.answer(f"❌ Start error: {e}")
    await c.answer()

@DP.callback_query_handler(lambda c: c.data and c.data.startswith("stop::"))
async def cb_stop(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    stop_project(uid, proj)
    await c.message.answer("⛔ Stopped.")
    await c.answer()

@DP.callback_query_handler(lambda c: c.data and c.data.startswith("restart::"))
async def cb_restart(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    try:
        restart_project(uid, proj)
        await c.message.answer("🔁 Restarted.")
    except Exception as e:
        await c.message.answer(f"❌ Restart error: {e}")
    await c.answer()

@DP.callback_query_handler(lambda c: c.data and c.data.startswith("logs::"))
async def cb_logs(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    content = read_logs(uid, proj, lines=500)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    with open(tmp.name, "w", encoding="utf-8") as f: f.write(content)
    await c.message.answer_document(InputFile(tmp.name, filename=f"{proj}_logs.txt"))
    os.unlink(tmp.name)
    await c.answer()

@DP.callback_query_handler(lambda c: c.data and c.data.startswith("delete::"))
async def cb_delete(c: types.CallbackQuery):
    proj = c.data.split("::",1)[1]
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_delete::{proj}"),
           InlineKeyboardButton("❌ Cancel", callback_data=f"proj:open:{proj}"))
    await c.message.edit_text(f"⚠️ Delete `{proj}`?", reply_markup=kb)
    await c.answer()

@DP.callback_query_handler(lambda c: c.data and c.data.startswith("confirm_delete::"))
async def cb_confirm_delete(c: types.CallbackQuery):
    proj = c.data.split("::",1)[1]
    try:
        shutil.rmtree(project_dir(c.from_user.id, proj), ignore_errors=True)
        st = load_state()
        lst = st.get("users", {}).get(str(c.from_user.id), {}).get("projects", [])
        if proj in lst: lst.remove(proj)
        save_state(st)
        await c.message.edit_text(f"🗑 `{proj}` deleted.")
    except Exception as e:
        await c.message.edit_text(f"Delete failed: {e}")
    await c.answer()

@DP.callback_query_handler(lambda c: c.data == "back_home")
async def cb_back_home(c: types.CallbackQuery):
    await c.message.edit_text(WELCOME, reply_markup=main_menu_kb(c.from_user.id))
    await c.answer()

# Admin handlers
@DP.callback_query_handler(lambda c: c.data == "admin:main")
async def cb_admin_main(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return await c.answer("Owner only", show_alert=True)
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("👥 User List", callback_data="admin_user_list"),
           InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"))
    kb.add(InlineKeyboardButton("🟩 Running Scripts", callback_data="admin_running"),
           InlineKeyboardButton("📂 Backup Manager", callback_data="admin_backup"))
    kb.add(InlineKeyboardButton("🌐 Dashboard", url=f"{BASE_URL}/admin/dashboard?key={OWNER_ID}"),
           InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    await c.message.edit_text("🛠 Admin Panel", reply_markup=kb)
    await c.answer()

@DP.callback_query_handler(lambda c: c.data == "admin_user_list")
async def cb_admin_user_list(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    st = load_state()
    users = st.get("users", {})
    if not users: return await c.message.answer("No users.")
    await c.message.answer("Users:\n" + "\n".join(users.keys()))

@DP.callback_query_handler(lambda c: c.data == "admin_broadcast")
async def cb_admin_broadcast(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    await c.message.answer("Send the broadcast message (text/photo/doc):")
    # register dynamic handler
    async def _b_handler(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        st = load_state()
        users = list(st.get("users", {}).keys())
        sent = 0
        for u in users:
            try:
                if msg.text:
                    await BOT.send_message(int(u), msg.text, parse_mode="Markdown")
                elif msg.photo:
                    await BOT.send_photo(int(u), msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.document:
                    await BOT.send_document(int(u), msg.document.file_id, caption=msg.caption or "")
                sent += 1
            except Exception:
                pass
        await msg.reply(f"Broadcast sent to {sent} users.")
        # unregister this handler (aiogram v2 doesn't provide easy unregister; keep simple)
    DP.register_message_handler(_b_handler, content_types=types.ContentType.ANY)

@DP.callback_query_handler(lambda c: c.data == "admin_running")
async def cb_admin_running(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    st = load_state()
    procs = st.get("procs", {})
    lines = []
    for uid, pdata in procs.items():
        for k, meta in pdata.items():
            lines.append(f"{uid} | {k.split(':')[0]} | pid={meta.get('pid')}")
    await c.message.answer("\n".join(lines) if lines else "No running scripts.")

@DP.callback_query_handler(lambda c: c.data == "admin_backup")
async def cb_admin_backup(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    last = backup_latest()
    text = "No backups." if not last else f"Latest backup: {last}"
    kb = InlineKeyboardMarkup()
    if last:
        kb.add(InlineKeyboardButton("📤 Restore Latest", callback_data="admin_restore_latest"),
               InlineKeyboardButton("📥 Upload Backup", callback_data="admin_upload_backup"))
    await c.message.answer(text, reply_markup=kb)

@DP.callback_query_handler(lambda c: c.data == "admin_restore_latest")
async def cb_admin_restore_latest(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    last = backup_latest()
    if not last: return await c.message.answer("No backup.")
    restore_from_zip(last)
    await c.message.answer("Restored from latest backup. Restart bot if needed.")

@DP.callback_query_handler(lambda c: c.data == "admin_upload_backup")
async def cb_admin_upload_backup(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    await c.message.answer("Send backup zip now as DOCUMENT. It will be restored on receipt.")
    async def _upload_handler(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        dest = os.path.join(BACKUP_ROOT, f"uploaded_{int(time.time())}.zip")
        await msg.document.download(dest)
        restore_from_zip(dest)
        await msg.reply("Uploaded and restored. Restart bot if needed.")
    DP.register_message_handler(_upload_handler, content_types=types.ContentType.DOCUMENT)

# ---------------- Utilities ----------------
def format_uptime(start_ts):
    if not start_ts: return "N/A"
    diff = int(time.time() - start_ts)
    h = diff // 3600; m = (diff%3600)//60; s = diff%60
    return f"{h:02d}:{m:02d}:{s:02d}"

def fm_token(uid, proj):
    return hmac.new(FILEMANAGER_SECRET.encode(), f"{uid}:{proj}:{str(int(time.time())//3600)}".encode(), hashlib.sha256).hexdigest()

# ---------------- Start Threads and Bot ----------------
def start_flask():
    app.run(host="0.0.0.0", port=PORT)

def main():
    # start monitor threads
    threading.Thread(target=expire_checker_loop, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()
    # restart saved procs
    try:
        restart_procs_on_boot()
    except Exception:
        pass
    # start flask in thread
    threading.Thread(target=start_flask, daemon=True).start()
    # start aiogram polling
    executor.start_polling(DP, skip_updates=True)

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Set BOT_TOKEN in env")
        sys.exit(1)
    print("Starting MADARA single-file bot...")
    main()
