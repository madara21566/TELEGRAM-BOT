# main.py

import os
import logging
import threading
import time
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
BASE_URL = os.getenv('BASE_URL', '')
PORT = int(os.getenv('PORT', '10000'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
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
from utils.backup import backup_projects, restore_latest_from_mongo
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

# ---------------- AUTO BACKUP (LOCAL + MONGO) ---------------- #
async def send_auto_backup(path):
    try:
        await bot.send_document(
            OWNER_ID,
            open(path, 'rb'),
            caption="📦 Auto Backup Completed (Every 10 Minutes)"
        )
        logging.info("Backup sent to owner successfully!")
    except Exception as e:
        logging.error(f"Backup send failed: {e}")


def backup_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            path = backup_projects()  # local zip + Mongo upload
            logging.info("Backup created successfully.")
            # owner ko bhi bhejo (optional)
            loop.run_until_complete(send_auto_backup(path))
        except Exception as e:
            logging.error(f"Backup error: {e}")
        time.sleep(600)  # 10 min

# ---------------- BOOT RESTORE + SERVICE START ---------------- #
def start_services():
    # 1) Try MongoDB se restore (agar configured)
    try:
        restored = restore_latest_from_mongo("data")
        if restored:
            logging.info("Restored from latest MongoDB backup at startup.")
        else:
            # 2) warna local backup se restore
            last = backup_latest_path()
            if last:
                restore_from_zip(last)
                logging.info("Restored from latest local backup at startup.")
    except Exception as e:
        logging.error(f"Restore failed: {e}")

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=expire_checker, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    try:
        ensure_restart_on_boot()
    except Exception as e:
        logging.error(f"Restart handler error: {e}")

    executor.start_polling(dp, skip_updates=True)

# ---------------- REGISTER HANDLERS ---------------- #
if __name__ == '__main__':
    register_start_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_project_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_admin_handlers(dp, bot, OWNER_ID, BASE_URL)
    register_backup_handlers(dp, bot, OWNER_ID, BASE_URL)

    start_services()
