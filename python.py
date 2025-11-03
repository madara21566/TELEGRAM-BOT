# main.py
# MADARA HOSTING BOT - Final single-file controller
# Requirements: aiogram, flask, uvicorn, psutil
# Place this at project root alongside `templates/`, `static/`, `utils/` and run.

import os
import time
import json
import secrets
import shutil
import zipfile
import asyncio
from pathlib import Path
from threading import Thread
from datetime import datetime

from flask import Flask, request, redirect, send_file, render_template, abort, make_response
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_polling

# utils we expect to exist (from the package created earlier)
from utils.helpers import load_json, save_json, ensure_user_record, now_iso
from utils.runner import start_user_process, stop_user_process, is_process_running
from utils.installer import detect_imports_and_install
from utils.backup import create_backup_and_rotate

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
BACKUP_INTERVAL_MIN = int(os.getenv("BACKUP_INTERVAL", "10"))
MAX_FREE = int(os.getenv("MAX_FREE_PROJECTS", "2"))
MAX_PREM = int(os.getenv("MAX_PREMIUM_PROJECTS", "10"))
DATA_PATH = Path(os.getenv("DATA_PATH", "./data")).resolve()
FILEMANAGER_SECRET = os.getenv("FILEMANAGER_SECRET", "secretkey786")
PORT = int(os.getenv("PORT", os.getenv("REPL_PORT", "8080")))

if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN in env")

# Directories & state
ROOT = Path(".").resolve()
USERS_DIR = DATA_PATH / "users"
TOKENS_FILE = DATA_PATH / "fm_tokens.json"
STATE_FILE = DATA_PATH / "state.json"
BACKUPS_DIR = Path("backups")

USERS_DIR.mkdir(parents=True, exist_ok=True)
DATA_PATH.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Load or initialize state
def load_state():
    return load_json(str(STATE_FILE), {"users": {}, "procs": {}, "premium": [], "banned": [], "awaiting_admin": {}})

STATE = load_state()

def save_state():
    save_json(str(STATE_FILE), STATE)

# ---------------- Flask Web (File Manager + Admin) ----------------
app = Flask(__name__, template_folder="templates", static_folder="static")

def create_fm_token(uid:int, proj:str, lifetime_seconds:int=3600):
    tokens = load_json(str(TOKENS_FILE), {})
    token = secrets.token_urlsafe(18)
    tokens[token] = {"uid": int(uid), "proj": proj, "expiry": int(time.time()) + lifetime_seconds}
    save_json(str(TOKENS_FILE), tokens)
    return token

def validate_fm_token(token:str, uid:int, proj:str):
    tokens = load_json(str(TOKENS_FILE), {})
    info = tokens.get(token)
    if not info: 
        return False
    if info["uid"] != int(uid) or info["proj"] != proj:
        return False
    if int(time.time()) > info["expiry"]:
        tokens.pop(token, None); save_json(str(TOKENS_FILE), tokens); return False
    return True

@app.get("/fm")
def fm_index(uid:int=None, proj:str=None, token:str=None):
    if not uid or not proj or not token:
        return "<h3>Invalid parameters</h3>", 400
    if not validate_fm_token(token, int(uid), proj):
        return "<h3>Invalid or expired token</h3>", 403
    base = USERS_DIR / str(uid) / proj
    if not base.exists():
        return "<h3>Project not found</h3>", 404
    files = sorted([p.name for p in base.iterdir() if p.is_file()])
    return render_template("fm_index.html", uid=uid, proj=proj, token=token, files=files, base_url=BASE_URL)

@app.post("/fm/upload")
def fm_upload():
    token = request.form.get("token")
    uid = request.form.get("uid")
    proj = request.form.get("proj")
    if not (uid and proj and token):
        return "Missing", 400
    if not validate_fm_token(token, int(uid), proj):
        return "Invalid token", 403
    file = request.files.get("file")
    if not file:
        return "No file", 400
    base = USERS_DIR / str(uid) / proj
    base.mkdir(parents=True, exist_ok=True)
    dest = base / file.filename
    file.save(str(dest))
    if dest.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(str(dest),'r') as z:
                z.extractall(path=str(base))
            dest.unlink()
        except Exception as e:
            return f"ZIP extract error: {e}", 500
    return redirect(f"{BASE_URL}/fm?uid={uid}&proj={proj}&token={token}")

