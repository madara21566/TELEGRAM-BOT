import os
import time
from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.helpers import (
    load_json,
    save_json,
    STATE_FILE,
    backup_latest_path,
    restore_from_zip,   # FIX 1
)
from utils.backup import backup_projects  # FIX 1


def register_backup_handlers(dp, bot, OWNER_ID, BASE_URL):  # FIX 2 (added BASE_URL)

    @dp.callback_query_handler(lambda c: c.data == "admin_backup")
    async def admin_backup(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return

        last = backup_latest_path()
        txt = "No backups yet." if not last else f"Latest Backup:\n`{last}`"

        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("📦 Backup Now", callback_data="admin_backup_now"),
            InlineKeyboardButton("♻ Restore Latest", callback_data="admin_restore_latest"),
        )
        kb.add(
            InlineKeyboardButton("📤 Upload Backup", callback_data="admin_backup_upload"),
        )

        await c.message.answer(txt, reply_markup=kb, parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_backup_now")
    async def admin_backup_now(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return

        path = backup_projects()
        await c.message.reply_document(open(path, "rb"), caption="Backup Created 😊")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_restore_latest")
    async def admin_restore_latest(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return

        last = backup_latest_path()
        if not last:
            return await c.message.answer("No backup found 😕")

        restore_from_zip(last)
        await c.message.answer("✔ Backup restored successfully 😊")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_backup_upload")
    async def upload_backup(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return

        st = load_json()
        st["awaiting_backup_upload"] = True
        save_json(STATE_FILE, st)

        await c.message.answer("📤 Send your backup `.zip` file now")
        await c.answer()

    @dp.message_handler(content_types=types.ContentType.DOCUMENT)
    async def receive_backup(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return

        st = load_json()
        if not st.get("awaiting_backup_upload"):
            return

        st["awaiting_backup_upload"] = False
        save_json(STATE_FILE, st)

        os.makedirs("data/backups", exist_ok=True)
        path = f"data/backups/uploaded_{int(time.time())}.zip"
        await msg.document.download(destination_file=path)

        try:
            restore_from_zip(path)
            await msg.reply("✔ Backup uploaded & restored! Restart bot if needed.")
        except Exception as e:
            await msg.reply(f"❌ Restore failed:\n\n`{e}`", parse_mode="Markdown")
