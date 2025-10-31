# bot.py - Telegram hosting bot with inline controls (Run / Stop / Restart bot / Logs / Files / Dashboard)
import os
import re
import sys
import json
import time
import shlex
import psutil
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ========== CONFIG ==========
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DISK_MOUNT = os.getenv("DISK_MOUNT", "/persistent")
WEB_DASHBOARD = os.getenv("WEB_DASHBOARD", "https://your-render-dashboard.example")  # set to your dashboard url
BASE_DIR = Path(DISK_MOUNT) / "users"
BASE_DIR.mkdir(parents=True, exist_ok=True)

PROCESS_MAP_FILE = Path(DISK_MOUNT) / "process_map.json"
if PROCESS_MAP_FILE.exists():
    try:
        PROCESS_MAP: Dict[str, Dict[str, Any]] = json.loads(PROCESS_MAP_FILE.read_text())
    except Exception:
        PROCESS_MAP = {}
else:
    PROCESS_MAP = {}


def save_map():
    try:
        PROCESS_MAP_FILE.write_text(json.dumps(PROCESS_MAP))
    except Exception as e:
        print("Failed to save process map:", e)


# ========== HELPERS ==========
def user_dir_for(uid: str) -> Path:
    d = BASE_DIR / uid
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_main_menu() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("📂 My Files", callback_data="files:show")],
        [
            InlineKeyboardButton("▶️ Run Script", callback_data="action:run"),
            InlineKeyboardButton("⛔ Stop Script", callback_data="action:stop"),
            InlineKeyboardButton("🔁 Restart Script", callback_data="action:restart_script")
        ],
        [InlineKeyboardButton("🧾 View Logs", callback_data="action:logs")],
        [InlineKeyboardButton("🌐 Web Dashboard", url=WEB_DASHBOARD)],
        [InlineKeyboardButton("♻️ Restart Bot (all users)", callback_data="bot:restart")]
    ]
    return InlineKeyboardMarkup(kb)


def build_file_buttons(uid: str) -> InlineKeyboardMarkup:
    d = user_dir_for(uid)
    files = [p.name for p in d.iterdir() if p.is_file()]
    kb = []
    if not files:
        kb = [[InlineKeyboardButton("No files uploaded", callback_data="noop")]]
    else:
        for f in files:
            kb.append([
                InlineKeyboardButton(f, callback_data=f"file:select:{f}")
            ])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:back")])
    return InlineKeyboardMarkup(kb)


def build_file_action_buttons(filename: str) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("▶️ Run", callback_data=f"run:{filename}"),
            InlineKeyboardButton("⛔ Stop", callback_data=f"stop:{filename}"),
            InlineKeyboardButton("🔁 Restart", callback_data=f"restart:{filename}")
        ],
        [
            InlineKeyboardButton("🧾 Logs", callback_data=f"logs:{filename}"),
            InlineKeyboardButton("📥 Download", callback_data=f"download:{filename}")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="files:show")]
    ]
    return InlineKeyboardMarkup(kb)


def tail_file(path: Path, limit_chars: int = 4000) -> str:
    try:
        if not path.exists():
            return "No output yet."
        text = path.read_text(errors="ignore")
        if len(text) <= limit_chars:
            return text
        else:
            return text[-limit_chars:]
    except Exception as e:
        return f"Failed to read logs: {e}"


# ========== SANDBOXED RUN HELPERS ==========
def detect_requirements(script_path: Path):
    req = script_path.with_name("requirements.txt")
    if req.exists():
        return req
    text = script_path.read_text(errors="ignore")
    imports = re.findall(r"^(?:from|import)\s+([A-Za-z0-9_\.]+)", text, flags=re.MULTILINE)
    return imports or []


def safe_preexec():
    # best-effort resource limits (Unix)
    try:
        import resource
        # CPU seconds
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        # Address space (bytes) - limit to ~700 MB
        resource.setrlimit(resource.RLIMIT_AS, (700 * 1024 * 1024, 700 * 1024 * 1024))
    except Exception:
        pass


def create_venv(user_dir: Path):
    venv_dir = user_dir / ".venv"
    if venv_dir.exists():
        return venv_dir
    rc = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], cwd=str(user_dir))
    if rc.returncode != 0:
        raise RuntimeError("Failed to create venv")
    return venv_dir


def install_requirements(pip_path: Path, reqs):
    if isinstance(reqs, Path):
        cmd = [str(pip_path), "install", "-r", str(reqs)]
    elif isinstance(reqs, list) and reqs:
        cmd = [str(pip_path), "install"] + reqs
    else:
        return  # nothing to install
    rc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if rc.returncode != 0:
        raise RuntimeError(rc.stderr.decode(errors="ignore")[:1000])


def start_user_script(uid: str, filename: str) -> int:
    """
    Start script for user in background, logging stdout/stderr to files.
    Returns pid.
    """
    user_dir = user_dir_for(uid)
    script = user_dir / filename
    if not script.exists():
        raise FileNotFoundError("Script not found")

    venv = create_venv(user_dir)
    pip_path = venv / "bin" / "pip"
    python_path = venv / "bin" / "python"

    # install inferred requirements if any
    reqs = detect_requirements(script)
    try:
        if isinstance(reqs, Path) or (isinstance(reqs, list) and reqs):
            install_requirements(pip_path, reqs)
    except Exception as e:
        # continue even if install fails; user will see error in logs
        print("Requirement install error:", e)

    stdout_f = user_dir / f"{filename}.out.log"
    stderr_f = user_dir / f"{filename}.err.log"

    # Launch subprocess detached (still track pid)
    with open(stdout_f, "ab") as outp, open(stderr_f, "ab") as errp:
        proc = subprocess.Popen(
            [str(python_path), str(script)],
            cwd=str(user_dir),
            stdout=outp,
            stderr=errp,
            preexec_fn=safe_preexec
        )
    # Record in PROCESS_MAP
    PROCESS_MAP.setdefault(uid, {})
    PROCESS_MAP[uid][filename] = {"pid": proc.pid, "start": time.time(), "out": str(stdout_f), "err": str(stderr_f)}
    save_map()
    return proc.pid


