# madara_hosting_bot_full.py
# Single-file consolidated MADARA HOSTING BOT implementation
# Save as main.py and run with: python3 main.py
# Requires: aiogram, Flask, python-dotenv, psutil, requests, aiofiles
# Make sure to set your .env (BOT_TOKEN, OWNER_ID, BASE_URL, PORT, FILEMANAGER_SECRET)

import os, sys, json, time, threading, subprocess, shutil, zipfile, tempfile, hmac, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, request, send_file, abort, render_template_string, redirect
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from dotenv import load_dotenv

# ------------- Config & Setup -------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "10000"))
FILEMANAGER_SECRET = os.getenv("FILEMANAGER_SECRET", "madara_secret_key_786")
AUTO_BACKUP_INTERVAL = int(os.getenv("AUTO_BACKUP_INTERVAL", "600"))  # seconds
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=getattr(logging, LOG_LEVEL),
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("madara")

# Data directories
os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
STATE_FILE = "data/state.json"

if not os.path.exists(STATE_FILE):
    with open(STATE_FILE, "w") as f:
        json.dump({"users": {}, "procs": {}, "redeem_codes": {}}, f)

# processes map in-memory
processes = {}  # key: (uid, proj) -> subprocess.Popen

# ------------- Helpers: JSON state, users, limits, premium -------------
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.exception("load_state failed")
        return {"users": {}, "procs": {}, "redeem_codes": {}}

def save_state(st):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATE_FILE)

def ensure_user(uid):
    st = load_state()
    s = str(uid)
    if s not in st["users"]:
        st["users"][s] = {"projects": [], "premium": False, "banned": False, "backups": []}
        save_state(st)
    return st["users"][s]

def is_banned(uid):
    st = load_state()
    return st.get("users", {}).get(str(uid), {}).get("banned", False)

def is_premium(uid):
    st = load_state()
    return st.get("users", {}).get(str(uid), {}).get("premium", False)

def set_premium(uid, val=True):
    st = load_state()
    st.setdefault("users", {}).setdefault(str(uid), {})["premium"] = bool(val)
    save_state(st)

def ban_user(uid, val=True):
    st = load_state()
    st.setdefault("users", {}).setdefault(str(uid), {})["banned"] = bool(val)
    save_state(st)

def add_project_for_user(uid, proj):
    st = load_state()
    user = st.setdefault("users", {}).setdefault(str(uid), {})
    user.setdefault("projects", [])
    if proj not in user["projects"]:
        user["projects"].append(proj)
    save_state(st)

def remove_project_for_user(uid, proj):
    st = load_state()
    user = st.setdefault("users", {}).setdefault(str(uid), {})
    if proj in user.get("projects", []):
        user["projects"].remove(proj)
    # remove procs and backups references
    st.get("procs", {}).get(str(uid), {}).pop(proj, None)
    user.get("backups", {})
    save_state(st)

# Limits
FREE_MAX_PROJECTS = 2
PREMIUM_MAX_PROJECTS = 10
FREE_MAX_RUNTIME = 12 * 3600  # 12 hours
PREMIUM_MAX_RUNTIME = 0  # 0 means unlimited

# ------------- Runner: start/stop/restart/read logs/status -------------
def user_proj_dir(uid, proj):
    return os.path.join("data", "users", str(uid), proj)

def pick_entry_py(base):
    main = os.path.join(base, "main.py")
    if os.path.exists(main):
        return main
    candidates = []
    for name in os.listdir(base):
        if name.endswith(".py"):
            p = os.path.join(base, name)
            try:
                txt = open(p, "r", encoding="utf-8", errors="ignore").read()
            except Exception:
                txt = ""
            score = (1 if "__main__" in txt else 0, os.path.getsize(p))
            candidates.append((score, p))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]

def persist_proc_state(uid, proj, pid, start_ts, cmd):
    st = load_state()
    s = str(uid)
    st.setdefault("procs", {}).setdefault(s, {})[proj] = {"pid": pid, "start": start_ts, "cmd": cmd}
    save_state(st)

def remove_proc_state(uid, proj):
    st = load_state()
    s = str(uid)
    st.setdefault("procs", {}).setdefault(s, {}).pop(proj, None)
    save_state(st)

