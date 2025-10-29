"""
GOD MADARA HOSTING BOT — ADVANCED FINAL (based on user's original script)
Features:
 - Public multi-user hosting bot
 - Upload, edit, delete, install, run/stop/restart projects
 - Auto-install requirements, auto-restart on crash
 - Hourly backups (projects + metadata), DB stored in users.json
 - Web editor (mobile light theme)
 - Free (12h) / Premium (24/7) runtime
Environment variables required:
 - BOT_TOKEN, RENDER_EXTERNAL_HOSTNAME, WEB_SECRET_KEY
Deploy: Render (Procfile: web: python main.py)
"""

import os, sys, time, zipfile, pathlib, subprocess, threading, shutil, logging, json, random, string
from datetime import datetime
from functools import wraps
from flask import Flask, request, session, redirect, render_template, jsonify, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

# ======= CONFIG =======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "your-render-app.onrender.com")
WEB_SECRET = os.environ.get("WEB_SECRET_KEY", "change_me_secret")

BASE_DIR = pathlib.Path.cwd() / "projects"
BACKUP_DIR = pathlib.Path.cwd() / "backups"
META_FILE = pathlib.Path.cwd() / "users.json"

BACKUPS_KEEP = 20
FREE_RUNTIME_SECONDS = 12 * 3600  # 12 hours free
RESTART_ON_CRASH = True
RESTART_DELAY = 5  # seconds before auto-restart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("god_madara_advanced")

BASE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# load metadata (users.json)
if META_FILE.exists():
    try:
        with open(META_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        users = {}
else:
    users = {}

def save_meta():
    try:
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        logger.exception("Failed to save metadata: %s", e)

def randpass(n=12):
    import random, string
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))

def user_dir(uid):
    p = BASE_DIR / str(uid)
    p.mkdir(parents=True, exist_ok=True)
    return p

def project_dir(uid, proj):
    p = user_dir(uid) / proj
    p.mkdir(parents=True, exist_ok=True)
    return p

def detect_main_file(uproj: pathlib.Path):
    for name in ("main.py", "app.py"):
        if (uproj / name).exists():
            return name
    py = list(uproj.glob("*.py"))
    return py[0].name if py else None

# ======= FLASK WEB EDITOR =======
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = WEB_SECRET

def login_required(f):
    @wraps(f)
    def inner(uid, *args, **kwargs):
        if "uid" not in session:
            return redirect("/login")
        if str(session.get("uid")) != str(uid):
            return "Not allowed", 403
        return f(uid, *args, **kwargs)
    inner.__name__ = f.__name__
    return inner

@app.route("/login", methods=["GET","POST"])
def login_page():
    error=None
    if request.method=="POST":
        uid = request.form.get("uid"); pwd = request.form.get("pwd")
        if uid in users:
            for p,meta in users[uid].get("projects", {}).items():
                if meta.get("web_password")==pwd:
                    session["uid"]=uid; return redirect(url_for("editor_list", uid=uid))
        error="Invalid credentials"
    return render_template("login_mobile.html", error=error, header="⚡ GOD MADARA HOSTING BOT ⚡ - ADVANCED")

@app.route("/editor/<uid>")
@login_required
def editor_list(uid):
    projs = users.get(str(uid), {}).get("projects", {})
    return render_template("editor_list.html", uid=uid, projs=projs, host=RENDER_HOST, header="⚡ GOD MADARA HOSTING BOT ⚡ - ADVANCED")

@app.route("/editor/<uid>/project/<proj>")
@login_required
def editor(uid, proj):
    uproj = project_dir(uid, proj)
    files = [str(p.relative_to(uproj)) for p in uproj.glob("**/*") if p.is_file()]
    return render_template("editor.html", uid=uid, proj=proj, files=files, host=RENDER_HOST, header="⚡ GOD MADARA HOSTING BOT ⚡ - ADVANCED")

@app.route("/editor/api/files/<uid>/<proj>")
@login_required
def api_files(uid, proj):
    uproj = project_dir(uid, proj)
    files = [str(p.relative_to(uproj)) for p in uproj.glob("**/*") if p.is_file()]
    return jsonify({"files": files})