@app.get("/fm/download")
def fm_download(uid:int=None, proj:str=None, file:str=None, token:str=None):
    if not validate_fm_token(token, int(uid), proj): abort(403)
    p = USERS_DIR / str(uid) / proj / file
    if not p.exists(): abort(404)
    return send_file(str(p), as_attachment=True, download_name=p.name)

@app.get("/fm/delete")
def fm_delete(uid:int=None, proj:str=None, file:str=None, token:str=None):
    if not validate_fm_token(token, int(uid), proj): abort(403)
    p = USERS_DIR / str(uid) / proj / file
    if p.exists():
        p.unlink()
    return redirect(f"{BASE_URL}/fm?uid={uid}&proj={proj}&token={token}")

@app.get("/fm/edit")
def fm_edit(uid:int=None, proj:str=None, file:str=None, token:str=None):
    if not validate_fm_token(token, int(uid), proj): abort(403)
    p = USERS_DIR / str(uid) / proj / file
    if not p.exists(): abort(404)
    content = p.read_text(errors="ignore")
    return render_template("fm_edit.html", uid=uid, proj=proj, file=file, token=token, content=content, base_url=BASE_URL)

@app.post("/fm/save")
def fm_save():
    uid = request.form.get("uid"); proj = request.form.get("proj"); file = request.form.get("file"); token = request.form.get("token"); content = request.form.get("content")
    if not validate_fm_token(token, int(uid), proj): abort(403)
    p = USERS_DIR / str(uid) / proj / file
    p.write_text(content)
    return redirect(f"{BASE_URL}/fm?uid={uid}&proj={proj}&token={token}")

@app.get("/fm/delete_project")
def fm_delete_project(uid:int=None, proj:str=None, token:str=None):
    if not validate_fm_token(token, int(uid), proj): abort(403)
    base = USERS_DIR / str(uid) / proj
    if base.exists():
        shutil.rmtree(str(base))
        # remove from STATE
        if STATE["users"].get(str(uid)):
            try:
                STATE["users"][str(uid)]["projects"].remove(proj)
            except Exception:
                pass
            save_state()
    return f"Deleted project {proj}"

# Admin web endpoints - downloadable backup listing & download
@app.get("/admin/backups")
def admin_backups(pw: str = None):
    # simple admin password in query (for quick use) - not ideal for prod
    admin_pw = os.getenv("ADMIN_PASSWORD", "")
    if not pw or pw != admin_pw:
        return "<h3>Provide valid ADMIN_PASSWORD (as ?pw=...)</h3>", 403
    files = sorted([p.name for p in BACKUPS_DIR.glob("backup_*.zip")], reverse=True)
    out = "<h3>Backups</h3><ul>"
    for f in files:
        out += f'<li>{f} - <a href="/admin/download_backup?pw={pw}&file={f}">Download</a></li>'
    out += "</ul>"
    return out

@app.get("/admin/download_backup")
def admin_download_backup(pw: str = None, file: str = None):
    admin_pw = os.getenv("ADMIN_PASSWORD", "")
    if not pw or pw != admin_pw:
        return "<h3>Invalid admin password</h3>", 403
    f = BACKUPS_DIR / file
    if not f.exists():
        return "Not found", 404
    return send_file(str(f), as_attachment=True, download_name=f.name)