def stop_user_script(uid: str, filename: str) -> bool:
    ent = PROCESS_MAP.get(uid, {}).get(filename)
    if not ent:
        return False
    pid = ent.get("pid")
    try:
        p = psutil.Process(pid)
        p.terminate()
        p.wait(timeout=5)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    PROCESS_MAP[uid].pop(filename, None)
    save_map()
    return True


# ========== TELEGRAM HANDLERS ==========
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome — use the buttons below:", reply_markup=build_main_menu())


async def upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    uid = str(update.message.from_user.id)
    user_dir = user_dir_for(uid)
    dest = user_dir / doc.file_name
    await update.message.reply_text(f"Saving `{doc.file_name}` ...")
    f = await doc.get_file()
    await f.download_to_drive(str(dest))
    await update.message.reply_text(f"Saved `{doc.file_name}`", reply_markup=build_file_action_buttons(doc.file_name))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    uid = str(q.from_user.id)

    # Menu nav
    if data == "menu:back":
        await q.edit_message_text("Main menu", reply_markup=build_main_menu())
        return
    if data == "files:show":
        await q.edit_message_text("Your files:", reply_markup=build_file_buttons(uid))
        return
    if data.startswith("file:select:"):
        filename = data.split(":", 2)[2]
        await q.edit_message_text(f"File: {filename}", reply_markup=build_file_action_buttons(filename))
        return

    # Download request - we can't send file via edit, send file message
    if data.startswith("download:"):
        filename = data.split(":", 1)[1]
        p = user_dir_for(uid) / filename
        if p.exists():
            await q.message.reply_document(document=str(p))
        else:
            await q.message.reply_text("File not found.")
        return

    # Actions for a given file
    if data.startswith("run:") or data == "action:run":
        # if 'action:run' (generic) ask user to pick a file - show files
        if data == "action:run":
            await q.edit_message_text("Choose file to run:", reply_markup=build_file_buttons(uid))
            return
        filename = data.split(":", 1)[1]
        try:
            pid = start_user_script(uid, filename)
            await q.edit_message_text(f"Started `{filename}` (PID: {pid})", reply_markup=build_file_action_buttons(filename))
        except Exception as e:
            await q.edit_message_text(f"Failed to start: {e}")
        return

    if data.startswith("stop:") or data == "action:stop":
        if data == "action:stop":
            await q.edit_message_text("Choose file to stop:", reply_markup=build_file_buttons(uid))
            return
        filename = data.split(":", 1)[1]
        ok = stop_user_script(uid, filename)
        if ok:
            await q.edit_message_text(f"Stopped `{filename}`", reply_markup=build_file_action_buttons(filename))
        else:
            await q.edit_message_text("No running process found for that file.")
        return

    if data.startswith("restart:"):
        filename = data.split(":", 1)[1]
        # restart single file: stop then start
        try:
            stop_user_script(uid, filename)
            pid = start_user_script(uid, filename)
            await q.edit_message_text(f"Restarted `{filename}` (PID: {pid})", reply_markup=build_file_action_buttons(filename))
        except Exception as e:
            await q.edit_message_text(f"Failed to restart `{filename}`: {e}")
        return

    if data.startswith("logs:") or data == "action:logs":
        if data == "action:logs":
            await q.edit_message_text("Choose file to view logs:", reply_markup=build_file_buttons(uid))
            return
        filename = data.split(":", 1)[1]
        ent = PROCESS_MAP.get(uid, {}).get(filename, {})
        out_path = Path(ent.get("out")) if ent.get("out") else user_dir_for(uid) / f"{filename}.out.log"
        err_path = Path(ent.get("err")) if ent.get("err") else user_dir_for(uid) / f"{filename}.err.log"
        out_text = tail_file(out_path)
        err_text = tail_file(err_path)
        text = f"📄 Logs for `{filename}`\n\n-- STDOUT --\n{out_text}\n\n-- STDERR --\n{err_text}"
        # Telegram messages limited — we will send as text; if too big, truncate
        if len(text) > 3900:
            text = text[-3900:]
        await q.edit_message_text(text, reply_markup=build_file_action_buttons(filename))
        return

    # Bot restart (whole process)
    if data == "bot:restart":
        await q.edit_message_text("♻️ Restarting bot now... (this will restart the whole process and reset in-memory state)")
        # flush map to disk (already saved on operations) then execv
        save_map()
        # Give the message a moment to be delivered
        await asyncio.sleep(1.0)
        # Re-exec the Python process -> same argv
        python = sys.executable
        os.execv(python, [python] + sys.argv)
        return

    if data == "noop":
        await q.answer("No action.")
        return

    # Fallback
    await q.edit_message_text("Unknown action. Returning to menu.", reply_markup=build_main_menu())


async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use the buttons. /start to open menu.", reply_markup=build_main_menu())


# ========== APP SETUP ==========
def main():
    if TOKEN is None:
        print("TELEGRAM_BOT_TOKEN env var required")
        sys.exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, upload_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_handler))

    print("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