@app.route("/editor/api/file/<uid>/<proj>", methods=["GET","POST","DELETE"])
@login_required
def api_file(uid, proj):
    uproj = project_dir(uid, proj)
    if request.method=="GET":
        path = request.args.get("path"); fp = uproj / path
        if not fp.exists(): return "Not found", 404
        return fp.read_text(errors="ignore")
    if request.method=="POST":
        data = request.get_json(); path = data.get("path"); content = data.get("content","")
        fp = uproj / path; fp.parent.mkdir(parents=True, exist_ok=True); fp.write_text(content)
        users.setdefault(str(uid), {}).setdefault("projects", {}).setdefault(proj, {})["restart_request"] = True; save_meta()
        return jsonify({"status":"ok"})
    if request.method=="DELETE":
        data = request.get_json(); path = data.get("path"); fp = uproj / path
        if fp.exists(): fp.unlink()
        return jsonify({"status":"ok"})

# ======= PROCESS & RUNTIME MANAGEMENT =======
process_table = {}
process_lock = threading.Lock()

def start_project_process(uid: str, proj: str, bot_app=None):
    uproj = project_dir(uid, proj)
    mainfile = detect_main_file(uproj)
    if not mainfile:
        return False, "No python file found to run."
    mainpath = uproj / mainfile
    logfile = uproj / "run.log"
    lf = open(str(logfile), "ab")
    try:
        proc = subprocess.Popen([sys.executable, str(mainpath)], cwd=str(uproj), stdout=lf, stderr=lf)
    except Exception as e:
        return False, f"Failed to start process: {e}"
    key = f"{uid}:{proj}"
    with process_lock:
        old = process_table.get(key)
        if old:
            t = old.get("auto_timer")
            try:
                if t: t.cancel()
            except Exception: pass
        users.setdefault(str(uid), {}).setdefault("projects", {}).setdefault(proj, {})["running"] = True
        users[str(uid)]["projects"][proj]["last_started"] = time.time()
        save_meta()
        is_premium = users.get(str(uid), {}).get("premium", False)
        auto_timer = None
        if not is_premium:
            seconds = FREE_RUNTIME_SECONDS
            def stop_after():
                try:
                    stop_project_process(uid, proj)
                    if bot_app:
                        try: bot_app.bot.send_message(int(uid), f"⏰ Free runtime limit reached. Project {proj} stopped after 12 hours.") 
                        except: pass
                except: pass
            auto_timer = threading.Timer(seconds, stop_after); auto_timer.daemon=True; auto_timer.start()
        process_table[key] = {"proc":proc, "started_at":time.time(), "auto_timer":auto_timer, "restarts":0}
    return True, f"Started {mainfile} (pid {proc.pid})"

def stop_project_process(uid: str, proj: str):
    key = f"{uid}:{proj}"
    with process_lock:
        info = process_table.get(key)
        if not info:
            users.setdefault(str(uid), {}).setdefault("projects", {}).setdefault(proj, {})["running"] = False; save_meta()
            return False, "Not running (no tracked process)."
        proc = info.get("proc"); timer = info.get("auto_timer")
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=8)
                except: proc.kill()
        except Exception: pass
        try:
            if timer: timer.cancel()
        except: pass
        process_table.pop(key, None)
        users.setdefault(str(uid), {}).setdefault("projects", {}).setdefault(proj, {})["running"] = False; save_meta()
    return True, "Stopped."

def restart_project_process(uid: str, proj: str, bot_app=None):
    stop_project_process(uid, proj)
    time.sleep(0.6)
    return start_project_process(uid, proj, bot_app=bot_app)

def monitor_processes_loop(bot_app=None):
    """Monitor background processes and auto-restart on crash if enabled"""
    while True:
        try:
            with process_lock:
                for key, info in list(process_table.items()):
                    proc = info.get("proc")
                    if proc and proc.poll() is not None:
                        # process exited
                        uid, proj = key.split(":",1)
                        logger.info("Process exited for %s/%s, code=%s", uid, proj, proc.returncode)
                        users.setdefault(str(uid), {}).setdefault("projects", {}).setdefault(proj, {})["running"] = False
                        save_meta()
                        # auto-restart if enabled
                        if RESTART_ON_CRASH:
                            # small delay then restart
                            time.sleep(RESTART_DELAY)
                            try:
                                ok, msg = start_project_process(uid, proj, bot_app=bot_app)
                                if ok:
                                    process_table[key]["restarts"] = process_table[key].get("restarts",0) + 1
                                    try:
                                        if bot_app:
                                            bot_app.bot.send_message(int(uid), f"🔁 Project {proj} was restarted automatically after crash.")
                                    except: pass
                            except Exception as e:
                                logger.exception("Auto-restart failed: %s", e)
        except Exception as e:
            logger.exception("Monitor loop error: %s", e)
        time.sleep(4)