def start_script(uid, proj, cmd=None):
    base = user_proj_dir(uid, proj)
    os.makedirs(base, exist_ok=True)
    entry = pick_entry_py(base)
    if not entry and not cmd:
        raise RuntimeError("No entry .py found")
    if not cmd:
        cmd = f"python3 {entry}"
    # enforce runtime limits before starting
    if not is_premium(uid):
        # count projects and check per-project total runtime eventually
        st = load_state()
        user_projects = st.get("users", {}).get(str(uid), {}).get("projects", [])
        if len(user_projects) > FREE_MAX_PROJECTS:
            raise RuntimeError(f"Free tier allows up to {FREE_MAX_PROJECTS} projects")
    # stop existing
    stop_script(uid, proj)
    log_path = os.path.join(base, "logs.txt")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logf = open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore")
    # start process
    proc = subprocess.Popen(cmd, shell=True, cwd=base, stdout=logf, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    processes[(uid, proj)] = proc
    persist_proc_state(uid, proj, proc.pid, int(time.time()), cmd)
    logger.info(f"Started project {proj} for {uid} pid={proc.pid}")
    return proc.pid

def stop_script(uid, proj):
    key = (uid, proj)
    proc = processes.get(key)
    if proc and proc.poll() is None:
        try:
            import signal, os
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
    processes.pop(key, None)
    remove_proc_state(uid, proj)
    logger.info(f"Stopped project {proj} for {uid}")

def restart_script(uid, proj, cmd=None):
    stop_script(uid, proj)
    time.sleep(0.5)
    return start_script(uid, proj, cmd)

def get_status(uid, proj):
    key = (uid, proj)
    proc = processes.get(key)
    running = False
    pid = None
    if proc:
        if proc.poll() is None:
            running = True
            pid = proc.pid
    # fallback: check state file for pid
    st = load_state()
    entry = st.get("procs", {}).get(str(uid), {}).get(proj)
    if entry and not running:
        # process may have died but entry remains
        return {"running": False, "pid": entry.get("pid")}
    return {"running": running, "pid": pid}

def read_logs(uid, proj, lines=500):
    path = os.path.join(user_proj_dir(uid, proj), "logs.txt")
    if not os.path.exists(path):
        return "No logs yet."
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.readlines()
    return "".join(data[-lines:])

# ------------- Installer: requirements or detect imports (best-effort) -------------
def install_requirements(base):
    req = os.path.join(base, "requirements.txt")
    if not os.path.exists(req):
        return False
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req])
        return True
    except Exception as e:
        logger.exception("install_requirements failed")
        return False

def detect_imports_and_install(pyfile):
    try:
        txt = open(pyfile, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return False
    imports = set()
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("import "):
            parts = line.split()
            if len(parts) >= 2:
                imports.add(parts[1].split(".")[0])
        elif line.startswith("from "):
            parts = line.split()
            if len(parts) >= 2:
                imports.add(parts[1].split(".")[0])
    # filter builtin-ish modules
    pip_install = []
    skip = {"sys","os","time","json","re","math","subprocess","threading","shutil","pathlib","logging","typing"}
    for mod in imports:
        if mod and mod not in skip:
            pip_install.append(mod)
    if pip_install:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + list(pip_install))
            return True
        except Exception:
            logger.exception("auto pip install failed")
    return False

# ------------- Backup system -------------
def make_backup(uid, proj):
    base = user_proj_dir(uid, proj)
    if not os.path.exists(base):
        return None
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    bname = f"{uid}_{proj}_{timestamp}.zip"
    dest = os.path.join("data", "backups", bname)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(base):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, start=base)
                z.write(full, arc)
    # keep only last 3 backups per project
    st = load_state()
    user = st.setdefault("users", {}).setdefault(str(uid), {})
    user.setdefault("backups", {})
    lst = user["backups"].setdefault(proj, [])
    lst.append(dest)
    if len(lst) > 3:
        old = lst.pop(0)
        try: os.remove(old)
        except: pass
    save_state(st)
    return dest

