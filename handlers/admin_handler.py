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
    
    # === MAIN ===
    @dp.callback_query_handler(lambda c: c.data == "admin:main")
    async def admin_main(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return await c.answer("Owner only!", show_alert=True)
        await c.message.edit_text("🛠 Admin Control Panel", reply_markup=_admin_kb(OWNER_ID, BASE_URL))
        await c.answer()

    # === USER LIST ===
    @dp.callback_query_handler(lambda c: c.data == "admin_user_list")
    async def users(c: types.CallbackQuery):
        st = load_json()
        users = st.get("users", {})
        if not users: 
            return await c.message.answer("No registered users!")
        txt = "👥 *Registered Users:*\n" + "\n".join(f"`{u}`" for u in users.keys())
        await c.message.answer(txt, parse_mode="Markdown")
        await c.answer()

    # ===========================
    # ✔ BROADCAST FULL FIX HERE ✔
    # ===========================

    @dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
    async def admin_broadcast(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        await c.message.answer("📢 Send broadcast message now\n(text/photo/document):")
        dp.register_message_handler(broadcast_handler, content_types=types.ContentType.ANY)
        await c.answer()

    async def broadcast_handler(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return  # Ignore others

        st = load_json()
        user_list = list(st.get("users", {}).keys())
        sent = 0

        for uid in user_list:
            try:
                if msg.text:
                    await bot.send_message(int(uid), msg.text)
                elif msg.photo:
                    await bot.send_photo(int(uid), msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.document:
                    await bot.send_document(int(uid), msg.document.file_id, caption=msg.caption or "")
                sent += 1
            except:
                pass

        # remove handler after work 🍫
        dp.message_handlers.unregister(broadcast_handler)

        await msg.reply(f"📨 Broadcast delivered to `{sent}` users.")

    # ===== KEY GENERATION =====
    @dp.callback_query_handler(lambda c: c.data == "admin_genkey")
    async def genkey(c):
        await c.message.answer("Use `/generate <days>` Example: `/generate 7`")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_keylist")
    async def keylist(c):
        keys = list_redeem_codes()
        if not keys: return await c.message.answer("No active keys.")
        txt = "🗝 *Active Keys:*\n" + "\n".join(f"`{k}` → {i['days']} days" for k,i in keys.items())
        await c.message.answer(txt, parse_mode="Markdown")
        await c.answer()

    # ===== Running Scripts =====
    @dp.callback_query_handler(lambda c: c.data == "admin_running")
    async def run(c):
        st = load_json()
        procs = st.get("procs", {})
        if not procs: return await c.message.answer("No scripts running.")
        lines = []
        for uid,p in procs.items():
            for k,m in p.items():
                proj=k.split(":")[0]
                lines.append(f"{uid} | {proj} | pid={m.get('pid')}")
        await c.message.answer("\n".join(lines))
        await c.answer()

    # ===== Backup =====
    @dp.callback_query_handler(lambda c: c.data == "admin_backup")
    async def backup(c):
        last = backup_latest_path()
        txt = "No backup found!" if not last else f"Latest backup: `{last}`"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📦 Backup Now", callback_data="admin_backup_now"))
        kb.add(InlineKeyboardButton("📤 Restore", callback_data="admin_restore_latest"))
        await c.message.answer(txt, reply_markup=kb, parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_backup_now")
    async def manual(c):
        path = backup_projects()
        await c.message.answer_document(open(path,"rb"), caption="Backup done ✔")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_restore_latest")
    async def restore(c):
        last = backup_latest_path()
        if not last: return await c.message.answer("Backup missing!")
        restore_from_zip(last)
        await c.message.answer("Backup restored ✔")
        await c.answer()

    # ===== Quick Menu Help for Owner Commands =====
    @dp.callback_query_handler(lambda c: c.data.startswith("admin_"))
    async def show_cmd(c):
        cmds = {
            "admin_start_script": "`/startproj <user_id> <project>`",
            "admin_stop_script": "`/stopproj <user_id> <project>`",
            "admin_download_script": "`/downloadproj <user_id> <project>`",
        }
        cmd = cmds.get(c.data)
        if cmd:
            await c.message.answer(f"Run command:\n{cmd}", parse_mode="Markdown")
        await c.answer()

    # === Owner commands (RUN/STOP/DOWNLOAD) ===
    @dp.message_handler(commands=['startproj'])
    async def startp(msg):
        if msg.from_user.id != OWNER_ID: return
        try:
            _, uid, proj = msg.text.split()
            start_script(int(uid), proj)
            await msg.reply(f"Started `{proj}` for user `{uid}`")
        except:
            await msg.reply("❌ Usage: /startproj <uid> <project>")

    @dp.message_handler(commands=['stopproj'])
    async def stopp(msg):
        if msg.from_user.id != OWNER_ID: return
        try:
            _, uid, proj = msg.text.split()
            stop_script(int(uid), proj)
            await msg.reply(f"Stopped `{proj}` for `{uid}`")
        except:
            await msg.reply("❌ Usage: /stopproj <uid> <project>")

    @dp.message_handler(commands=['downloadproj'])
    async def dl(msg):
        if msg.from_user.id != OWNER_ID: return
        try:
            _, uid, proj = msg.text.split()
            proj_dir=_user_proj_dir(uid,proj)
            if not os.path.exists(proj_dir):
                return await msg.reply("❌ Not found.")
            zipf=f"/tmp/{uid}_{proj}.zip"
            with zipfile.ZipFile(zipf,"w") as z:
                for r,_,fs in os.walk(proj_dir):
                    for f in fs:
                        z.write(os.path.join(r,f), os.path.relpath(os.path.join(r,f),proj_dir))
            await msg.reply_document(open(zipf,"rb"), caption="📦 Script Exported")
            os.remove(zipf)
        except:
            await msg.reply("❌ Usage: /downloadproj <uid> <project>")

    # === BACK BUTTON ===
    @dp.callback_query_handler(lambda c: c.data == "main_menu")
    async def back(c):
        from handlers.start_handler import main_menu, WELCOME
        await c.message.edit_text(WELCOME, reply_markup=main_menu(c.from_user.id))
        await c.answer()