def tail_log(uproj: pathlib.Path, length=3000):
    lf = uproj / "run.log"
    if not lf.exists():
        return "No logs yet."
    try:
        text = lf.read_text(errors="ignore")
        return text[-length:]
    except Exception as e:
        return f"Error reading logs: {e}"

# ======= TELEGRAM HANDLERS =======
NEW_NAME = range(1)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    users.setdefault(uid, {}).setdefault("projects", {})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 New Project", callback_data="newproject")],
        [InlineKeyboardButton("📂 My Projects", callback_data=f"myprojects|{uid}")],
        [InlineKeyboardButton("⚙️ Manage Files (Web)", callback_data=f"managefiles|{uid}")],
        [InlineKeyboardButton("🚀 Deployment", callback_data=f"deployment|{uid}")],
    ])
    await update.message.reply_text("✅ Welcome to ⚡ GOD MADARA HOSTING BOT ⚡ - ADVANCED\nChoose an option below 👇", reply_markup=kb)

async def newproject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer(); await update.callback_query.edit_message_text("Enter a name for your new project (no spaces):")
    else:
        await update.message.reply_text("Enter a name for your new project (no spaces):")
    return NEW_NAME

async def receive_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().replace(" ","_"); uid = str(update.effective_user.id)
    users.setdefault(uid, {}).setdefault("projects", {})
    if name in users[uid]["projects"]:
        await update.message.reply_text("Project exists. Choose another name."); return ConversationHandler.END
    users[uid]["projects"][name] = {"created_at": time.time(), "running": False, "web_password": randpass(12)}
    users[uid]["creating"] = name; users[uid]["premium"] = users[uid].get("premium", False); save_meta()
    await update.message.reply_text(f"Project '{name}' created. Now send your .py or .zip file as Document.") 
    return ConversationHandler.END

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document; uid = str(update.effective_user.id)
    proj = users.get(uid, {}).get("creating")
    if not proj:
        return await update.message.reply_text("No project in creation. Use New Project first.")
    uproj = project_dir(uid, proj); dest = uproj / (doc.file_name or "uploaded")
    status = await update.message.reply_text(f"📤 Preparing upload: {doc.file_name}\n\n▒░░░░░░░░ 0%")
    try:
        await status.edit_text("📥 Downloading...\n\n▓▓░░░░░░░ 30%")
        await doc.get_file().download_to_drive(str(dest))
        await status.edit_text("💾 Saving...\n\n▓▓▓▓▓░░░░ 60%")
        time.sleep(0.4)
        if str(dest).lower().endswith(".zip"):
            await status.edit_text("📦 Extracting ZIP...\n\n▓▓▓▓▓▓▓░ 85%")
            with zipfile.ZipFile(str(dest), "r") as zf: zf.extractall(path=str(uproj))
            try: dest.unlink()
            except: pass
        await status.edit_text("✅ Finalizing...\n\n▓▓▓▓▓▓▓▓▓ 100%")
        users[uid].pop("creating", None); save_meta()
        url = f"https://{RENDER_HOST}/editor/{uid}/project/{proj}"; pwd = users[uid]["projects"][proj]["web_password"]
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🖥️ Open Web Editor", url=url), InlineKeyboardButton("🔁 Deployment", callback_data=f"deployment|{proj}|{uid}")],[InlineKeyboardButton("🗑️ Delete Project", callback_data=f"deleteproj|{proj}|{uid}"), InlineKeyboardButton("🔙 My Projects", callback_data=f"myprojects|{uid}")]])
        await status.edit_text(f"✅ Uploaded!\n🌐 Web Editor: {url}\n🆔 UID: {uid}\n🔑 Password: {pwd}", reply_markup=kb)
    except Exception as e:
        await status.edit_text(f"❌ Upload failed: {e}")