# ---------------- Aiogram Bot ----------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def main_kb(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🆕 New Project", callback_data="deploy:start"))
    kb.add(types.InlineKeyboardButton("📁 My Projects", callback_data="menu:my_projects"))
    kb.add(types.InlineKeyboardButton("❓ Help", callback_data="menu:help"))
    kb.add(types.InlineKeyboardButton("💎 Premium", callback_data="upgrade:premium"))
    if int(uid) == OWNER_ID:
        kb.add(types.InlineKeyboardButton("🛠 Admin Panel", callback_data="admin:main"))
    return kb

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    ensure_user_record(uid, STATE)
    # make sure banned list enforced
    if str(uid) in STATE.get("banned", []):
        await bot.send_message(uid, "You are banned from using this bot.")
        return
    text = """👋 Welcome to the Python Project Hoster!

I'm your personal bot for securely deploying and managing your Python scripts and applications, right here from Telegram.

━━━━━━━━━━━━━━━━━━━
⚡ Key Features:
🚀 Deploy Instantly — Upload your code as a .zip or .py file and I’ll handle the rest.
📂 Manage from Web Dashboard — Edit, run, or delete scripts live.
🪄 Auto Setup — Automatically install missing Python packages.
💾 Backup System — Projects backed up every 10 minutes.
📊 Resource Monitor — Shows CPU, RAM, and uptime per project.
━━━━━━━━━━━━━━━━━━━

🆓 Free Tier:
• Host up to 2 projects
• 12 hours per run

⭐ Premium Tier:
• Host up to 10 projects
• 24/7 continuous runtime
• Daily auto backups
━━━━━━━━━━━━━━━━━━━

🧑‍💻 Powered by: @MADARAXHEREE
🔒 Secure • Fast • Easy to Use
"""
    await bot.send_message(uid, text, reply_markup=main_kb(uid))

@dp.callback_query_handler(lambda c: c.data == "menu:help")
async def cb_help(c: types.CallbackQuery):
    await c.message.edit_text("Help:\n• New Project → name → upload .py/.zip (send as document)\n• My Projects → manage your projects\n• Free: 2 projects (12h), Premium: 10 projects (24/7)", reply_markup=main_kb(c.from_user.id))

# Deploy flow
@dp.callback_query_handler(lambda c: c.data == "deploy:start")
async def cb_deploy_start(c: types.CallbackQuery):
    uid = c.from_user.id
    if str(uid) in STATE.get("banned", []):
        await c.answer("You are banned.", show_alert=True); return
    ensure_user_record(uid, STATE)
    STATE["users"].setdefault(str(uid), {})
    STATE["users"][str(uid)].update({"awaiting_name": True})
    save_state()
    await bot.send_message(uid, "📦 Send the project name (single word, no spaces).")
    await c.answer()

