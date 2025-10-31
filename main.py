import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

# ---------------- CONFIG ----------------
BOT_TOKEN = "7869581039:AAFSE2JhjV8bm7zpzrp9WMRxUV4tA0f5A_4"
OWNER_ID = 7640327597  # <-- Replace with your Telegram user id (int)
DATA_FILE = "db.json"
BACKUP_DIR = "backups"
PROJECTS_DIR = "projects"
BACKUP_INTERVAL_MIN = 10  # periodic backup every N minutes
FREE_RUNTIME_HOURS = 12
PREMIUM_RUNTIME_NONE = None  # premium 24/7
MAX_PROJECTS_FREE = 2
MAX_PROJECTS_PREMIUM = 10

# Ensure directories
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(PROJECTS_DIR, exist_ok=True)

# ---------------- Persistence ----------------
_default_db = {
    "users": {},  # user_id -> {"plan": "free"/"premium", "projects": [names], "is_owner": False}
    "projects": {},  # project_name -> {owner, files:[...], created_at, status, proc_info}
}

_db_lock = asyncio.Lock()

async def load_db() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        await save_db(_default_db)
        return dict(_default_db)
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Try to recover from latest backup
        backups = sorted(Path(BACKUP_DIR).glob("*.json"), key=os.path.getmtime, reverse=True)
        if backups:
            shutil.copy(backups[0], DATA_FILE)
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            await save_db(_default_db)
            return dict(_default_db)

async def save_db(data: Dict[str, Any]):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DATA_FILE)

async def backup_db_periodically():
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_MIN * 60)
        await do_backup()

async def do_backup():
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dst = Path(BACKUP_DIR) / f"db_{ts}.json"
    try:
        shutil.copy(DATA_FILE, dst)
    except Exception:
        # Try writing fresh
        async with _db_lock:
            db = await load_db()
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=2)

# ---------------- Helpers ----------------
async def ensure_user(db: Dict[str, Any], user_id: int):
    if str(user_id) not in db["users"]:
        db["users"][str(user_id)] = {"plan": "free", "projects": [], "is_owner": (user_id==OWNER_ID)}

def project_path(name: str) -> Path:
    return Path(PROJECTS_DIR) / name

async def create_project_folder(name: str):
    p = project_path(name)
    p.mkdir(parents=True, exist_ok=True)
    (p / "logs.txt").touch(exist_ok=True)

async def save_project_file(project: str, filename: str, data: bytes):
    p = project_path(project)
    await create_project_folder(project)
    with open(p / filename, "wb") as f:
        f.write(data)

async def append_log(project: str, text: str):
    p = project_path(project)
    with open(p / "logs.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.utcnow().isoformat()}] {text}\n")

# Keep runtime process handles in memory
process_registry: Dict[str, subprocess.Popen] = {}
# For free-user timers to auto-stop
auto_stop_tasks: Dict[str, asyncio.Task] = {}

# ---------------- Bot & Dispatcher ----------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------------- UI Helpers ----------------
def project_control_keyboard(project_name: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Run", callback_data=f"run::{project_name}"),
         InlineKeyboardButton(text="⏹ Stop", callback_data=f"stop::{project_name}"),
         InlineKeyboardButton(text="🔁 Restart", callback_data=f"restart::{project_name}")],
        [InlineKeyboardButton(text="📜 Logs", callback_data=f"logs::{project_name}"),
         InlineKeyboardButton(text="📊 Status", callback_data=f"status::{project_name}")],
        [InlineKeyboardButton(text="🔧 Install Req", callback_data=f"install::{project_name}")]
    ])
    return kb

# ---------------- Commands ----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db = await load_db()
    await ensure_user(db, message.from_user.id)
    await save_db(db)
    await message.reply("Welcome! Send a project name to create a new project.\nExample: `myproject`", parse_mode="Markdown")

# Text handler: project name creation or other text commands
@dp.message()
async def handle_text(message: types.Message):
    text = message.text.strip()
    if not text:
        return
    # Interpret as project creation request
    if " " in text or len(text) > 64:
        await message.reply("Project name invalid. Use single-word name, max 64 chars.")
        return
    project = text
    db = await load_db()
    await ensure_user(db, message.from_user.id)
    user = db["users"][str(message.from_user.id)]
    max_proj = MAX_PROJECTS_PREMIUM if user.get("plan") == "premium" else MAX_PROJECTS_FREE
    if len(user["projects"]) >= max_proj:
        await message.reply(f"Project limit reached for your plan ({max_proj}).")
        return
    if project in db["projects"]:
        await message.reply("Project name already exists. Choose a different name.")
        return
    # create project entry
    db["projects"][project] = {
        "owner": message.from_user.id,
        "files": [],
        "created_at": datetime.utcnow().isoformat(),
        "status": "stopped",
        "proc_info": None
    }
    user["projects"].append(project)
    await save_db(db)
    await create_project_folder(project)
    # Ask to upload files
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Upload Files (.py, requirements.txt etc)", callback_data=f"upload::{project}")
    ]])
    await message.reply(f"Project *{project}* created. Now send files (.py, requirements.txt).", parse_mode="Markdown", reply_markup=kb)

