#!/usr/bin/env python3
"""
MADARA HOSTING BOT - single-file combined implementation (V11 single-file)
Features:
- Telegram bot (aiogram) + Flask web panel in same process (thread)
- Upload .py/.zip projects, auto-flatten zip, auto-install requirements
- Run/Stop/Restart scripts, logs, file manager link via HMAC token
- Free (2 projects, 12h runtime) / Premium (10 projects, 24/7) limits
- Auto-backup every 10 minutes, keep last 3 backups, send latest backup to owner
- Restore latest backup automatically on boot, manual restore via admin
- Redeem code system (/generate by owner, /redeem by user)
- Admin panel inside Telegram + web dashboard (view only)
- Uses data/state.json for persistent state
Run: python madara_hosting_bot.py
"""

import os, sys, time, json, shutil, zipfile, tempfile, threading, subprocess, signal, hmac, hashlib, secrets, logging
from datetime import datetime, timezone
from functools import partial

# ===== env and logging =====
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "10000"))
FILEMANAGER_SECRET = os.getenv("FILEMANAGER_SECRET", "madara_secret_key_786")
AUTO_BACKUP_INTERVAL = int(os.getenv("AUTO_BACKUP_INTERVAL", "600"))  # seconds
FREE_PROJECT_LIMIT = 2
PREMIUM_PROJECT_LIMIT = 10
FREE_RUNTIME_SECONDS = 12 * 3600  # 12 hours

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN not set in .env")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ===== storage dirs =====
os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    with open("data/state.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

STATE_FILE = "data/state.json"

# ===== helpers =====
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(st):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)

def ensure_user(uid):
    st = load_state()
    su = str(uid)
    st.setdefault("users", {}).setdefault(su, {}).setdefault("projects", [])
    st.setdefault("procs", {}).setdefault(su, {})
    st.setdefault("premium_users", st.get("premium_users", {}))
    st.setdefault("redeem_codes", st.get("redeem_codes", {}))
    save_state(st)
    return st

def is_premium(uid):
    st = load_state()
    pu = st.get("premium_users", {})
    su = str(uid)
    if su in pu:
        exp = pu[su]
        if exp is None: return True
        if time.time() < exp: return True
        # expired
        del pu[su]
        save_state(st)
        return False
    return False

def generate_redeem_code(days):
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
    su = str(uid)
    st.setdefault("premium_users", {})[su] = int(time.time()) + days * 24 * 3600
    del codes[code]
    save_state(st)
    return True, days

def backup_latest_path():
    root = "data/backups"
    if not os.path.exists(root): return None
    zips = [os.path.join(root, f) for f in os.listdir(root) if f.endswith(".zip")]
    if not zips: return None
    zips.sort(key=os.path.getmtime, reverse=True)
    return zips[0]

def restore_from_zip(zip_path):
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp)
    # copy into current project root (merge)
    for r,d,files in os.walk(tmp):
        for fn in files:
            src = os.path.join(r,fn)
            rel = os.path.relpath(src, tmp)
            dst = os.path.join(".", rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    shutil.rmtree(tmp, ignore_errors=True)
    return True

# ===== installer (simple import detection) =====
import re
def detect_imports(py_path):
    try:
        txt = open(py_path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return []
    imports = re.findall(r'^\s*(?:from\s+([\w\.]+)|import\s+([\w\.]+))', txt, flags=re.M)
    pkgs = set()
    stds = {"os","sys","time","json","re","logging","subprocess","math","typing","datetime","pathlib"}
    for a,b in imports:
        mod = (a or b).split(".")[0]
        if mod and mod not in stds and len(mod) > 1:
            pkgs.add(mod)
    return sorted(pkgs)

def install_packages(pkgs):
    if not pkgs: return
    logging.info("Installing packages: %s", pkgs)
    subprocess.call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--prefer-binary", *pkgs])

def install_requirements_if_present(base):
    req = os.path.join(base, "requirements.txt")
    if os.path.exists(req):
        subprocess.call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req])

# ===== runner =====
processes = {}  # (uid,proj) -> Popen

def project_dir(uid, proj):
    return os.path.join("data", "users", str(uid), proj)

def pick_entry_py(base):
    for root, dirs, files in os.walk(base):
        if "main.py" in files:
            return os.path.join(root, "main.py")
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".py"):
                return os.path.join(root, f)
    return None