def send_backup_to_owner(client_bot, path):
    try:
        if OWNER_ID and os.path.exists(path):
            client_bot.send_document(OWNER_ID, InputFile(path))
            logger.info(f"Sent backup {path} to owner {OWNER_ID}")
    except Exception:
        logger.exception("send backup failed")

def backup_loop(bot_client):
    while True:
        try:
            st = load_state()
            for uid_str, user in st.get("users", {}).items():
                for proj in user.get("projects", []):
                    # make backup
                    path = make_backup(uid_str, proj)
                    if path:
                        # send last backup to owner
                        try:
                            send_backup_to_owner(bot_client, path)
                        except Exception:
                            logger.exception("send to owner")
            time.sleep(AUTO_BACKUP_INTERVAL)
        except Exception:
            logger.exception("backup_loop error")
            time.sleep(10)

# ------------- Restore after restart -------------
def restore_and_start_running_projects():
    st = load_state()
    procs = st.get("procs", {})
    for uid_str, projects in procs.items():
        for proj, entry in projects.items():
            start_ts = entry.get("start", 0)
            cmd = entry.get("cmd")
            uid = int(uid_str)
            try:
                # try to start
                start_script(uid, proj, cmd)
                logger.info(f"Restored project {proj} for {uid}")
            except Exception as e:
                logger.exception("restore failed for %s %s", uid, proj)

