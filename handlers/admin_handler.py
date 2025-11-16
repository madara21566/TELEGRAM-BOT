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
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
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
        if c.from_user.id != OWNER_ID: return
        st = load_json()
        users = st.get("users", {})
        txt = "👥 *Registered Users:*\n" + "\n".join(f"- `{x}`" for x in users.keys())
        await c.message.answer(txt, parse_mode="Markdown")
        await c.answer()

    # ===== BROADCAST FIXED =====
    @dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
    async def ask_broadcast(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        await c.message.answer("📢 Send your broadcast message now:")
        dp.register_message_handler(broadcast_handler, content_types=types.ContentType.ANY)
        await c.answer()

    async def broadcast_handler(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        st = load_json()
        users = list(st.get("users", {}).keys())
        sent = 0
        for uid in users:
            try:
                if msg.text:
                    await bot.send_message(int(uid), msg.text)
                elif msg.photo:
                    await bot.send_photo(int(uid), msg.photo[-1].file_id)
                elif msg.document:
                    await bot.send_document(int(uid), msg.document.file_id)
                sent += 1
            except: pass
        dp.message_handlers.unregister(broadcast_handler)
        await msg.reply(f"📨 Broadcast delivered to `{sent}` users.")

    @dp.callback_query_handler(lambda c: c.data == "admin_genkey")
    async def admin_genkey(c: types.CallbackQuery):
        await c.message.answer("Use:\n`/generate <days>`\nExample: `/generate 7`", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_keylist")
    async def admin_keylist(c: types.CallbackQuery):
        codes = list_redeem_codes()
        if not codes: return await c.message.answer("No active keys.")
        txt = "🗝 *Active Keys:*\n" + "\n".join(f"`{c}` → {i['days']} days" for c,i in codes.items())
        await c.message.answer(txt, parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_running")
    async def admin_running(c: types.CallbackQuery):
        st = load_json(); procs = st.get("procs",{})
        if not procs: return await c.message.answer("No running scripts.")
        lines=[]
        for uid,p in procs.items():
            for key,meta in p.items():
                proj=key.split(':')[0]
                lines.append(f"{uid} | {proj} | pid={meta.get('pid')}")
        await c.message.answer("\n".join(lines))
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_backup")
    async def admin_backup(c: types.CallbackQuery):
        last = backup_latest_path()
        txt = "No backups yet." if not last else f"Latest backup:\n`{last}`"
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("📦 Backup Now", callback_data="admin_backup_now"),
            InlineKeyboardButton("📤 Restore Latest", callback_data="admin_restore_latest")
        )
        await c.message.answer(txt, reply_markup=kb, parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_backup_now")
    async def admin_backup_now(c: types.CallbackQuery):
        path = backup_projects()
        await c.message.reply_document(open(path,"rb"), caption="Full backup created!")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_restore_latest")
    async def admin_restore_latest(c: types.CallbackQuery):
        last = backup_latest_path()
        if not last: return await c.message.answer("No backup found")
        restore_from_zip(last)
        await c.message.answer("Restored from backup.")
        await c.answer()

    # ====== FIXED BUTTON CLICK ======
    @dp.callback_query_handler(lambda c: c.data == "admin_start_script")
    async def on_start_btn(c: types.CallbackQuery):
        await c.message.answer("Run command:\n`/startproj <user_id> <project>`", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_stop_script")
    async def on_stop_btn(c: types.CallbackQuery):
        await c.message.answer("Run command:\n`/stopproj <user_id> <project>`", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_download_script")
    async def on_dl_btn(c: types.CallbackQuery):
        await c.message.answer("Run command:\n`/downloadproj <user_id> <project>`", parse_mode="Markdown")
        await c.answer()

    # ===== OWNER COMMANDS KEEPED SAME =====
    @dp.message_handler(commands=['startproj'])
    async def cmd_start(msg):
        if msg.from_user.id != OWNER_ID: return
        try:
            _, uid, proj = msg.text.split()
            start_script(int(uid), proj)
            await msg.reply(f"Started `{proj}` for `{uid}`")
        except: await msg.reply("Usage: /startproj <user_id> <project>")

    @dp.message_handler(commands=['stopproj'])
    async def cmd_stop(msg):
        if msg.from_user.id != OWNER_ID: return
        try:
            _, uid, proj = msg.text.split()
            stop_script(int(uid), proj)
            await msg.reply(f"Stopped `{proj}`")
        except: await msg.reply("Usage: /stopproj <user_id> <project>")

    @dp.message_handler(commands=['downloadproj'])
    async def cmd_dl(msg):
        if msg.from_user.id != OWNER_ID: return
        try:
            _, uid, proj = msg.text.split()
            proj_dir=_user_proj_dir(uid,proj)
            if not os.path.exists(proj_dir):
                return await msg.reply("Not exist.")
            tmp=f"/tmp/{uid}_{proj}.zip"
            with zipfile.ZipFile(tmp,"w") as a:
                for r,d,fs in os.walk(proj_dir):
                    for f in fs:
                        a.write(os.path.join(r,f),os.path.relpath(os.path.join(r,f),proj_dir))
            await msg.reply_document(open(tmp,"rb"), caption="Your requested script")
            os.remove(tmp)
        except: await msg.reply("Usage: /downloadproj <user_id> <project>")

    @dp.callback_query_handler(lambda c: c.data == "main_menu")
    async def back(c):
        from handlers.start_handler import main_menu, WELCOME
        await c.message.edit_text(WELCOME, reply_markup=main_menu(c.from_user.id))
        await c.answer()
