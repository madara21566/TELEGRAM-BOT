import os
import io
import zipfile
import json
import shutil
import asyncio
import uuid
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
import docker
from docker.errors import APIError, ContainerError, ImageNotFound

load_dotenv()
TOKEN = os.getenv("TG_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("TG_BOT_TOKEN missing in .env")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
client = docker.from_env()

BASE_DIR = Path("projects")
BASE_DIR.mkdir(exist_ok=True)
META_FILE = BASE_DIR / "meta.json"

# load metadata
if META_FILE.exists():
    with open(META_FILE, "r") as f:
        meta = json.load(f)
else:
    meta = {}
    with open(META_FILE, "w") as f:
        json.dump(meta, f)

# Helpers
def save_meta():
    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

def gen_id():
    return uuid.uuid4().hex[:10]

def make_keyboard(project_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Start ▶️", callback_data=f"start:{project_id}"),
        InlineKeyboardButton("Stop ⏹️", callback_data=f"stop:{project_id}"),
    )
    kb.add(
        InlineKeyboardButton("Logs 📄", callback_data=f"logs:{project_id}"),
        InlineKeyboardButton("Status ℹ️", callback_data=f"status:{project_id}")
    )
    kb.add(InlineKeyboardButton("Delete 🗑️", callback_data=f"delete:{project_id}"))
    return kb

async def send_msg(chat_id, text):
    await bot.send_message(chat_id, text, parse_mode="HTML")

# When user sends a document (zip)
@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_zip(message: types.Message):
    doc = message.document
    if not doc.file_name.lower().endswith(".zip"):
        await message.reply("Kripya ek .zip file bhejein jo `main.py` aur `requirements.txt` contain kare.")
        return

    # download file
    file = await bot.get_file(doc.file_id)
    bytes_io = io.BytesIO()
    await bot.download_file(file.file_path, bytes_io)
    bytes_io.seek(0)

    # extract safe
    project_id = gen_id()
    project_dir = BASE_DIR / project_id
    project_dir.mkdir(parents=True)

    try:
        with zipfile.ZipFile(bytes_io) as z:
            # prevent zip slip
            for member in z.namelist():
                member_path = Path(member)
                if ".." in member_path.parts:
                    await message.reply("Zip contains illegal paths.")
                    shutil.rmtree(project_dir)
                    return
            z.extractall(project_dir)
    except zipfile.BadZipFile:
        shutil.rmtree(project_dir)
        await message.reply("Invalid ZIP file.")
        return

    # validate required files
    if not (project_dir / "main.py").exists():
        shutil.rmtree(project_dir)
        await message.reply("ZIP mein `main.py` nahi mila. Kripya usko include karein.")
        return

    # requirements.txt optional, but recommended
    # Save metadata
    meta[project_id] = {
        "owner": message.from_user.id,
        "owner_name": message.from_user.username or message.from_user.full_name,
        "dir": str(project_dir),
        "status": "uploaded",
        "container_id": None,
        "image_tag": None,
    }
    save_meta()

    kb = make_keyboard(project_id)
    await message.reply(f"Upload successful. Project id: <code>{project_id}</code>", reply_markup=kb, parse_mode="HTML")

# Callback handlers
@dp.callback_query_handler(lambda c: True)
async def cb_handler(callback_query: types.CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    if ":" not in data:
        await callback_query.answer()
        return
    action, project_id = data.split(":", 1)
    if project_id not in meta:
        await callback_query.answer("Project not found.", show_alert=True)
        return
    if meta[project_id]["owner"] != user_id:
        await callback_query.answer("You are not the owner of this project.", show_alert=True)
        return

    if action == "start":
        await callback_query.answer()
        await start_project(callback_query.message.chat.id, project_id)
    elif action == "stop":
        await callback_query.answer()
        await stop_project(callback_query.message.chat.id, project_id)
    elif action == "logs":
        await callback_query.answer()
        await send_logs(callback_query.message.chat.id, project_id)
    elif action == "status":
        await callback_query.answer()
        await send_status(callback_query.message.chat.id, project_id)
    elif action == "delete":
        await callback_query.answer()
        await delete_project(callback_query.message.chat.id, project_id)

# Core operations
async def start_project(chat_id, project_id):
    info = meta[project_id]
    project_dir = Path(info["dir"])
    # build image
    tag = f"userapp:{project_id}"
    try:
        # Use docker API build from folder
        # We pass Dockerfile.template content (already placed as Dockerfile)
        # Simplest: copy template into project dir as Dockerfile
        shutil.copy("Dockerfile.template", project_dir / "Dockerfile")
        # Build image
        await send_msg(chat_id, f"Building Docker image for <code>{project_id}</code> — this may take a while.",)
        image, logs = client.images.build(path=str(project_dir), tag=tag, rm=True)
        meta[project_id]["image_tag"] = tag
        save_meta()
    except (APIError, Exception) as e:
        await send_msg(chat_id, f"Build failed: <code>{str(e)}</code>")
        return

    # Run container with strict limits
    try:
        # Example limits: 256MB memory, 0.5 CPU, no network, read-only rootfs disabled for pip install
        container = client.containers.run(
            image=tag,
            detach=True,
            name=f"run_{project_id}",
            mem_limit="256m",
            cpu_quota=50000,  # 50,000 = 50% of single CPU; adjust per host
            network_disabled=True,
            stdin_open=False,
            tty=False,
            working_dir="/home/appuser/app",
            security_opt=["no-new-privileges"],
            pids_limit=64,
            # If you want to mount a tmpfs writable location: tmpfs={'/tmp': ''},
        )
        meta[project_id]["container_id"] = container.id
        meta[project_id]["status"] = "running"
        save_meta()
        kb = make_keyboard(project_id)
        await bot.send_message(chat_id, f"Container started for <code>{project_id}</code>. Container id: <code>{container.id[:12]}</code>", reply_markup=kb, parse_mode="HTML")
    except (APIError, ContainerError) as e:
        await send_msg(chat_id, f"Failed to run container: <code>{str(e)}</code>")

async def stop_project(chat_id, project_id):
    info = meta[project_id]
    cid = info.get("container_id")
    if not cid:
        await send_msg(chat_id, "No running container for this project.")
        return
    try:
        cont = client.containers.get(cid)
        cont.stop(timeout=3)
        cont.remove()
    except Exception as e:
        # ignore if already stopped
        pass
    meta[project_id]["container_id"] = None
    meta[project_id]["status"] = "stopped"
    save_meta()
    kb = make_keyboard(project_id)
    await bot.send_message(chat_id, f"Stopped container for <code>{project_id}</code>.", reply_markup=kb, parse_mode="HTML")

async def send_logs(chat_id, project_id):
    info = meta[project_id]
    cid = info.get("container_id")
    if not cid:
        await send_msg(chat_id, "No running container. Showing last 2000 chars of image logs (if any).")
        # try to get image logs via docker run logs? limited
        await send_msg(chat_id, "No logs available.")
        return
    try:
        cont = client.containers.get(cid)
        logs = cont.logs(tail=200, stream=False).decode(errors="ignore")
        # Telegram message limit ~4096; chunk if needed
        CHUNK = 3800
        if not logs:
            await send_msg(chat_id, "No logs yet.")
            return
        for i in range(0, len(logs), CHUNK):
            await bot.send_message(chat_id, f"<pre>{logs[i:i+CHUNK]}</pre>", parse_mode="HTML")
    except Exception as e:
        await send_msg(chat_id, f"Error getting logs: <code>{str(e)}</code>")

async def send_status(chat_id, project_id):
    info = meta[project_id]
    status = info.get("status", "unknown")
    cid = info.get("container_id")
    text = f"Project: <code>{project_id}</code>\nStatus: <b>{status}</b>\nImage: <code>{info.get('image_tag')}</code>\nContainer: <code>{(cid[:12] if cid else '—')}</code>"
    await bot.send_message(chat_id, text, parse_mode="HTML")

async def delete_project(chat_id, project_id):
    info = meta[project_id]
    # stop container if running
    cid = info.get("container_id")
    if cid:
        try:
            cont = client.containers.get(cid)
            cont.stop(timeout=2)
            cont.remove()
        except Exception:
            pass
    # remove image if exist
    tag = info.get("image_tag")
    if tag:
        try:
            client.images.remove(image=tag, force=True)
        except Exception:
            pass
    # remove files
    try:
        shutil.rmtree(info["dir"])
    except Exception:
        pass
    meta.pop(project_id, None)
    save_meta()
    await send_msg(chat_id, f"Project <code>{project_id}</code> deleted.",)

# On /start
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply("Hello! Send a ZIP containing `main.py` (and optional `requirements.txt`). Use inline buttons to Start/Stop/Logs/Status/Delete.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
