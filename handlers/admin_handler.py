import os
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from utils.helpers import load_json, save_json, STATE_FILE, backup_latest_path, restore_from_zip, list_premium_users
from utils.backup import backup_projects

def _admin_kb(owner_id, base_url):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("👥 User List", callback_data="admin_user_list"),
           InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"))
    kb.add(InlineKeyboardButton("🟩 Running Scripts", callback_data="admin_running"),
           InlineKeyboardButton("📂 Backup Manager", callback_data="admin_backup"))
    kb.add(InlineKeyboardButton("🌐 Dashboard", url=f"{base_url}/admin/dashboard?key={owner_id}"),
           InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    return kb

def register_admin_handlers(dp, bot, OWNER_ID, BASE_URL):
    @dp.callback_query_handler(lambda c: c.data == "admin:main")
    async def admin_main(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return await c.answer("Owner only", show_alert=True)
        await c.message.edit_text("Admin Panel", reply_markup=_admin_kb(OWNER_ID, BASE_URL))
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_user_list")
    async def users(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        st = load_json()
        users = st.get("users",{})
        lines = ["Users:"]
        for uid in users.keys(): lines.append(str(uid))
        await c.message.answer("\n".join(lines))

    @dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
    async def admin_broadcast(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        await c.message.answer("Send the broadcast (text/photo/document) now. It will be sent to all users.")
        # dynamic handler registration; ensure only owner uses it
        dp.register_message_handler(lambda m: _broadcast_handler(m, bot), content_types=types.ContentType.ANY)

    async def _broadcast_handler(msg: types.Message, bot):
        if msg.from_user.id != OWNER_ID: return
        st = load_json()
        users = list(st.get("users",{}).keys())
        sent = 0
        for uid in users:
            try:
                if msg.text:
                    await bot.send_message(int(uid), msg.text, parse_mode='Markdown')
                elif msg.photo:
                    await bot.send_photo(int(uid), msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.document:
                    await bot.send_document(int(uid), msg.document.file_id, caption=msg.caption or "")
                sent +=1
            except Exception:
                pass
        await msg.reply(f"Broadcast sent to {sent} users.")

    @dp.callback_query_handler(lambda c: c.data == "admin_running")
    async def admin_running(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        st = load_json()
        procs = st.get("procs",{})
        if not procs: return await c.message.answer("No running scripts.")
        lines=[]
        for uid,p in procs.items():
            for key,meta in p.items():
                proj=key.split(':')[0]; lines.append(f"{uid} | {proj} | pid={meta.get('pid')}")
        await c.message.answer("\n".join(lines))

    @dp.callback_query_handler(lambda c: c.data == "admin_backup")
    async def admin_backup(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        last = backup_latest_path()
        text = "No backups found." if not last else f"Latest backup: {last}"
        kb = InlineKeyboardMarkup()
        if last:
            kb.add(InlineKeyboardButton("📤 Restore Latest", callback_data="admin_restore_latest"))
            kb.add(InlineKeyboardButton("📥 Upload Backup", callback_data="admin_upload_backup"))
        await c.message.answer(text, reply_markup=kb)

    @dp.callback_query_handler(lambda c: c.data == "admin_restore_latest")
    async def admin_restore_latest(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        last = backup_latest_path()
        if not last: return await c.message.answer("No backup.")
        restore_from_zip(last)
        await c.message.answer("Restored from latest backup. Restarting procs...")

    @dp.callback_query_handler(lambda c: c.data == "admin_upload_backup")
    async def admin_upload_backup(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        await c.message.answer("Send the backup zip file now as document. It will be restored when received.")
        dp.register_message_handler(lambda m: _backup_upload_handler(m), content_types=types.ContentType.DOCUMENT)

    async def _backup_upload_handler(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        path = f"data/backups/uploaded_{int(time.time())}.zip"
        await msg.document.download(destination_file=path)
        restore_from_zip(path)
        await msg.reply("Backup uploaded and restored. Please restart bot if needed.")

    @dp.callback_query_handler(lambda c: c.data == "main_menu")
    async def main_back(c: types.CallbackQuery):
        from handlers.start_handler import WELCOME, main_menu
        await c.message.edit_text(WELCOME, reply_markup=main_menu(c.from_user.id))
        await c.answer()