def project_control_keyboard(proj, uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖥️ Edit (Web)", url=f"https://{RENDER_HOST}/editor/{uid}/project/{proj}"), InlineKeyboardButton("📁 Files", callback_data=f"manage|{proj}|{uid}")],
        [InlineKeyboardButton("📦 Install Req", callback_data=f"install|{proj}|{uid}"), InlineKeyboardButton("▶️ Start", callback_data=f"start|{proj}|{uid}")],
        [InlineKeyboardButton("⏹ Stop", callback_data=f"stop|{proj}|{uid}"), InlineKeyboardButton("🔁 Restart", callback_data=f"restart|{proj}|{uid}")],
        [InlineKeyboardButton("📜 Logs", callback_data=f"logs|{proj}|{uid}"), InlineKeyboardButton("🗑 Delete", callback_data=f"deleteproj|{proj}|{uid}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"myprojects|{uid}")]
    ])

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); data = q.data or ""; parts = data.split("|"); action = parts[0]
    if action == "myprojects":
        uid = parts[1] if len(parts)>1 else str(q.from_user.id); projs = users.get(uid, {}).get("projects", {}) or {}
        if not projs:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🆕 New Project", callback_data="newproject")]])
            await q.edit_message_text("You have no projects yet. Create one:", reply_markup=kb); return
        buttons=[]; text="Your Projects:\n\n"
        for p in projs.keys():
            text += f"• {p}\n"; buttons.append([InlineKeyboardButton(f"⚙️ {p}", callback_data=f"projectmenu|{p}|{uid}")])
        buttons.append([InlineKeyboardButton("🆕 Create New", callback_data="newproject")]); buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data=f"mainmenu|{uid}")])
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons)); return

    if action == "projectmenu":
        if len(parts)<3: await q.edit_message_text("Invalid project request."); return
        proj = parts[1]; uid = parts[2]
        if proj not in users.get(uid, {}).get("projects", {}):
            await q.edit_message_text("Project not found."); return
        text = f"Project: {proj}\nOwner UID: {uid}"; kb = project_control_keyboard(proj, uid); await q.edit_message_text(text, reply_markup=kb); return

    if action == "manage":
        if len(parts)<3: await q.edit_message_text("Invalid manage request."); return
        proj = parts[1]; uid = parts[2]; uproj = project_dir(uid, proj)
        files = "\n".join([str(p.relative_to(uproj)) for p in uproj.glob("**/*") if p.is_file()]) or "No files"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🖥️ Open Web Editor", url=f"https://{RENDER_HOST}/editor/{uid}/project/{proj}")],[InlineKeyboardButton("🔙 Back", callback_data=f"projectmenu|{proj}|{uid}")]])
        await q.edit_message_text(f"Files for {proj}:\n{files}", reply_markup=kb); return

    if action == "deployment":
        if len(parts)==3:
            proj = parts[1]; uid = parts[2]
        else:
            uid = parts[1] if len(parts)>1 else str(q.from_user.id); projs = users.get(uid, {}).get("projects", {}) or {}
            if not projs: await q.edit_message_text("No projects to deploy. Create a project first."); return
            buttons=[]; text="Select project for deployment:\n\n"
            for p in projs.keys(): text += f"• {p}\n"; buttons.append([InlineKeyboardButton(f"🚀 {p}", callback_data=f"deployment|{p}|{uid}")])
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"mainmenu|{uid}")]); await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons)); return
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📦 Install Requirements", callback_data=f"install|{proj}|{uid}"), InlineKeyboardButton("▶️ Start", callback_data=f"start|{proj}|{uid}")],[InlineKeyboardButton("⏹ Stop", callback_data=f"stop|{proj}|{uid}"), InlineKeyboardButton("🔁 Restart", callback_data=f"restart|{proj}|{uid}")],[InlineKeyboardButton("📜 Logs", callback_data=f"logs|{proj}|{uid}"), InlineKeyboardButton("🗑 Delete", callback_data=f"deleteproj|{proj}|{uid}")],[InlineKeyboardButton("🔙 Back", callback_data=f"projectmenu|{proj}|{uid}")]])
        await q.edit_message_text(f"Deployment menu for {proj}:", reply_markup=kb); return

    if action in ("install","start","stop","restart","logs","deleteproj"):
        if len(parts)<3: await q.edit_message_text("Invalid request."); return
        proj = parts[1]; uid = parts[2]; caller = str(q.from_user.id)
        if caller != str(uid): await q.edit_message_text("❌ You are not the owner of this project. Action denied."); return
        uproj = project_dir(uid, proj)
        if action == "install":
            req = uproj / "requirements.txt"
            if not req.exists(): await q.edit_message_text("No requirements.txt found.", reply_markup=project_control_keyboard(proj, uid)); return
            await q.edit_message_text("Installing dependencies... You will be notified when complete.", reply_markup=project_control_keyboard(proj, uid))
            def install_thread():
                try:
                    subprocess.check_call([shutil.which("pip") or "pip", "install", "-r", str(req)])
                    try: context.application.bot.send_message(int(uid), f"✅ Dependencies installed for {proj}.") 
                    except: pass
                except Exception as e:
                    try: context.application.bot.send_message(int(uid), f"❌ Failed to install dependencies for {proj}: {e}") 
                    except: pass
            threading.Thread(target=install_thread, daemon=True).start(); return
        if action == "start":
            ok,msg = start_project_process(uid, proj, bot_app=context.application); await q.edit_message_text(msg, reply_markup=project_control_keyboard(proj, uid)); return
        if action == "stop":
            ok,msg = stop_project_process(uid, proj); await q.edit_message_text(msg, reply_markup=project_control_keyboard(proj, uid)); return
        if action == "restart":
            ok,msg = restart_project_process(uid, proj, bot_app=context.application); await q.edit_message_text(msg, reply_markup=project_control_keyboard(proj, uid)); return
        if action == "logs":
            txt = tail_log(uproj); 
            if len(txt)>3900: txt = txt[-3900:]
            await q.edit_message_text(f"Last logs:\n{txt}", reply_markup=project_control_keyboard(proj, uid)); return
        if action == "deleteproj":
            stop_project_process(uid, proj)
            try: shutil.rmtree(uproj)
            except Exception: pass
            users.get(uid, {}).get("projects", {}).pop(proj, None); save_meta()
            await q.edit_message_text(f"🗑 Project {proj} deleted.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 My Projects", callback_data=f"myprojects|{uid}")]])); return

    if action == "mainmenu":
        uid = parts[1] if len(parts)>1 else str(q.from_user.id)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🆕 New Project", callback_data="newproject")],[InlineKeyboardButton("📂 My Projects", callback_data=f"myprojects|{uid}")],[InlineKeyboardButton("⚙️ Manage Files (Web)", callback_data=f"managefiles|{uid}")],[InlineKeyboardButton("🚀 Deployment", callback_data=f"deployment|{uid}")]])
        await q.edit_message_text("Main menu:", reply_markup=kb); return

    await q.edit_message_text("Unknown action or invalid input.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use the inline menu. Send /start to open the menu.")