# ------------- FileManager token (HMAC) -------------
def fm_token(uid, proj):
    secret = FILEMANAGER_SECRET.encode()
    ts = str(int(time.time()) // 3600)  # 1-hour buckets
    mac = hmac.new(secret, f"{uid}:{proj}:{ts}".encode(), hashlib.sha256).hexdigest()
    return mac

def verify_fm_token(uid, proj, token):
    secret = FILEMANAGER_SECRET.encode()
    for tdelta in (0, -1, 1):  # allow leeway
        ts = str((int(time.time()) // 3600) + tdelta)
        if hmac.new(secret, f"{uid}:{proj}:{ts}".encode(), hashlib.sha256).hexdigest() == token:
            return True
    return False

# ------------- Flask web app (minimal templates inline) -------------
app = Flask(__name__)

DASH_HTML = """
<!doctype html>
<title>Madara Hosting - Dashboard</title>
<h2>Madara Hosting Dashboard (view-only)</h2>
<p><b>Total Users:</b> {{ total_users }} &nbsp; <b>Banned:</b> {{ banned }} &nbsp; <b>Premium:</b> {{ premium }}</p>
<h3>Running Scripts</h3>
<ul>
{% for item in running %}
  <li>{{ item }}</li>
{% endfor %}
</ul>
"""

FM_HTML = """
<!doctype html>
<title>File Manager - {{ uid }} / {{ proj }}</title>
<h2>Files for {{ proj }}</h2>
<ul>
{% for f in files %}
  <li>{{ f }} - <a href="{{ url }}/download/{{ uid }}/{{ proj }}/{{ f|urlencode }}">Download</a></li>
{% endfor %}
</ul>
"""

@app.route("/")
def home():
    st = load_state()
    users = st.get("users", {})
    total = len(users)
    banned = sum(1 for u in users.values() if u.get("banned"))
    premium = sum(1 for u in users.values() if u.get("premium"))
    # running
    running = []
    procs = st.get("procs", {})
    for uid, projects in procs.items():
        for p, e in projects.items():
            running.append(f"{uid}/{p} (pid {e.get('pid')})")
    return render_template_string(DASH_HTML, total_users=total, banned=banned, premium=premium, running=running)

@app.route("/fm")
def file_manager():
    uid = request.args.get("uid")
    proj = request.args.get("proj")
    token = request.args.get("token")
    if not uid or not proj or not token:
        return "Missing", 400
    if not verify_fm_token(uid, proj, token):
        abort(403)
    base = os.path.join("data", "users", str(uid), proj)
    if not os.path.exists(base):
        return "Project not found", 404
    files = []
    for root, dirs, fs in os.walk(base):
        for f in fs:
            files.append(os.path.relpath(os.path.join(root, f), start=base))
    return render_template_string(FM_HTML, uid=uid, proj=proj, files=files, url=BASE_URL)

@app.route("/download/<uid>/<proj>/<path:fname>")
def download_file(uid, proj, fname):
    base = os.path.join("data", "users", uid, proj)
    full = os.path.join(base, fname)
    if not os.path.exists(full):
        abort(404)
    return send_file(full, as_attachment=True)

@app.route("/download_backup/<path:back>")
def download_backup(back):
    # path is relative under data/backups
    backpath = os.path.join("data", "backups", os.path.basename(back))
    if not os.path.exists(backpath):
        abort(404)
    return send_file(backpath, as_attachment=True)

# ------------- Telegram bot setup & handlers -------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Welcome and main menu
WELCOME = """👋 Welcome to MADARA HOSTING BOT!

⚡ Key Features:
• Upload and run python projects (.py / .zip)
• Web file manager & logs
• Auto setup of requirements
• Backup every 10 minutes
"""

def main_menu_kb(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🆕 New Project", callback_data="deploy:start"),
           InlineKeyboardButton("📂 My Projects", callback_data="menu:my_projects"))
    kb.add(InlineKeyboardButton("💬 Help", callback_data="help"),
           InlineKeyboardButton("⭐ Premium", callback_data="premium_info"))
    if uid == OWNER_ID:
        kb.add(InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_open"))
    return kb

@dp.message_handler(commands=["start"])
async def cmd_start(msg: types.Message):
    ensure_user(msg.from_user.id)
    await msg.reply(WELCOME, reply_markup=main_menu_kb(msg.from_user.id))

@dp.callback_query_handler(lambda c: c.data == "help")
async def help_cb(c: types.CallbackQuery):
    await c.message.answer("Send New Project → name → upload .py or .zip as DOCUMENT. Use My Projects to manage.")
    await c.answer()

# ---------------- Deploy / Project flow ----------------
@dp.callback_query_handler(lambda c: c.data == "deploy:start")
async def start_deploy(c: types.CallbackQuery):
    if is_banned(c.from_user.id):
        await c.answer("You are banned.")
        return
    st = load_state()
    user = st.setdefault("users", {}).setdefault(str(c.from_user.id), {})
    # check project count vs limits
    max_proj = PREMIUM_MAX_PROJECTS if is_premium(c.from_user.id) else FREE_MAX_PROJECTS
    current = len(user.get("projects", []))
    if current >= max_proj:
        await c.answer(f"Project limit reached for your tier ({max_proj}).")
        return
    # ask for name
    user.setdefault("awaiting_name", True)
    save_state(st)
    await c.message.edit_text("Send your project name (single word, no spaces):", reply_markup=InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 Back", callback_data="menu:my_projects")))
    await c.answer()

@dp.message_handler(content_types=types.ContentType.TEXT)
async def receive_name(msg: types.Message):
    st = load_state()
    u = st.get("users", {}).get(str(msg.from_user.id), {})
    if u.get("awaiting_name"):
        name = msg.text.strip().replace(" ", "_")
        u["awaiting_name"] = False
        u.setdefault("projects", [])
        if name not in u["projects"]:
            u["projects"].append(name)
        save_state(st)
        os.makedirs(user_proj_dir(msg.from_user.id, name), exist_ok=True)
        await msg.reply(f"Project `{name}` created. Now send your .py or .zip as DOCUMENT.", parse_mode="Markdown")
    # else ignore (other text handled elsewhere)

@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def receive_document(msg: types.Message):
    uid = msg.from_user.id
    if is_banned(uid):
        await msg.answer("You are banned.")
        return
    st = load_state()
    projs = st.get("users", {}).get(str(uid), {}).get("projects", [])
    if not projs:
        await msg.answer("Create a project first with 'New Project'.")
        return
    proj = projs[-1]
    base = user_proj_dir(uid, proj)
    os.makedirs(base, exist_ok=True)
    m1 = await msg.reply("📦 Processing Project...")
    file_path = os.path.join(base, msg.document.file_name)
    await msg.document.download(destination_file=file_path)
    m2 = await msg.reply("🔧 Extracting / Saving files...")
    # if zip -> extract
    if file_path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(file_path, "r") as z:
                z.extractall(base)
            os.remove(file_path)
            # if single inner dir, flatten
            items = os.listdir(base)
            if len(items) == 1 and os.path.isdir(os.path.join(base, items[0])):
                inner = os.path.join(base, items[0])
                for fn in os.listdir(inner):
                    shutil.move(os.path.join(inner, fn), os.path.join(base, fn))
                shutil.rmtree(inner, ignore_errors=True)
        except Exception as e:
            await msg.reply(f"Zip error: {e}")
            return
    m3 = await msg.reply("⚙️ Installing dependencies (best-effort)...")
    if os.path.exists(os.path.join(base, "requirements.txt")):
        install_requirements(base)
    else:
        # find a py file and detect imports
        py = None
        for n in os.listdir(base):
            if n.endswith(".py"):
                py = os.path.join(base, n); break
        if py:
            detect_imports_and_install(py)
    # cleanup progress messages
    for m in (m1, m2, m3):
        try: await m.delete()
        except: pass
    await msg.reply("🎉 Upload Complete!\n➡️ Go to “My Projects” to Run, Restart & Manage.\n🚀 Powered by @MADARAXHEREE")

# ------------- Project management callbacks -------------
def project_kb(uid, proj):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("▶️ Run", callback_data=f"run::{proj}"),
           InlineKeyboardButton("⏹ Stop", callback_data=f"stop::{proj}"),
           InlineKeyboardButton("🔁 Restart", callback_data=f"restart::{proj}"))
    kb.add(InlineKeyboardButton("📜 Logs", callback_data=f"logs::{proj}"),
           InlineKeyboardButton("📂 File Manager", url=f"{BASE_URL}/fm?uid={uid}&proj={proj}&token={fm_token(uid,proj)}"),
           InlineKeyboardButton("🔄 Refresh", callback_data=f"status_refresh::{proj}"))
    kb.add(InlineKeyboardButton("⬇️ Download", url=f"{BASE_URL}/download/{uid}/{proj}"),
           InlineKeyboardButton("🗑 Delete", callback_data=f"delete::{proj}"),
           InlineKeyboardButton("🔙 Back", callback_data="menu:my_projects"))
    return kb

def status_text(uid, proj):
    st = load_state()
    procs = st.get("procs", {}).get(str(uid), {})
    entry = procs.get(proj)
    s = get_status(uid, proj)
    running = s["running"]
    pid = s["pid"] or "N/A"
    if entry:
        start_ts = entry.get("start", 0)
        uptime_secs = int(time.time() - start_ts) if start_ts else 0
        h = uptime_secs // 3600; m = (uptime_secs % 3600) // 60; s_ = uptime_secs % 60
        last_run = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        cmd = entry.get("cmd", "python3 main.py")
        return (f"Project Status for {proj}\n\n"
                f"🔹 Status: {'🟢 Running' if running else '🔴 Stopped'}\n"
                f"🔹 PID: {pid}\n"
                f"🔹 Uptime: {h:02d}:{m:02d}:{s_:02d}\n"
                f"🔹 Last Run: {last_run}\n"
                f"🔹 Run Command: {cmd}")
    else:
        return (f"Project Status for {proj}\n\n"
                f"🔹 Status: {'🟢 Running' if running else '🔴 Stopped'}\n"
                f"🔹 PID: {pid if running else 'N/A'}\n"
                f"🔹 Uptime: {'N/A' if not running else '00:00:00'}\n"
                f"🔹 Last Run: Never\n"
                f"🔹 Run Command: auto-detected")

@dp.callback_query_handler(lambda c: c.data == "menu:my_projects")
async def my_projects(c: types.CallbackQuery):
    st = load_state()
    projs = st.get("users", {}).get(str(c.from_user.id), {}).get("projects", [])
    kb = InlineKeyboardMarkup(row_width=1)
    for p in projs:
        kb.add(InlineKeyboardButton(p, callback_data=f"proj:open:{p}"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="back_home"))
    await c.message.edit_text("Your Projects:", reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("proj:open:"))
async def open_proj(c: types.CallbackQuery):
    proj = c.data.split(":",2)[2]
    await c.message.edit_text(status_text(c.from_user.id, proj), reply_markup=project_kb(c.from_user.id, proj))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("status_refresh::"))
async def refresh(c: types.CallbackQuery):
    proj = c.data.split("::",1)[1]
    await c.message.edit_text(status_text(c.from_user.id, proj), reply_markup=project_kb(c.from_user.id, proj))
    await c.answer("Refreshed")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("run::"))
async def run_cb(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    await c.message.answer("⚙️ Setting up environment...\n📦 Checking required libraries...\n🚀 Launching project...")
    try:
        pid = start_script(uid, proj, None)
        await c.message.answer(status_text(uid, proj), reply_markup=project_kb(uid, proj))
    except Exception as e:
        await c.message.answer(f"Start error: {e}")
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("stop::"))
async def stop_cb(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    stop_script(uid, proj)
    await c.message.answer("⛔ Stopped.")
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("restart::"))
async def restart_cb(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    try:
        restart_script(uid, proj, None)
        await c.message.answer("🔁 Restarted successfully.")
    except Exception as e:
        await c.message.answer(f"Restart failed: {e}")
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("logs::"))
async def logs_cb(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    content = read_logs(uid, proj, lines=500)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    with open(tmp.name, "w", encoding="utf-8") as f:
        f.write(content)
    await c.message.answer_document(InputFile(tmp.name, filename=f"{proj}_logs.txt"))
    try: os.unlink(tmp.name)
    except: pass
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("delete::"))
async def delete_cb(c: types.CallbackQuery):
    proj = c.data.split("::",1)[1]
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("✅ Confirm Delete", callback_data=f"confirm_delete::{proj}"),
           InlineKeyboardButton("❌ Cancel", callback_data=f"proj:open:{proj}"))
    await c.message.edit_text(f"⚠️ Are you sure you want to permanently delete project `{proj}`?", parse_mode="Markdown", reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("confirm_delete::"))
async def confirm_delete(c: types.CallbackQuery):
    proj = c.data.split("::",1)[1]
    base = user_proj_dir(c.from_user.id, proj)
    try:
        stop_script(c.from_user.id, proj)
        shutil.rmtree(base, ignore_errors=True)
        remove_project_for_user(c.from_user.id, proj)
        await c.message.edit_text(f"🗑 Project `{proj}` deleted successfully.", parse_mode="Markdown")
    except Exception as e:
        await c.message.edit_text(f"Delete failed: {e}")
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "back_home")
async def back_home(c: types.CallbackQuery):
    await c.message.edit_text(WELCOME, reply_markup=main_menu_kb(c.from_user.id))
    await c.answer()