@dp.message_handler(content_types=types.ContentType.TEXT)
async def text_msg(msg: types.Message):
    uid = msg.from_user.id
    # owner-admin awaiting actions
    awaiting = STATE.get("awaiting_admin", {})
    if awaiting:
        # handle admin flows keyed by owner id (owner only)
        adm = awaiting.get(str(OWNER_ID))
        if adm and msg.from_user.id == OWNER_ID:
            action = adm.get("action")
            if action == "add_premium":
                try:
                    target = str(int(msg.text.strip()))
                    if target not in STATE.get("premium", []):
                        STATE.setdefault("premium", []).append(target)
                        save_state()
                        await msg.reply(f"✅ Added premium for user {target}")
                    else:
                        await msg.reply("User already premium.")
                except:
                    await msg.reply("Invalid user id.")
                awaiting.pop(str(OWNER_ID), None); save_state(); return
            if action == "remove_premium":
                try:
                    target = str(int(msg.text.strip()))
                    if target in STATE.get("premium", []):
                        STATE["premium"].remove(target)
                        save_state()
                        await msg.reply(f"✅ Removed premium for user {target}")
                    else:
                        await msg.reply("User not premium.")
                except:
                    await msg.reply("Invalid user id.")
                awaiting.pop(str(OWNER_ID), None); save_state(); return
            if action == "ban_user":
                try:
                    target = str(int(msg.text.strip()))
                    if target not in STATE.get("banned", []):
                        STATE.setdefault("banned", []).append(target)
                        save_state()
                        await msg.reply(f"🚫 Banned user {target}")
                    else:
                        await msg.reply("User already banned.")
                except:
                    await msg.reply("Invalid user id.")
                awaiting.pop(str(OWNER_ID), None); save_state(); return
            if action == "unban_user":
                try:
                    target = str(int(msg.text.strip()))
                    if target in STATE.get("banned", []):
                        STATE["banned"].remove(target)
                        save_state()
                        await msg.reply(f"✅ Unbanned user {target}")
                    else:
                        await msg.reply("User not banned.")
                except:
                    await msg.reply("Invalid user id.")
                awaiting.pop(str(OWNER_ID), None); save_state(); return
            if action == "download_backup_user":
                # expect "user_id backup_name"
                parts = msg.text.strip().split()
                if len(parts) >= 2:
                    target = parts[0]; fname = parts[1]
                    filep = BACKUPS_DIR / fname
                    if filep.exists():
                        await bot.send_document(OWNER_ID, open(str(filep),'rb'))
                        await msg.reply("Sent backup.")
                    else:
                        await msg.reply("Backup not found.")
                else:
                    await msg.reply("Send: <user_id> <backup_filename.zip>")
                awaiting.pop(str(OWNER_ID), None); save_state(); return

    urec = STATE["users"].get(str(uid), {})
    if urec.get("awaiting_name"):
        name = msg.text.strip()
        if not name or " " in name:
            await msg.reply("Invalid name. Single word only.")
            return
        # check limits
        is_prem = str(uid) in STATE.get("premium", [])
        limit = MAX_PREM if is_prem else MAX_FREE
        projects = STATE["users"].setdefault(str(uid), {}).setdefault("projects", [])
        if len(projects) >= limit:
            await msg.reply("Project limit reached. Upgrade to premium.")
            STATE["users"][str(uid)].pop("awaiting_name", None)
            save_state()
            return
        projects.append(name)
        Path(USERS_DIR / str(uid) / name).mkdir(parents=True, exist_ok=True)
        STATE["users"][str(uid)].pop("awaiting_name", None)
        save_state()
        await msg.reply(f"Project `{name}` created. Now upload .py or .zip as Document (send file).")
        return

@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def doc_msg(msg: types.Message):
    uid = msg.from_user.id
    if str(uid) in STATE.get("banned", []):
        await msg.reply("You are banned."); return
    urec = STATE["users"].get(str(uid))
    if not urec or not urec.get("projects"):
        await msg.reply("No project found. Use New Project first.")
        return
    project = urec["projects"][-1]
    doc = msg.document
    base = USERS_DIR / str(uid) / project
    base.mkdir(parents=True, exist_ok=True)
    path = base / doc.file_name
    await msg.reply("📤 Uploading...")
    await doc.download(destination_file=str(path))
    await msg.reply("📦 Saved.")
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(str(path),'r') as z:
                z.extractall(path=str(base))
            path.unlink()
        except Exception as e:
            await msg.reply(f"Zip extract error: {e}")
            return
    mains = list(base.glob("*.py"))
    if mains:
        await msg.reply("🔎 Detecting imports and installing (best-effort)...")
        try:
            pkgs = detect_imports_and_install(mains[0])
            if pkgs:
                await msg.reply(f"Installed: {', '.join(pkgs)}")
            else:
                await msg.reply("No external imports detected.")
        except Exception as e:
            await msg.reply(f"Install error: {e}")
    await msg.reply("✅ Project ready. Open My Projects to manage it.", reply_markup=main_kb(uid))

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("menu:my_projects"))
async def cb_my_projects(c: types.CallbackQuery):
    uid = c.from_user.id
    projects = STATE["users"].get(str(uid), {}).get("projects", [])
    if not projects:
        await c.message.answer("No projects yet. Use New Project.")
        await c.answer()
        return
    text = "📁 Your Projects:\n"
    kb = types.InlineKeyboardMarkup(row_width=1)
    for pr in projects:
        kb.add(types.InlineKeyboardButton(f"{pr} ▶", callback_data=f"proj:open:{pr}"))
    kb.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_home"))
    await c.message.answer(text, reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("proj:"))
