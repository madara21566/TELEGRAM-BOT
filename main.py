import os, logging, threading, time, asyncio
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
BASE_URL = os.getenv('BASE_URL', '')
PORT = int(os.getenv('PORT', '10000'))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger('aiogram').setLevel(logging.ERROR)

os.makedirs('data/users', exist_ok=True)
os.makedirs('data/backups', exist_ok=True)
if not os.path.exists('data/state.json'):
    open('data/state.json', 'w').write('{}')

from web.app import app as flask_app
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

from handlers.start_handler import register_start_handlers
from handlers.project_handler import register_project_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.backup_handler import register_backup_handlers
from utils.monitor import check_expired, ensure_restart_on_boot
from utils.backup import backup_projects
from utils.helpers import backup_latest_path, restore_from_zip


# ---------------- FLASK SERVER ---------------- #
def run_flask():
    flask_app.run(host='0.0.0.0', port=PORT)


# ---------------- EXPIRY CHECK ---------------- #
def expire_checker():
    while True:
        try:
            check_expired()
        except Exception as e:
            logging.error(f'Expire Error: {e}')
        time.sleep(60)


# ---------------- AUTO BACKUP FIXED ---------------- #
async def auto_backup_send(path):
    try:
        with open(path, 'rb') as f:
            await bot.send_document(
                OWNER_ID, f,
                caption="📦 Auto Backup (Every 10 Minutes)"
            )
        logging.info("Backup sent to owner successfully!")
    except Exception as e:
        logging.error(f"Backup send failed: {e}")

async def auto_backup_loop():
    while True:
        try:
            path = backup_projects()
            logging.info("Backup created successfully.")
            await auto_backup_send(path)
        except Exception as e:
            logging.error(f"Backup error: {e}")
        await asyncio.sleep(600)


# ---------------- START ALL SERVICES ---------------- #
def start_services():
    try:
        last = backup_latest_path()
        if last:
            restore_from_zip(last)
            logging.info("Restored latest backup on startup.")
    except Exception as e:
        logging.error(f"Restore failed: {e}")

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()

    loop = asyncio.get_event_loop()
    loop.create_task(auto_backup_loop())

    try:
        ensure_restart_on_boot()
    except Exception as e:
        logging.error(f"Restart handler error: {e}")

    executor.start_polling(dp, skip_updates=True)


if __name__ == '__main__':
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)

    start_services()