# Document handler: save files into active upload flow
@dp.message(lambda m: m.document is not None)
async def handle_document(message: types.Message):
    # We heuristically find latest project owned by user that doesn't have main.py yet or just use last created
    db = await load_db()
    uid = str(message.from_user.id)
    if uid not in db["users"]:
        await ensure_user(db, message.from_user.id)
        db = await load_db()
    user = db["users"][uid]
    if not user["projects"]:
        await message.reply("No project found. First create a project name by sending it as text.")
        return
    project = user["projects"][-1]
    doc = message.document
    fname = doc.file_name
    # Download
    f = await bot.get_file(doc.file_id)
    file_path = f.file_path
    data = await bot.download_file(file_path)
    await save_project_file(project, fname, data.getvalue())
    # update db
    if fname not in db["projects"][project]["files"]:
        db["projects"][project]["files"].append(fname)
    await save_db(db)
    await append_log(project, f"Uploaded file: {fname} by {message.from_user.id}")
    # provide visual uploading animation (fake) - simulate progress
    msg = await message.reply(f"Uploading {fname}: 0%")
    for p in range(10, 101, 10):
        await asyncio.sleep(0.08)
        try:
            await msg.edit_text(f"Uploading {fname}: {p}%")
        except Exception:
            pass
    kb = project_control_keyboard(project)
    await message.reply(f"File saved to project *{project}*.", parse_mode="Markdown", reply_markup=kb)

# Callback handlers for inline buttons
@dp.callback_query()
async def cb_handler(query: types.CallbackQuery):
    data = query.data or ""
    if "::" not in data:
        await query.answer()
        return
    cmd, proj = data.split("::", 1)
    db = await load_db()
    if proj not in db["projects"]:
        await query.answer("Project not found.")
        return
    # permission check: only owner or owner id for admin actions
    owner = db["projects"][proj]["owner"]
    if query.from_user.id != owner and query.from_user.id != OWNER_ID:
        await query.answer("You are not the owner of this project.", show_alert=True)
        return

    if cmd == "install":
        await query.answer("Installing requirements...")
        await run_install_requirements(query.message.chat.id, proj, query.message.message_id)
        return
    if cmd == "run":
        await query.answer()
        await start_project(proj, query.message.chat.id)
        return
    if cmd == "stop":
        await query.answer()
        await stop_project(proj, query.message.chat.id)
        return
    if cmd == "restart":
        await query.answer()
        await restart_project(proj, query.message.chat.id)
        return
    if cmd == "logs":
        await query.answer()
        await send_logs(proj, query.message.chat.id)
        return
    if cmd == "status":
        await query.answer()
        await send_status(proj, query.message.chat.id)
        return