async def cb_project_actions(c: types.CallbackQuery):
    uid = c.from_user.id
    parts = c.data.split(":")
    action = parts[1]
    if action == "open":
        proj = parts[2]
        base = USERS_DIR / str(uid) / proj
        files = sorted([p.name for p in base.iterdir() if p.is_file()])
        text = f"📂 Project: {proj}\nFiles:\n" + ("\n".join(files[:50]) if files else "No files yet.")
        kb = types.InlineKeyboardMarkup(row_width=2)
        for f in files:
            if f.lower().endswith(".py"):
                kb.add(types.InlineKeyboardButton(f"▶ {f}", callback_data=f"run:{proj}:{f}"),
                       types.InlineKeyboardButton(f"⏹ {f}", callback_data=f"stop:{proj}:{f}"))
                kb.add(types.InlineKeyboardButton(f"Logs {f}", callback_data=f"logs:{proj}:{f}"))
        token = create_fm_token(uid, proj)
        link = f"{BASE_URL}/fm?uid={uid}&proj={proj}&token={token}"
        kb.add(types.InlineKeyboardButton("📂 File Manager (Web)", url=link))
        kb.add(types.InlineKeyboardButton("🌐 Open Dashboard", url=f"{BASE_URL}/dashboard?uid={uid}&proj={proj}&token={token}"))
        kb.add(types.InlineKeyboardButton("🗑 Delete Project", callback_data=f"proj:delete:{proj}"))
        kb.add(types.InlineKeyboardButton("⬅️ Back", callback_data="menu:my_projects"))
        await c.message.answer(text, reply_markup=kb)
        await c.answer()
        return
    if action == "delete":
        proj = parts[2]
        base = USERS_DIR / str(uid) / proj
        if base.exists():
            shutil.rmtree(str(base))
        try:
            STATE["users"].get(str(uid), {}).get("projects", []).remove(proj)
        except Exception:
            pass
        save_state()
        await c.message.answer(f"Deleted project {proj}")
        await c.answer()
        return

@dp.callback_query_handler(lambda c: c.data and (c.data.startswith("run:") or c.data.startswith("stop:") or c.data.startswith("logs:")))
async def cb_run_stop_logs(c: types.CallbackQuery):
    uid = c.from_user.id
    parts = c.data.split(":")
    cmd = parts[0]; proj = parts[1]; fname = parts[2]
    if cmd == "run":
        try:
            pid = start_user_process(uid, proj, fname)
            await c.message.answer(f"✅ Started `{fname}` (pid {pid})")
        except Exception as e:
            await c.message.answer(f"Start error: {e}")
    elif cmd == "stop":
        ok = stop_user_process(uid, proj, fname)
        await c.message.answer("Stopped." if ok else "Not running.")
    elif cmd == "logs":
        p = USERS_DIR / str(uid) / proj / f"{fname}.out.log"
        if p.exists():
            text = p.read_text(errors="ignore")[-4000:]
            await c.message.answer(f"Logs for {fname}:\n\n{text}")
        else:
            await c.message.answer("No logs yet.")
    await c.answer()

