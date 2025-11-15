import os, time, shutil, zipfile

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import load_json, backup_latest_path, restore_from_zip, list_redeem_codes
from utils.backup import backup_projects
from utils.runner import start_script, stop_script

def _user_proj_dir(uid, proj):
    return os.path.join("data", "users", str(uid), proj)

def _admin_kb(owner_id, base_url):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("👥 User List", callback_data="admin_user_list"),
        InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"),
    )
    kb.add(
        InlineKeyboardButton("🔑 Generate Key", callback_data="admin_genkey"),
        InlineKeyboardButton("🗝 Key List", callback_data="admin_keylist"),
    )
    kb.add(
        InlineKeyboardButton("🟩 Running Scripts", callback_data="admin_running"),
        InlineKeyboardButton("📂 Backup Manager", callback_data="admin_backup"),
    )
    kb.add(
        InlineKeyboardButton("▶ Start Script", callback_data="admin_start_script"),
        InlineKeyboardButton("⛔ Stop Script", callback_data="admin_stop_script"),
    )
    kb.add(
        InlineKeyboardButton("⬇ Download Script", callback_data="admin_download_script"),
        InlineKeyboardButton("🌐 Dashboard", url=f"{base_url}/admin/dashboard?key={owner_id}"),
    )
    kb.add(
        InlineKeyboardButton("🔙 Back", callback_data="main_menu"),
    )
    return kb

def register_admin_handlers(dp, bot, OWNER_ID, BASE_URL):
    @dp.callback_query_handler(lambda c: c.data == "admin:main")
    async def admin_main(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return await c.answer("Owner only", show_alert=True)
        await c.message.edit_text("🛠 Admin Control Panel", reply_markup=_admin_kb(OWNER_ID, BASE_URL))
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_user_list")
    async def users(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        users = st.get("users", {})
        lines = ["👥 *Registered Users:*"]
        for uid in users.keys():
            lines.append(f"- `{uid}`")
        await c.message.answer("\n".join(lines), parse_mode="Markdown")

    # BROADCAST via /broadcast
    @dp.message_handler(commands=['broadcast'])
    async def broadcast_cmd(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return await msg.reply("Owner only")
        st = load_json()
        users = list(st.get("users", {}).keys())
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            return await msg.reply("Usage: /broadcast Your message here")
        payload = parts[1]
        sent = 0
        for uid in users:
            try:
                await bot.send_message(int(uid), payload, parse_mode="Markdown")
                sent += 1
            except Exception:
                pass
        await msg.reply(f"Broadcast sent to {sent} users.")

    @dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
    async def admin_broadcast(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        await c.message.answer("Use `/broadcast <text>` to send message to all users.", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_genkey")
    async def admin_genkey(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        await c.message.answer("Use `/generate <days>` to create a premium key. Example: `/generate 7`", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_keylist")
    async def admin_keylist(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        codes = list_redeem_codes()
        if not codes:
            return await c.message.answer("No active keys.")
        lines = ["🗝 *Active Keys:*"]
        for code, info in codes.items():
            lines.append(f"`{code}` → {info['days']} days")
        await c.message.answer("\n".join(lines), parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_running")
    async def admin_running(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        procs = st.get("procs", {})
        lines = []
        for uid, p in procs.items():
            for key, meta in p.items():
                proj = key.split(':')[0]
                lines.append(f"{uid} | {proj} | pid={meta.get('pid')}")
        await c.message.answer("\n".join(lines) if lines else "No running scripts.")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_backup")
    async def admin_backup(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        last = backup_latest_path()
        text = "No backups found." if not last else f"Latest backup: `{last}`"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📦 Manual Backup Now", callback_data="admin_backup_now"))
        if last:
            kb.add(InlineKeyboardButton("📤 Restore Latest", callback_data="admin_restore_latest"))
            kb.add(InlineKeyboardButton("📥 Upload Backup", callback_data="admin_upload_backup"))
        await c.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_backup_now")
    async def admin_backup_now(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        path = backup_projects()
        await c.message.answer_document(open(path, "rb"), caption="Manual full backup")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_restore_latest")
    async def admin_restore_latest(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        last = backup_latest_path()
        if not last:
            return await c.message.answer("No backup.")
        restore_from_zip(last)
        await c.message.answer("Restored from latest backup. Restart bot if needed.")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_upload_backup")
    async def admin_upload_backup(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        await c.message.answer("Send the backup zip file now as DOCUMENT. It will be restored.")
        await c.answer()

        @dp.message_handler(content_types=types.ContentType.DOCUMENT)
        async def _backup_upload_handler(msg: types.Message):
            if msg.from_user.id != OWNER_ID:
                return
            path = f"data/backups/uploaded_{int(time.time())}.zip"
            await msg.document.download(destination_file=path)
            restore_from_zip(path)
            await msg.reply("Backup uploaded and restored. Please restart bot if needed.")

    # -------- OWNER RUN/STOP/DOWNLOAD ANY SCRIPT (COMMANDS) --------

    @dp.message_handler(commands=['startproj'])
    async def startproj_cmd(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return
        parts = msg.text.split()
        if len(parts) < 3:
            return await msg.reply("Usage: /startproj <user_id> <project_name>")
        uid = int(parts[1])
        proj = parts[2]
        try:
            start_script(uid, proj, None)
            await msg.reply(f"Started {proj} for user {uid}")
        except Exception as e:
            await msg.reply(f"Error: {e}")

    @dp.message_handler(commands=['stopproj'])
    async def stopproj_cmd(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return
        parts = msg.text.split()
        if len(parts) < 3:
            return await msg.reply("Usage: /stopproj <user_id> <project_name>")
        uid = int(parts[1])
        proj = parts[2]
        try:
            stop_script(uid, proj)
            await msg.reply(f"Stopped {proj} for user {uid}")
        except Exception as e:
            await msg.reply(f"Error: {e}")

    @dp.message_handler(commands=['downloadproj'])
    async def downloadproj_cmd(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return
        parts = msg.text.split()
        if len(parts) < 3:
            return await msg.reply("Usage: /downloadproj <user_id> <project_name>")
        uid = int(parts[1])
        proj = parts[2]
        proj_dir = _user_proj_dir(uid, proj)
        if not os.path.exists(proj_dir):
            return await msg.reply("Project not found.")
        tmp_zip = f"/tmp/{uid}_{proj}_project.zip"
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for r, d, fs in os.walk(proj_dir):
                for f in fs:
                    p = os.path.join(r, f)
                    z.write(p, os.path.relpath(p, proj_dir))
        await msg.reply_document(open(tmp_zip, "rb"), caption=f"Project {proj} of user {uid}")
        os.remove(tmp_zip)

    @dp.callback_query_handler(lambda c: c.data == "admin_start_script")
    async def admin_start_script(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        await c.message.answer("Use `/startproj <user_id> <project>` to start a script.", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_stop_script")
    async def admin_stop_script(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        await c.message.answer("Use `/stopproj <user_id> <project>` to stop a script.", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_download_script")
    async def admin_download_script(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        await c.message.answer("Use `/downloadproj <user_id> <project>` to download a script as ZIP.", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "main_menu")
    async def main_back(c: types.CallbackQuery):
        from handlers.start_handler import WELCOME, main_menu
        await c.message.edit_text(WELCOME, reply_markup=main_menu(c.from_user.id))
        await c.answer()