# ------------- Admin panel & handlers (owner-only) -------------
def admin_panel_kb():
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("👥 User List", callback_data="admin_user_list"),
           InlineKeyboardButton("📂 Backup History", callback_data="admin_backup_history"),
           InlineKeyboardButton("🟩 Running Scripts", callback_data="admin_running"))
    kb.add(InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban_user"),
           InlineKeyboardButton("✅ Unban User", callback_data="admin_unban_user"),
           InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="back_home"))
    return kb

@dp.callback_query_handler(lambda c: c.data == "admin_open")
async def open_admin(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        await c.answer("Unauthorized"); return
    await c.message.edit_text("🛠 Admin Control Panel", reply_markup=admin_panel_kb())
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_user_list")
async def admin_user_list(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return
    st = load_state()
    users = st.get("users", {})
    text = "👥 Registered Users:\n\n"
    for uid, info in users.items():
        text += f"- {uid} | projects: {len(info.get('projects',[]))} | premium: {info.get('premium')} | banned: {info.get('banned')}\n"
    await c.message.edit_text(text, reply_markup=admin_panel_kb())

@dp.callback_query_handler(lambda c: c.data == "admin_backup_history")
async def admin_backup_history(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return
    st = load_state()
    s = "📂 Backup History (last 3 per project):\n\n"
    for uid, info in st.get("users", {}).items():
        s += f"User {uid}:\n"
        for proj, backs in info.get("backups", {}).items():
            s += f"  - {proj}:\n"
            for b in backs:
                s += f"     • {os.path.basename(b)}\n"
    await c.message.edit_text(s, reply_markup=admin_panel_kb())

@dp.callback_query_handler(lambda c: c.data == "admin_running")
async def admin_running(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return
    st = load_state()
    running = []
    for uid, projs in st.get("procs", {}).items():
        for p, e in projs.items():
            running.append(f"{uid}/{p} pid={e.get('pid')}")
    if not running:
        txt = "No running scripts."
    else:
        txt = "Running:\n" + "\n".join(running)
    await c.message.edit_text(txt, reply_markup=admin_panel_kb())

@dp.callback_query_handler(lambda c: c.data == "admin_ban_user")
async def admin_ban_user(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return
    await c.message.answer("Send user ID to ban:")
    # register one-shot handler
    @dp.message_handler()
    async def receive_ban(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        try:
            uid = int(msg.text.strip())
            ban_user(uid, True)
            await msg.reply(f"Banned {uid}")
        except Exception as e:
            await msg.reply(f"Error: {e}")

@dp.callback_query_handler(lambda c: c.data == "admin_unban_user")
async def admin_unban_user(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return
    await c.message.answer("Send user ID to unban:")
    @dp.message_handler()
    async def receive_unban(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        try:
            uid = int(msg.text.strip())
            ban_user(uid, False)
            await msg.reply(f"Unbanned {uid}")
        except Exception as e:
            await msg.reply(f"Error: {e}")

@dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return
    await c.message.answer("Send broadcast message now (will send to all users):")
    @dp.message_handler()
    async def receive_broadcast(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        st = load_state()
        users = st.get("users", {})
        count = 0
        for uid in list(users.keys()):
            try:
                bot.send_message(int(uid), msg.text)
                count += 1
            except Exception:
                pass
        await msg.reply(f"Broadcast sent to {count} users")

# ------------- Redeem code system -------------
@dp.message_handler(commands=["generate"])
async def cmd_generate(msg: types.Message):
    # owner only
    if msg.from_user.id != OWNER_ID:
        await msg.reply("Unauthorized")
        return
    # usage: /generate 7d (or 30d or 1d)
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.reply("Usage: /generate <days> (e.g. /generate 7)")
        return
    days = int(parts[1])
    code = hashlib.sha256(f"{time.time()}:{os.urandom(8)}".encode()).hexdigest()[:12]
    st = load_state()
    st.setdefault("redeem_codes", {})[code] = {"days": days, "created": int(time.time()), "used": False}
    save_state(st)
    await msg.reply(f"Code: `{code}` for {days} days", parse_mode="Markdown")

@dp.message_handler(commands=["redeem"])
async def cmd_redeem(msg: types.Message):
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.reply("Usage: /redeem <code>")
        return
    code = parts[1].strip()
    st = load_state()
    info = st.get("redeem_codes", {}).get(code)
    if not info:
        await msg.reply("Invalid code")
        return
    if info.get("used"):
        await msg.reply("Code already used")
        return
    # mark premium for user
    set_premium(msg.from_user.id, True)
    info["used"] = True
    info["redeemed_by"] = msg.from_user.id
    info["redeemed_at"] = int(time.time())
    save_state(st)
    await msg.reply("Redeemed! You are now premium. Contact owner for assistance.")

# ------------- Other utility handlers -------------
@dp.message_handler(commands=["me"])
async def cmd_me(msg: types.Message):
    uid = msg.from_user.id
    st = load_state()
    user = st.get("users", {}).get(str(uid), {})
    await msg.reply(f"User: {uid}\nProjects: {len(user.get('projects',[]))}\nPremium: {user.get('premium')}\nBanned: {user.get('banned')}")

# ------------- Startup threads & main -------------
def run_flask():
    logger.info(f"Starting Flask server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)

def start_services():
    # restore prior procs
    restore_and_start_running_projects()
    # start backup thread
    t = threading.Thread(target=backup_loop, args=(bot,), daemon=True)
    t.start()
    # Flask
    f = threading.Thread(target=run_flask, daemon=True)
    f.start()
    # Polling for aiogram
    logger.info("Telegram bot starting polling...")
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    logger.info("MADARA HOSTING BOT starting...")
    start_services()