# ---------------- Admin Inline Handlers ----------------
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("admin:"))
async def cb_admin(c: types.CallbackQuery):
    uid = c.from_user.id
    if uid != OWNER_ID:
        await c.answer("Owner only", show_alert=True)
        return
    cmd = c.data.split(":",1)[1]
    if cmd == "main":
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton("👥 Users", callback_data="admin:users"),
               types.InlineKeyboardButton("⭐ Premium", callback_data="admin:premium"))
        kb.add(types.InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast"),
               types.InlineKeyboardButton("💾 Backup Now", callback_data="admin:backup"))
        kb.add(types.InlineKeyboardButton("🔧 Add Premium", callback_data="admin:add_premium"),
               types.InlineKeyboardButton("❌ Remove Premium", callback_data="admin:remove_premium"))
        kb.add(types.InlineKeyboardButton("🚫 Ban User", callback_data="admin:ban"),
               types.InlineKeyboardButton("✅ Unban User", callback_data="admin:unban"))
        kb.add(types.InlineKeyboardButton("📂 Backups (web)", callback_data="admin:backups"),
               types.InlineKeyboardButton("🛠 Manage Scripts", callback_data="admin:manage_scripts"))
        kb.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_home"))
        await c.message.edit_text("Admin Panel", reply_markup=kb)
        await c.answer()
        return
    if cmd == "backup":
        create_backup_and_rotate(USERS_DIR, BACKUPS_DIR, max_keep=20)
        await c.message.answer("Backup created.")
        await c.answer()
        return
    if cmd == "broadcast":
        await c.message.answer("Send broadcast message now (text):")
        STATE["awaiting_broadcast"] = True
        save_state()
        await c.answer()
        return
    if cmd == "users":
        users_list = list(STATE["users"].keys())
        await c.message.answer("Users:\n" + ("\n".join(users_list) if users_list else "No users"))
        await c.answer()
        return
    if cmd == "premium":
        await c.message.answer("Premium users:\n" + ("\n".join(STATE.get("premium", [])) if STATE.get("premium") else "No premium users"))
        await c.answer(); return
    if cmd == "add_premium":
        STATE.setdefault("awaiting_admin", {})[str(OWNER_ID)] = {"action": "add_premium"}
        save_state()
        await c.message.answer("Send user id to ADD premium for (just the numeric id).")
        await c.answer(); return
    if cmd == "remove_premium":
        STATE.setdefault("awaiting_admin", {})[str(OWNER_ID)] = {"action": "remove_premium"}
        save_state()
        await c.message.answer("Send user id to REMOVE premium for.")
        await c.answer(); return
    if cmd == "ban":
        STATE.setdefault("awaiting_admin", {})[str(OWNER_ID)] = {"action": "ban_user"}
        save_state()
        await c.message.answer("Send user id to BAN.")
        await c.answer(); return
    if cmd == "unban":
        STATE.setdefault("awaiting_admin", {})[str(OWNER_ID)] = {"action": "unban_user"}
        save_state()
        await c.message.answer("Send user id to UNBAN.")
        await c.answer(); return
    if cmd == "backups":
        admin_pw = os.getenv("ADMIN_PASSWORD","")
        if not admin_pw:
            await c.message.answer("Set ADMIN_PASSWORD env to use web backups list.")
        else:
            await c.message.answer(f"Open web backups: {BASE_URL}/admin/backups?pw={admin_pw}")
        await c.answer(); return
    if cmd == "manage_scripts":
        # list running procs
        st = load_json(str(STATE_FILE), {})
        procs = st.get("procs", {})
        text = "Running processes:\n"
        for uid_k, entries in procs.items():
            for key,info in entries.items():
                text += f"User {uid_k} - {key} - pid {info.get('pid')}\n"
        if not procs:
            text = "No running processes"
        await c.message.answer(text)
        await c.answer(); return

@dp.message_handler()
async def fallback(msg: types.Message):
    # broadcast handler
    if STATE.get("awaiting_broadcast") and msg.from_user.id == OWNER_ID:
        text = msg.text
        for uid in list(STATE["users"].keys()):
            try:
                asyncio.create_task(bot.send_message(int(uid), f"📢 Broadcast from owner:\n\n{text}"))
            except Exception as e:
                print("Broadcast error to", uid, e)
        STATE["awaiting_broadcast"] = False; save_state()
        await msg.reply("Broadcast sent.")
        return
    # default
    await msg.reply("Use the inline buttons or /start.")

# ---------------- Background tasks: periodic backup ----------------
async def background_tasks():
    while True:
        try:
            create_backup_and_rotate(USERS_DIR, BACKUPS_DIR, max_keep=20)
        except Exception as e:
            print("Backup error:", e)
        await asyncio.sleep(BACKUP_INTERVAL_MIN * 60)

def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def start_bot_and_web():
    t = Thread(target=run_flask, daemon=True)
    t.start()
    loop = asyncio.get_event_loop()
    loop.create_task(background_tasks())
    start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    start_bot_and_web()