# ---------------- Project Actions ----------------
async def run_install_requirements(chat_id: int, project: str, reply_to_message_id: Optional[int]=None):
    p = project_path(project)
    req = p / "requirements.txt"
    if not req.exists():
        await bot.send_message(chat_id, "requirements.txt not found in project folder.")
        return
    await bot.send_message(chat_id, f"Installing requirements for {project}... This can take time.")
    proc = subprocess.Popen(["python", "-m", "pip", "install", "-r", str(req)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = proc.communicate()
    text = out.decode(errors="ignore") if out else ""
    await append_log(project, f"Pip install output:\n{text}")
    if len(text) > 4000:
        fn = project_path(project) / "install_output.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write(text)
        await bot.send_document(chat_id, FSInputFile(fn))
    else:
        await bot.send_message(chat_id, f"Install output:\n<pre>{text}</pre>", parse_mode="HTML")

async def start_project(project: str, chat_id: int):
    db = await load_db()
    entry = db["projects"][project]
    owner = entry["owner"]
    # find main file
    p = project_path(project)
    main_candidates = ["main.py", "app.py", "run.py"]
    main = None
    for m in main_candidates:
        if (p / m).exists():
            main = m
            break
    if not main:
        # try any .py
        pyfiles = list(p.glob("*.py"))
        if not pyfiles:
            await bot.send_message(chat_id, "No python file found in project folder.")
            return
        main = pyfiles[0].name
    # If already running, inform
    if project in process_registry and process_registry[project].poll() is None:
        await bot.send_message(chat_id, f"Project {project} is already running.")
        return
    # Start process
    logfile = open(p / "logs.txt", "ab")
    proc = subprocess.Popen(["python", str(p / main)], stdout=logfile, stderr=subprocess.STDOUT)
    process_registry[project] = proc
    entry["status"] = "running"
    entry["proc_info"] = {"pid": proc.pid, "start_ts": datetime.utcnow().isoformat(), "main": main}
    await append_log(project, f"Started process PID={proc.pid}, main={main}")
    await save_db(db)
    await bot.send_message(chat_id, f"🚀 Project *{project}* started (PID: {proc.pid}).", parse_mode="Markdown")

    # Schedule auto-stop for free users
    uid = str(owner)
    user = db["users"].get(uid)
    plan = user.get("plan", "free")
    if plan != "premium":
        # cancel existing auto-stop
        if project in auto_stop_tasks and not auto_stop_tasks[project].done():
            auto_stop_tasks[project].cancel()
        # create a task
        async def auto_stop():
            await asyncio.sleep(FREE_RUNTIME_HOURS * 3600)
            # if still running, stop
            if project in process_registry and process_registry[project].poll() is None:
                await stop_project(project, chat_id, auto=True)
                try:
                    await bot.send_message(chat_id, f"⏰ Free runtime ended for project {project}. It was stopped automatically.")
                except Exception:
                    pass
        t = asyncio.create_task(auto_stop())
        auto_stop_tasks[project] = t

async def stop_project(project: str, chat_id: int, auto: bool=False):
    db = await load_db()
    if project not in process_registry or process_registry[project].poll() is not None:
        await bot.send_message(chat_id, f"Project {project} is not running.")
        return
    proc = process_registry[project]
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    del process_registry[project]
    entry = db["projects"][project]
    entry["status"] = "stopped"
    entry["proc_info"]["stopped_at"] = datetime.utcnow().isoformat()
    await append_log(project, f"Stopped process PID={proc.pid}")
    await save_db(db)
    await bot.send_message(chat_id, f"⏹ Project {project} stopped.")

async def restart_project(project: str, chat_id: int):
    await stop_project(project, chat_id)
    await asyncio.sleep(1)
    await start_project(project, chat_id)

async def send_logs(project: str, chat_id: int):
    p = project_path(project)
    fn = p / "logs.txt"
    if not fn.exists():
        await bot.send_message(chat_id, "No logs found.")
        return
    size = fn.stat().st_size
    if size > 5 * 1024 * 1024:
        # send last lines instead
        with open(fn, "rb") as f:
            f.seek(max(0, size - 200000))
            data = f.read()
        tmp = p / "logs_tail.txt"
        with open(tmp, "wb") as f:
            f.write(data)
        await bot.send_document(chat_id, FSInputFile(tmp))
    else:
        await bot.send_document(chat_id, FSInputFile(fn))

async def send_status(project: str, chat_id: int):
    db = await load_db()
    info = db["projects"][project]
    status = info.get("status", "stopped")
    proc = process_registry.get(project)
    pid = proc.pid if proc and proc.poll() is None else None
    owner = info.get("owner")
    text = f"Project: {project}\nOwner: {owner}\nStatus: {status}\nPID: {pid}\nFiles: {', '.join(info.get('files', []))}"
    await bot.send_message(chat_id, text)

# ---------------- Admin Panel ----------------
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("You are not the owner.")
        return
    db = await load_db()
    total_projects = len(db["projects"])
    running = sum(1 for p in process_registry if process_registry[p].poll() is None)
    users_count = len(db["users"])
    text = f"Admin Panel\nTotal users: {users_count}\nTotal projects: {total_projects}\nRunning: {running}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="List Projects", callback_data="admin::list_projects")],
        [InlineKeyboardButton(text="Backup Now", callback_data="admin::backup_now")],
        [InlineKeyboardButton(text="Show Running", callback_data="admin::show_running")]
    ])
    await message.reply(text, reply_markup=kb)

@dp.callback_query()
async def admin_cb(query: types.CallbackQuery):
    data = query.data or ""
    if not data.startswith("admin::"):
        return
    if query.from_user.id != OWNER_ID:
        await query.answer("Not allowed")
        return
    cmd = data.split("::", 1)[1]
    db = await load_db()
    if cmd == "list_projects":
        items = []
        for name, info in db["projects"].items():
            items.append(f"{name} - owner {info['owner']} - {info.get('status')}")
        await query.message.reply("\n".join(items) or "No projects")
    elif cmd == "backup_now":
        await do_backup()
        await query.message.reply("Backup done.")
    elif cmd == "show_running":
        items = []
        for name in process_registry:
            proc = process_registry[name]
            if proc.poll() is None:
                items.append(f"{name} - PID {proc.pid}")
        await query.message.reply("\n".join(items) or "No running projects")
    await query.answer()

# ---------------- Startup & Shutdown ----------------
async def on_startup():
    # Load DB (and possibly recover)
    await load_db()
    # Restore running processes? We cannot resurrect arbitrary processes but we can note state
    # Start backup task
    asyncio.create_task(backup_db_periodically())

async def on_shutdown():
    # terminate all child processes
    for name, proc in list(process_registry.items()):
        try:
            proc.terminate()
        except Exception:
            pass
    await bot.session.close()

# ---------------- Main ----------------
if __name__ == "__main__":
    try:
        print("Bot starting...")
        asyncio.run(on_startup())
        from aiogram import executor
        executor.start_polling(dp, skip_updates=True)
    except KeyboardInterrupt:
        print("Stopping...")
        asyncio.run(on_shutdown())


# ---------------- requirements.txt (for reference) ----------------
# aiogram>=3.0.0
# asyncio
# psutil
# apscheduler

"""END OF FILE"""
                        
