import os, threading, asyncio, time
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "") or os.getenv("REPL_URL", "") or "http://localhost:8080"
PORT = int(os.getenv("PORT", os.getenv("RENDER_PORT", "10000")))
DATA_PATH = Path(os.getenv("DATA_PATH", "data")).resolve()
DATA_PATH.mkdir(parents=True, exist_ok=True)
USERS_DIR = DATA_PATH / "users"
BACKUPS_DIR = DATA_PATH / "backups"
STATE_FILE = DATA_PATH / "state.json"
USERS_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Start Flask app in background thread
from web.app import run_flask
t = threading.Thread(target=lambda: run_flask(port=PORT), daemon=True)
t.start()
print("🌐 Flask Web Server Started on port", PORT)

# Start aiogram bot
from aiogram import Bot, Dispatcher
from aiogram.utils.executor import start_polling
from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in environment")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

register_start_handlers(dp, bot, OWNER_ID)
register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)

# Background backup task
from utils.backup import create_backup_and_rotate

async def background_tasks():
    while True:
        try:
            create_backup_and_rotate(str(USERS_DIR), str(BACKUPS_DIR), max_keep=5)
        except Exception as e:
            print("Backup error:", e)
        await asyncio.sleep(int(os.getenv("BACKUP_INTERVAL", "10"))*60)

def start_bot():
    loop = asyncio.get_event_loop()
    loop.create_task(background_tasks())
    start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    start_bot()