def start_script(uid, proj, cmd=None):
    base = project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)
    entry = pick_entry_py(base)
    if not entry and not cmd:
        raise RuntimeError("No entry .py found")
    if not cmd:
        cmd = f"{sys.executable} {os.path.basename(entry)}"
    # stop if exists
    stop_script(uid, proj)
    log_path = os.path.join(base, "logs.txt")
    logf = open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore")
    proc = subprocess.Popen(cmd, shell=True, cwd=os.path.dirname(entry) if entry else base,
                            stdout=logf, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    processes[(str(uid), proj)] = proc
    st = load_state()
    su = str(uid)
    st.setdefault("procs", {}).setdefault(su, {})[f"{proj}:entry"] = {
        "pid": proc.pid, "start": int(time.time()), "cmd": cmd
    }
    # expiration for free users
    if su not in st.get("premium_users", {}):
        st["procs"][su][f"{proj}:entry"]["expire"] = int(time.time()) + FREE_RUNTIME_SECONDS
    else:
        st["procs"][su][f"{proj}:entry"]["expire"] = None
    save_state(st)
    logging.info("Started %s/%s pid=%s", uid, proj, proc.pid)
    return proc.pid

def stop_script(uid, proj):
    key = (str(uid), proj)
    proc = processes.get(key)
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass
    processes.pop(key, None)
    st = load_state(); su = str(uid)
    if st.get("procs", {}).get(su, {}).get(f"{proj}:entry"):
        try:
            del st["procs"][su][f"{proj}:entry"]
            save_state(st)
        except Exception:
            pass
    logging.info("Stopped %s/%s", uid, proj)

def restart_script(uid, proj, cmd=None):
    stop_script(uid, proj)
    time.sleep(0.5)
    return start_script(uid, proj, cmd)

def get_status(uid, proj):
    key = (str(uid), proj)
    proc = processes.get(key)
    if not proc:
        return {"running": False, "pid": None}
    running = proc.poll() is None
    return {"running": running, "pid": proc.pid if running else None}

def read_logs(uid, proj, lines=500):
    p = os.path.join(project_dir(uid, proj), "logs.txt")
    if not os.path.exists(p): return "No logs yet."
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        data = f.readlines()
    return "".join(data[-lines:])

# ===== backup =====
def create_backup():
    root = "data"
    out_root = "data/backups"
    os.makedirs(out_root, exist_ok=True)
    ts = int(time.time())
    out = os.path.join(out_root, f"backup_{ts}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for r,d,files in os.walk("data"):
            for fn in files:
                p = os.path.join(r,fn)
                z.write(p, os.path.relpath(p, "data"))
    # keep last 3
    items = sorted([os.path.join(out_root,f) for f in os.listdir(out_root) if f.endswith(".zip")],
                   key=os.path.getmtime, reverse=True)
    for old in items[3:]:
        try: os.remove(old)
        except Exception: pass
    return out

# ===== monitor (expire + restart on boot) =====
def check_and_stop_expired():
    st = load_state()
    changed = False
    for su, procs in list(st.get("procs", {}).items()):
        for key, meta in list(procs.items()):
            exp = meta.get("expire")
            if exp and time.time() > exp:
                # kill if running
                pid = meta.get("pid")
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception:
                    pass
                del procs[key]
                changed = True
    if changed:
        save_state(st)

def restore_procs_on_boot():
    st = load_state()
    for su, procs in st.get("procs", {}).items():
        for key, meta in procs.items():
            proj = key.split(":")[0]
            exp = meta.get("expire")
            if exp and time.time() > exp:
                continue
            try:
                start_script(int(su), proj, meta.get("cmd"))
            except Exception:
                pass

# ===== web (Flask) =====
from flask import Flask, request, render_template_string, redirect, url_for, send_file, abort, jsonify
app = Flask(__name__)
app.secret_key = FILEMANAGER_SECRET

def fm_token(uid, proj, ts=None):
    secret = (FILEMANAGER_SECRET or "madara_secret_key_786").encode()
    ts = ts or str(int(time.time())//3600)
    msg = f"{uid}:{proj}:{ts}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

def verify_fm(uid, proj, token):
    return token == fm_token(uid, proj)

@app.route("/")
def home():
    return "<h3>🤖 MADARA Hosting Bot is Running</h3>"

# file manager: list, upload, download, edit, delete
@app.route("/fm")
def fm_index():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token")
    if not (uid and proj and token): return "Missing params", 400
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = os.path.join("data","users",uid,proj)
    if not os.path.exists(base): return "Project not found", 404
    files=[]
    for r,d,fs in os.walk(base):
        for f in fs:
            files.append(os.path.relpath(os.path.join(r,f), base))
    files.sort()
    html = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
    <h2>File Manager - {{proj}}</h2>
    <form action="/fm/upload" method="post" enctype="multipart/form-data">
      <input type="hidden" name="uid" value="{{uid}}">
      <input type="hidden" name="proj" value="{{proj}}">
      <input type="hidden" name="token" value="{{token}}">
      <input type="file" name="file" required>
      <button>Upload</button>
    </form>
    <hr>
    <ul>
    {% for f in files %}
      <li>{{f}} - <a href="/fm/download?uid={{uid}}&proj={{proj}}&token={{token}}&path={{f}}">Download</a> |
        <a href="/fm/edit?uid={{uid}}&proj={{proj}}&token={{token}}&path={{f}}">Edit</a> |
        <a href="/fm/delete?uid={{uid}}&proj={{proj}}&token={{token}}&path={{f}}">Delete</a></li>
    {% endfor %}
    </ul>
    """
    return render_template_string(html, uid=uid, proj=proj, token=token, files=files)

@app.route("/fm/upload", methods=["POST"])
def fm_upload():
    uid = request.form.get("uid"); proj = request.form.get("proj"); token = request.form.get("token")
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = os.path.join("data","users",uid,proj)
    os.makedirs(base, exist_ok=True)
    f = request.files.get("file")
    if f:
        fn = f.filename
        dst = os.path.join(base, fn)
        f.save(dst)
    return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")

@app.route("/fm/download")
def fm_download():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token"); path = request.args.get("path")
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = os.path.join("data","users",uid,proj); fp = os.path.join(base, path)
    if not os.path.exists(fp): return "Not found", 404
    return send_file(fp, as_attachment=True)

@app.route("/fm/delete")
def fm_delete():
    uid = request.args.get("uid"); proj = request.args.get("proj"); token = request.args.get("token"); path = request.args.get("path")
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = os.path.join("data","users",uid,proj); fp = os.path.join(base, path)
    if os.path.exists(fp):
        os.remove(fp)
    return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")

@app.route("/fm/edit", methods=["GET","POST"])
def fm_edit():
    uid = request.values.get("uid"); proj = request.values.get("proj"); token = request.values.get("token"); path = request.values.get("path")
    if not verify_fm(uid, proj, token): return "Unauthorized", 401
    base = os.path.join("data","users",uid,proj); fp = os.path.join(base, path)
    if request.method == "POST":
        text = request.form.get("content","")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)
        return redirect(f"/fm?uid={uid}&proj={proj}&token={token}")
    content = ""
    if os.path.exists(fp):
        content = open(fp, "r", encoding="utf-8", errors="ignore").read()
    html = """<h3>Edit {{path}}</h3>
    <form method="post"><textarea name="content" style="width:100%;height:60vh">{{content}}</textarea><br><button>Save</button></form>"""
    return render_template_string(html, path=path, content=content)

@app.route("/logs/<uid>/<proj>")
def web_logs(uid, proj):
    p = os.path.join("data","users",uid,proj,"logs.txt")
    if not os.path.exists(p): return "No logs", 404
    return send_file(p, as_attachment=True)

@app.route("/download/<uid>/<proj>")
def download_project(uid, proj):
    base = os.path.join("data","users",uid,proj)
    if not os.path.exists(base): return "Not found", 404
    mem = tempfile.SpooledTemporaryFile()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for r,d,files in os.walk(base):
            for fn in files:
                p = os.path.join(r,fn)
                z.write(p, os.path.relpath(p, base))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=f"{proj}.zip")

# admin dashboard view
@app.route("/admin/dashboard")
def admin_dashboard():
    key = request.args.get("key")
    if str(key) != str(OWNER_ID):
        return "Unauthorized", 403
    st = load_state()
    users = st.get("users", {})
    procs = st.get("procs", {})
    total_projects = sum(len(u.get("projects", [])) for u in users.values())
    running = sum(len(v) for v in procs.values())
    cpu = None
    ram = None
    disk = None
    try:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except Exception:
        cpu = ram = disk = "n/a"
    last_b = backup_latest_path()
    html = f"""<h2>MADARA Admin Dashboard</h2>
    <div>Total users: {len(users)} | Total projects: {total_projects} | Running: {running} | Last backup: {last_b}</div>
    <div>CPU: {cpu} | RAM: {ram} | Disk: {disk}</div>"""
    return html

# ===== telegram bot (aiogram v2) =====
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# keyboard generator
def main_menu_kb(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🆕 New Project", callback_data="deploy:start"),
           types.InlineKeyboardButton("📂 My Projects", callback_data="menu:my_projects"),
           types.InlineKeyboardButton("💬 Help", callback_data="menu:help"),
           types.InlineKeyboardButton("⭐ Premium", callback_data="menu:premium"))
    if uid == OWNER_ID and BASE_URL:
        kb.add(types.InlineKeyboardButton("🌐 Admin Dashboard", url=f"{BASE_URL}/admin/dashboard?key={OWNER_ID}"))
        kb.add(types.InlineKeyboardButton("🛠 Admin Panel", callback_data="admin:main"))
    return kb

WELCOME_TEXT = """👋 Welcome to MADARA Hosting Bot!
Upload .py or .zip, run scripts, backups, admin panel and more.
"""

# Register handlers
@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message):
    ensure_user(m.from_user.id)
    await m.answer(WELCOME_TEXT, reply_markup=main_menu_kb(m.from_user.id))

@dp.callback_query_handler(lambda c: c.data == "menu:help")
async def cb_help(c: types.CallbackQuery):
    txt = ("Help:\n1) New Project -> provide name -> upload .py or .zip\n"
           "2) My Projects -> manage (Run/Stop/Restart/Logs/File Manager/Delete)\n"
           "3) Contact owner for premium or use /redeem code")
    await c.message.edit_text(txt, reply_markup=main_menu_kb(c.from_user.id))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "menu:premium")
async def cb_premium(c: types.CallbackQuery):
    await c.message.edit_text("To get premium: contact owner or use /redeem <code> if you have a code.", reply_markup=main_menu_kb(c.from_user.id))
    await c.answer()

# Redeem and generate
@dp.message_handler(commands=["redeem"])
async def cmd_redeem(m: types.Message):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        return await m.reply("Usage: /redeem CODE")
    code = parts[1].strip()
    ok, info = redeem_code(code, m.from_user.id)
    if ok:
        await m.reply(f"✅ Premium activated for {info} days.")
    else:
        await m.reply(f"❌ {info}")

@dp.message_handler(commands=["generate"])
async def cmd_generate(m: types.Message):
    if m.from_user.id != OWNER_ID:
        return await m.reply("Owner only")
    parts = m.text.split()
    days = 7
    if len(parts) > 1:
        try: days = int(parts[1])
        except: days = 7
    c = generate_redeem_code(days)
    await m.reply(f"Code: `{c}` valid for {days} days", parse_mode="Markdown")

# --- project handlers: deployment and management
@dp.callback_query_handler(lambda c: c.data == "deploy:start")
async def cb_deploy_start(c: types.CallbackQuery):
    st = ensure_user(c.from_user.id)
    st.setdefault("awaiting_name", {})[str(c.from_user.id)] = True
    save_state(st)
    await c.message.edit_text("Send your project name (single word, no spaces):", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="menu:my_projects")))
    await c.answer()

@dp.message_handler(content_types=types.ContentType.TEXT)
async def msg_receive_name(m: types.Message):
    st = load_state()
    awaiting = st.get("awaiting_name", {})
    if awaiting.get(str(m.from_user.id)):
        name = m.text.strip().replace(" ", "_")
        awaiting.pop(str(m.from_user.id), None)
        st.setdefault("users", {}).setdefault(str(m.from_user.id), {}).setdefault("projects", [])
        su = str(m.from_user.id)
        limit = PREMIUM_PROJECT_LIMIT if is_premium(m.from_user.id) else FREE_PROJECT_LIMIT
        if len(st["users"][su]["projects"]) >= limit:
            save_state(st)
            return await m.reply(f"⚠️ Project limit reached. Free={FREE_PROJECT_LIMIT}, Premium={PREMIUM_PROJECT_LIMIT}.")
        if name not in st["users"][su]["projects"]:
            st["users"][su]["projects"].append(name)
        save_state(st)
        os.makedirs(project_dir(m.from_user.id, name), exist_ok=True)
        await m.reply(f"✅ Project `{name}` created. Now send the .py or .zip as a document.", parse_mode="Markdown")

# helper: extract zip flatten
def _extract_zip(zip_path, dest):
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest)
    while True:
        items = os.listdir(dest)
        if len(items) == 1 and os.path.isdir(os.path.join(dest, items[0])):
            inner = os.path.join(dest, items[0])
            for fn in os.listdir(inner):
                shutil.move(os.path.join(inner, fn), os.path.join(dest, fn))
            shutil.rmtree(inner, ignore_errors=True)
        else:
            break

@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def msg_receive_doc(m: types.Message):
    uid = m.from_user.id
    st = load_state()
    projs = st.get("users", {}).get(str(uid), {}).get("projects", [])
    if not projs:
        return await m.reply("Create a project first via New Project.")
    proj = projs[-1]
    base = project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)
    info_msg = await m.reply("📦 Processing upload...")
    file_name = m.document.file_name
    dst = os.path.join(base, file_name)
    await m.document.download(destination_file=dst)
    try:
        if dst.lower().endswith(".zip"):
            await bot.send_message(uid, "🔧 Extracting zip...")
            _extract_zip(dst, base)
            os.remove(dst)
    except Exception as e:
        await bot.send_message(uid, f"Zip error: {e}")
        return
    # install requirements
    await bot.send_message(uid, "⚙️ Installing dependencies (if any)...")
    if os.path.exists(os.path.join(base, "requirements.txt")):
        install_requirements_if_present(base)
    else:
        # pick any py and detect
        p = pick_entry_py(base)
        if p:
            pkgs = detect_imports(p)
            if pkgs:
                install_packages(pkgs)
    try:
        await bot.delete_message(uid, info_msg.message_id)
    except Exception:
        pass
    await bot.send_message(uid, "🎉 Upload complete! Use My Projects to manage.")

# build project keyboard
def project_kb(uid, proj):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(types.InlineKeyboardButton("▶️ Run", callback_data=f"run::{proj}"),
           types.InlineKeyboardButton("⏹ Stop", callback_data=f"stop::{proj}"),
           types.InlineKeyboardButton("🔁 Restart", callback_data=f"restart::{proj}"))
    kb.add(types.InlineKeyboardButton("📜 Logs", callback_data=f"logs::{proj}"),
           types.InlineKeyboardButton("📂 File Manager", url=f"{BASE_URL}/fm?uid={uid}&proj={proj}&token={fm_token(uid,proj)}"),
           types.InlineKeyboardButton("🔄 Refresh", callback_data=f"status_refresh::{proj}"))
    kb.add(types.InlineKeyboardButton("⬇️ Download", url=f"{BASE_URL}/download/{uid}/{proj}"),
           types.InlineKeyboardButton("🗑 Delete", callback_data=f"delete::{proj}"),
           types.InlineKeyboardButton("🔙 Back", callback_data="menu:my_projects"))
    return kb

def status_text(uid, proj):
    st = load_state()
    procs = st.get("procs", {}).get(str(uid), {})
    entry = None
    for k,v in procs.items():
        if k.startswith(f"{proj}:"):
            entry = v; break
    s = get_status(uid, proj)
    running = s["running"]
    pid = s["pid"] or "N/A"
    if entry:
        start_ts = entry.get("start", 0)
        uptime = int(time.time() - start_ts) if start_ts else 0
        h = uptime // 3600; m = (uptime % 3600) // 60; s2 = uptime % 60
        last_run = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        cmd = entry.get("cmd", "auto")
        return (f"Project Status for {proj}\n\n"
                f"🔹 Status: {'🟢 Running' if running else '🔴 Stopped'}\n"
                f"🔹 PID: {pid}\n"
                f"🔹 Uptime: {h:02d}:{m:02d}:{s2:02d}\n"
                f"🔹 Last Run: {last_run}\n"
                f"🔹 Run Command: {cmd}")
    return (f"Project Status for {proj}\n\n"
            f"🔹 Status: {'🟢 Running' if running else '🔴 Stopped'}\n"
            f"🔹 PID: {'N/A' if not running else pid}\n"
            f"🔹 Uptime: {'N/A' if not running else '00:00:00'}\n"
            f"🔹 Last Run: Never\n"
            f"🔹 Run Command: auto-detected")

@dp.callback_query_handler(lambda c: c.data == "menu:my_projects")
async def cb_my_projects(c: types.CallbackQuery):
    st = load_state()
    projs = st.get("users", {}).get(str(c.from_user.id), {}).get("projects", [])
    kb = types.InlineKeyboardMarkup(row_width=1)
    for p in projs:
        kb.add(types.InlineKeyboardButton(p, callback_data=f"proj:open:{p}"))
    kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="back_home"))
    await c.message.edit_text("Your Projects:", reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("proj:open:"))
async def cb_proj_open(c: types.CallbackQuery):
    proj = c.data.split(":",2)[2]
    await c.message.edit_text(status_text(c.from_user.id, proj), reply_markup=project_kb(c.from_user.id, proj))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("status_refresh::"))
async def cb_refresh(c: types.CallbackQuery):
    proj = c.data.split("::",1)[1]
    await c.message.edit_text(status_text(c.from_user.id, proj), reply_markup=project_kb(c.from_user.id, proj))
    await c.answer("Refreshed")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("run::"))
async def cb_run(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    # check project exists
    try:
        pid = start_script(uid, proj, None)
        await c.message.answer(status_text(uid, proj), reply_markup=project_kb(uid, proj))
    except Exception as e:
        await c.message.answer(f"Start error: {e}")
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("stop::"))
async def cb_stop(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    stop_script(uid, proj)
    await c.message.answer("⛔ Stopped.")
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("restart::"))
async def cb_restart(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    restart_script(uid, proj, None)
    await c.message.answer("🔁 Restarted.")
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("logs::"))
async def cb_logs(c: types.CallbackQuery):
    uid = c.from_user.id; proj = c.data.split("::",1)[1]
    txt = read_logs(uid, proj, lines=500)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    with open(tmp.name, "w", encoding="utf-8") as f: f.write(txt)
    await bot.send_document(uid, open(tmp.name, "rb"))
    try: os.unlink(tmp.name)
    except: pass
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("delete::"))
async def cb_delete(c: types.CallbackQuery):
    proj = c.data.split("::",1)[1]
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("✅ Confirm Delete", callback_data=f"confirm_delete::{proj}"),
           types.InlineKeyboardButton("❌ Cancel", callback_data=f"proj:open:{proj}"))
    await c.message.edit_text(f"⚠️ Delete `{proj}`?", reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("confirm_delete::"))
async def cb_confirm_delete(c: types.CallbackQuery):
    proj = c.data.split("::",1)[1]
    uid = c.from_user.id
    shutil.rmtree(project_dir(uid, proj), ignore_errors=True)
    st = load_state()
    lst = st.get("users", {}).get(str(uid), {}).get("projects", [])
    if proj in lst: lst.remove(proj)
    save_state(st)
    await c.message.edit_text(f"🗑 {proj} deleted.")
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "back_home")
async def cb_back_home(c: types.CallbackQuery):
    await c.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb(c.from_user.id))
    await c.answer()

# ===== admin handlers =====
@dp.callback_query_handler(lambda c: c.data == "admin:main")
async def cb_admin_main(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return await c.answer("Owner only", show_alert=True)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("👥 User List", callback_data="admin_user_list"),
           types.InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"))
    kb.add(types.InlineKeyboardButton("🟩 Running Scripts", callback_data="admin_running"),
           types.InlineKeyboardButton("📂 Backup Manager", callback_data="admin_backup"))
    kb.add(types.InlineKeyboardButton("🌐 Dashboard", url=f"{BASE_URL}/admin/dashboard?key={OWNER_ID}"),
           types.InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    await c.message.edit_text("🛠 Admin Panel", reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_user_list")
async def cb_admin_user_list(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    st = load_state()
    users = list(st.get("users", {}).keys())
    if not users: return await c.message.answer("No users")
    await c.message.answer("Users:\n" + "\n".join(users))

# broadcast: register temporary handler to catch next message from owner
broadcast_waiting = {}
@dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
async def cb_admin_broadcast(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    await c.message.answer("Send broadcast (text/photo/document) now. It will be sent to all users.")
    broadcast_waiting[OWNER_ID] = True

@dp.message_handler(content_types=types.ContentType.ANY)
async def catch_broadcast_and_generate(m: types.Message):
    # if owner in broadcast_waiting -> broadcast; else other normal handlers already match earlier so guard
    if m.from_user.id == OWNER_ID and broadcast_waiting.get(OWNER_ID):
        st = load_state(); users = list(st.get("users", {}).keys())
        sent = 0
        for uid in users:
            try:
                if m.text:
                    await bot.send_message(int(uid), m.text, parse_mode="Markdown")
                elif m.photo:
                    await bot.send_photo(int(uid), m.photo[-1].file_id, caption=m.caption or "")
                elif m.document:
                    await bot.send_document(int(uid), m.document.file_id, caption=m.caption or "")
                else:
                    await bot.send_message(int(uid), "📢 (unsupported broadcast type)")
                sent += 1
            except Exception:
                pass
        broadcast_waiting.pop(OWNER_ID, None)
        return await m.reply(f"Broadcast sent to {sent} users.")
    # otherwise ignore here to let other handlers process

@dp.callback_query_handler(lambda c: c.data == "admin_running")
async def cb_admin_running(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    st = load_state()
    lines = []
    for su, procs in st.get("procs", {}).items():
        for key, meta in procs.items():
            proj = key.split(":")[0]
            lines.append(f"{su} | {proj} | pid={meta.get('pid')}")
    await c.message.answer("\n".join(lines) if lines else "No running scripts.")

@dp.callback_query_handler(lambda c: c.data == "admin_backup")
async def cb_admin_backup(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    last = backup_latest_path()
    kb = types.InlineKeyboardMarkup()
    if last:
        kb.add(types.InlineKeyboardButton("📤 Restore Latest", callback_data="admin_restore_latest"))
    kb.add(types.InlineKeyboardButton("📥 Upload Backup", callback_data="admin_upload_backup"))
    await c.message.answer(f"Latest backup: {last if last else 'None'}", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "admin_restore_latest")
async def cb_admin_restore_latest(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID: return
    last = backup_latest_path()
    if not last: return await c.message.answer("No backup found.")
    restore_from_zip(last)
    await c.message.answer("Restored from latest backup. Restart bot if required.")

@dp.callback_query_handler(lambda c: c.data == "admin_upload_backup")
async def cb_admin_upload_backup(c: types.CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return
    await c.message.answer("Send backup zip now as document. It will be restored when received.")
    # we rely on document handler earlier to save and don't auto-restore here; owner can send and we restore in document handler path for admin uploads
    # simple approach: owner sends document; msg_receive_doc will handle saving to last project; so recommend owner to use web to upload or use /backup to receive file

@dp.callback_query_handler(lambda c: c.data == "main_menu")
async def cb_main_menu(c: types.CallbackQuery):
    await c.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb(c.from_user.id))
    await c.answer()

# ===== background threads orchestration =====
def flask_thread():
    logging.info("Starting Flask server on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)

def expire_thread():
    while True:
        try:
            check_and_stop_expired()
        except Exception as e:
            logging.exception("expire check failed: %s", e)
        time.sleep(60)

def backup_thread():
    while True:
        try:
            path = create_backup()
            # attempt to send to owner (best-effort)
            try:
                with open(path, "rb") as f:
                    # send via bot - need to use asyncio loop; easiest is to schedule via aiogram's loop
                    import asyncio
                    async def send():
                        try:
                            await bot.send_document(OWNER_ID, f)
                            await bot.send_message(OWNER_ID, f"📦 Auto backup created: {os.path.basename(path)}")
                        except Exception as e:
                            logging.error("Failed to send backup to owner: %s", e)
                    asyncio.run(send())
            except Exception as e:
                logging.error("Failed to open/send backup: %s", e)
        except Exception as e:
            logging.exception("backup failed: %s", e)
        time.sleep(max(60, AUTO_BACKUP_INTERVAL))

# ===== start services =====
def start_services():
    # restore procs from last state (files must exist or will fail silently)
    try:
        restore_procs_on_boot()
    except Exception:
        logging.exception("restore_procs_on_boot failed")
    t1 = threading.Thread(target=flask_thread, daemon=True); t1.start()
    t2 = threading.Thread(target=expire_thread, daemon=True); t2.start()
    t3 = threading.Thread(target=backup_thread, daemon=True); t3.start()
    logging.info("Background threads started.")

if __name__ == "__main__":
    start_services()
    # start telegram polling (blocking)
    executor.start_polling(dp, skip_updates=True)
