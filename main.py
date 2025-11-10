import os, logging, threading, time
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("aiogram").setLevel(logging.WARNING)

os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    open("data/state.json", "w").write("{}")

# Flask Web Panel
from web.app import app as flask_app

# Bot Core
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Handlers
from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers

# Fixes for auto-restore / auto-stop / backup loop
from utils.monitor import check_expired
from utils.backup import backup_projects
from utils.restore import restore_running_after_restart


def run_flask():
    logging.info(f"🌐 Web Panel Running on PORT {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)


def expire_checker():
    while True:
        try:
            check_expired()
        except Exception as e:
            logging.error(f"expire_checker error: {e}")
        time.sleep(60)


def backup_loop():
    while True:
        try:
            backup_projects()
        except Exception as e:
            logging.error(f"backup_loop error: {e}")
        time.sleep(600)  # ~10 minutes


def restore_on_boot():
    time.sleep(5)
    try:
        restore_running_after_restart()
        logging.info("✅ Auto-Restored Previous Running Projects")
    except Exception as e:
        logging.error(f"restore_on_boot error: {e}")


def start_services():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()
    threading.Thread(target=restore_on_boot, daemon=True).start()

    logging.info("🤖 Telegram Bot Started")
    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)
    start_services()