# ======= BACKUPS & DB SNAPSHOT =======
def backup_project(uid, proj):
    uproj = project_dir(uid, proj)
    if not uproj.exists(): return
    outdir = BACKUP_DIR / str(uid); outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    z = outdir / f"{proj}_{ts}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(uproj):
            for f in files:
                fp = pathlib.Path(root) / f; rel = fp.relative_to(uproj); zf.write(fp, arcname=str(rel))
    files = sorted(outdir.glob(f"{proj}_*.zip"))
    if len(files)>BACKUPS_KEEP:
        for old in files[:-BACKUPS_KEEP]:
            try: old.unlink()
            except: pass

def db_snapshot():
    try:
        out = BACKUP_DIR / "db_snapshots"; out.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target = out / f"users_{ts}.json"
        with open(target, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        logger.exception("DB snapshot failed: %s", e)

def backup_loop():
    while True:
        try:
            for uid, meta in list(users.items()):
                for proj in meta.get("projects", {}):
                    backup_project(uid, proj)
            db_snapshot()
        except Exception as e:
            logger.exception("backup loop error: %s", e)
        time.sleep(3600)

# ======= MAIN =======
def main():
    t = threading.Thread(target=backup_loop, daemon=True); t.start()
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    monitor_thread = threading.Thread(target=lambda: monitor_processes_loop(bot_app=app_bot), daemon=True); monitor_thread.start()
    conv = ConversationHandler(entry_points=[CallbackQueryHandler(newproject_start, pattern="^newproject$")], states={NEW_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_project_name)]}, fallbacks=[])
    app_bot.add_handler(CommandHandler("start", start_cmd)); app_bot.add_handler(conv); app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document)); app_bot.add_handler(CallbackQueryHandler(callback_handler)); app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000))), daemon=True); flask_thread.start()
    import asyncio; asyncio.run(app_bot.run_polling())

if __name__ == "__main__": main()