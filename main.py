import os, logging, threading, time, asyncio
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
BASE_URL = os.getenv('BASE_URL', '')
PORT = int(os.getenv('PORT', '10000'))

logging.basicConfig(level=logging.INFO)
logging.getLogger("aiogram").setLevel(logging.WARNING)

os.makedirs("data/users", exist_ok=True)
os.makedirs("data/backups", exist_ok=True)
if not os.path.exists("data/state.json"):
    open("data/state.json", "w").write("{}")

from web.app import app as flask_app
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from utils.monitor import check_expired, ensure_restart_on_boot
from utils.backup import backup_projects, backup_latest_path, restore_from_zip


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


def expire_checker():
    while True:
        try:
            check_expired()
        except Exception as e:
            logging.error(e)
        time.sleep(60)


async def auto_backup_task():
    while True:
        try:
            path = backup_projects()
            await bot.send_document(
                OWNER_ID,
                open(path, "rb"),
                caption="📦 Auto Backup Completed (Every 10 min)"
            )
        except Exception as e:
            logging.error(f"Auto Backup Error: {e}")
        await asyncio.sleep(600)


def start_async_tasks():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(auto_backup_task())


def start_services():
    try:
        last_backup = backup_latest_path()
        users_exist = os.listdir("data/users")
        if last_backup and not users_exist:
            restore_from_zip(last_backup)
            logging.info("Restored last backup at boot!")
    except Exception as e:
        logging.error(e)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=start_async_tasks, daemon=True).start()

    ensure_restart_on_boot()

    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)

    start_services()
