import os, time, shutil, zipfile
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import (
    load_json,
    save_json,
    STATE_FILE,
    backup_latest_path,
    restore_from_zip,
    list_redeem_codes,
)
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

    # =============== MAIN PANEL ===============

    @dp.callback_query_handler(lambda c: c.data == "admin:main")
    async def admin_main(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return await c.answer("Owner only", show_alert=True)
        await c.message.edit_text("🛠   Admin Control Panel", reply_markup=_admin_kb(OWNER_ID, BASE_URL))
        await c.answer()

    # =============== USER LIST ===============

    @dp.callback_query_handler(lambda c: c.data == "admin_user_list")
    async def users(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        users = st.get("users", {})
        if not users:
            await c.message.answer("No users yet.")
            return await c.answer()
        txt = "👥 *Registered Users:*\n" + "\n".join(f"- `{x}`" for x in users.keys())
        await c.message.answer(txt, parse_mode="Markdown")
        await c.answer()

    # =============== BROADCAST (BUTTON) ===============

    @dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
    async def ask_broadcast(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        await c.message.answer("📢 Send your broadcast message now (text / photo / document):")
        # one-time handler
        dp.register_message_handler(broadcast_handler, content_types=types.ContentType.ANY)
        await c.answer()

    async def broadcast_handler(msg: types.Message):
        # only owner allowed
        if msg.from_user.id != OWNER_ID:
            return

        st = load_json()
        users = list(st.get("users", {}).keys())
        sent = 0

        for uid in users:
            try:
                uid_int = int(uid)
                if msg.text:
                    await bot.send_message(uid_int, msg.text)
                elif msg.photo:
                    await bot.send_photo(uid_int, msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.document:
                    await bot.send_document(uid_int, msg.document.file_id, caption=msg.caption or "")
                sent += 1
            except:
                pass

        # unregister this handler after one use
        dp.message_handlers.unregister(broadcast_handler)
        await msg.reply(f"📨 Broadcast delivered to `{sent}` users.", parse_mode="Markdown")

    # =============== KEY GENERATION / LIST ===============

    @dp.callback_query_handler(lambda c: c.data == "admin_genkey")
    async def admin_genkey(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        await c.message.answer(
            "Use:\n`/generate <days>`\nExample: `/generate 7`",
            parse_mode="Markdown"
        )
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_keylist")
    async def admin_keylist(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        codes = list_redeem_codes()
        if not codes:
            return await c.message.answer("No active keys.")
        txt = "🗝 *Active Keys:*\n" + "\n".join(
            f"`{code}` → {info['days']} days" for code, info in codes.items()
        )
        await c.message.answer(txt, parse_mode="Markdown")
        await c.answer()

    # =============== RUNNING SCRIPTS LIST ===============

    @dp.callback_query_handler(lambda c: c.data == "admin_running")
    async def admin_running(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        procs = st.get("procs", {})
        if not procs:
            await c.message.answer("No running scripts.")
            return await c.answer()
        lines = []
        for uid, p in procs.items():
            for key, meta in p.items():
                proj = key.split(':')[0]
                lines.append(f"{uid} | {proj} | pid={meta.get('pid')}")
        await c.message.answer("\n".join(lines))
        await c.answer()

    # =============== BACKUP MANAGER ===============

    @dp.callback_query_handler(lambda c: c.data == "admin_backup")
    async def admin_backup(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        last = backup_latest_path()
        txt = "No backups yet." if not last else f"Latest backup:\n`{last}`"
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("📦 Backup Now", callback_data="admin_backup_now"),
            InlineKeyboardButton("♻ Restore Latest", callback_data="admin_restore_latest"),
        )
        kb.add(
            InlineKeyboardButton("⬆ Upload & Restore", callback_data="admin_backup_upload"),
        )
        await c.message.answer(txt, reply_markup=kb, parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_backup_now")
    async def admin_backup_now(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        path = backup_projects()
        await c.message.reply_document(open(path, "rb"), caption="Full backup created!")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin_restore_latest")
    async def admin_restore_latest(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        last = backup_latest_path()
        if not last:
            return await c.message.answer("No backup found")
        restore_from_zip(last)
        await c.message.answer("Restored from backup.")
        await c.answer()

    # ---- UPLOAD & RESTORE (OWNER SENDS ZIP) ----

    @dp.callback_query_handler(lambda c: c.data == "admin_backup_upload")
    async def admin_backup_upload(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        st["awaiting_backup_upload"] = True
        save_json(STATE_FILE, st)
        await c.message.answer(
            "Send your backup `.zip` file now as *DOCUMENT*.\n"
            "I'll restore everything from it.",
            parse_mode="Markdown"
        )
        await c.answer()

    @dp.message_handler(content_types=types.ContentType.DOCUMENT)
    async def handle_backup_upload(msg: types.Message):
        # Only owner + when flag is set
        if msg.from_user.id != OWNER_ID:
            return

        st = load_json()
        if not st.get("awaiting_backup_upload"):
            return  # normal document (e.g. project upload), let other handlers manage

        # Clear flag first
        st["awaiting_backup_upload"] = False
        save_json(STATE_FILE, st)

        os.makedirs("data/backups", exist_ok=True)
        path = f"data/backups/uploaded_{int(time.time())}.zip"
        await msg.document.download(destination_file=path)
        try:
            restore_from_zip(path)
            await msg.reply("✅ Backup uploaded and restored.\nIf needed, restart bot on Render.")
        except Exception as e:
            await msg.reply(f"❌ Restore failed: `{e}`", parse_mode="Markdown")

    # =============== START SCRIPT (BUTTON FLOW) ===============

    @dp.callback_query_handler(lambda c: c.data == "admin_start_script")
    async def admin_start_script(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        users = st.get("users", {})
        if not users:
            await c.message.answer("No users found.")
            return await c.answer()

        kb = InlineKeyboardMarkup(row_width=1)
        for uid in users.keys():
            kb.add(InlineKeyboardButton(f"User {uid}", callback_data=f"ss_user:{uid}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin:main"))

        await c.message.answer("Select user to *start* script:", parse_mode="Markdown", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("ss_user:"))
    async def ss_choose_user(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        uid = c.data.split(":", 1)[1]
        st = load_json()
        user = st.get("users", {}).get(uid, {})
        projects = user.get("projects", [])
        if not projects:
            await c.message.answer(f"User `{uid}` has no projects.", parse_mode="Markdown")
            return await c.answer()

        kb = InlineKeyboardMarkup(row_width=1)
        for proj in projects:
            kb.add(InlineKeyboardButton(proj, callback_data=f"ss_proj:{uid}:{proj}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_start_script"))

        await c.message.answer(f"Select project of user `{uid}` to *start*:", parse_mode="Markdown", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("ss_proj:"))
    async def ss_choose_project(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        _, uid, proj = c.data.split(":", 2)
        try:
            start_script(int(uid), proj)
            await c.message.answer(f"✅ Started `{proj}` for user `{uid}`", parse_mode="Markdown")
        except Exception as e:
            await c.message.answer(f"❌ Error starting `{proj}` for `{uid}`:\n`{e}`", parse_mode="Markdown")
        await c.answer()

    # =============== STOP SCRIPT (BUTTON FLOW) ===============

    @dp.callback_query_handler(lambda c: c.data == "admin_stop_script")
    async def admin_stop_script(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        users = st.get("users", {})
        if not users:
            await c.message.answer("No users found.")
            return await c.answer()

        kb = InlineKeyboardMarkup(row_width=1)
        for uid in users.keys():
            kb.add(InlineKeyboardButton(f"User {uid}", callback_data=f"st_user:{uid}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin:main"))

        await c.message.answer("Select user to *stop* script:", parse_mode="Markdown", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("st_user:"))
    async def st_choose_user(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        uid = c.data.split(":", 1)[1]
        st = load_json()
        user = st.get("users", {}).get(uid, {})
        projects = user.get("projects", [])
        if not projects:
            await c.message.answer(f"User `{uid}` has no projects.", parse_mode="Markdown")
            return await c.answer()

        kb = InlineKeyboardMarkup(row_width=1)
        for proj in projects:
            kb.add(InlineKeyboardButton(proj, callback_data=f"st_proj:{uid}:{proj}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_stop_script"))

        await c.message.answer(f"Select project of user `{uid}` to *stop*:", parse_mode="Markdown", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("st_proj:"))
    async def st_choose_project(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        _, uid, proj = c.data.split(":", 2)
        try:
            stop_script(int(uid), proj)
            await c.message.answer(f"⛔ Stopped `{proj}` for user `{uid}`", parse_mode="Markdown")
        except Exception as e:
            await c.message.answer(f"❌ Error stopping `{proj}` for `{uid}`:\n`{e}`", parse_mode="Markdown")
        await c.answer()

    # =============== DOWNLOAD SCRIPT (BUTTON FLOW) ===============

    @dp.callback_query_handler(lambda c: c.data == "admin_download_script")
    async def admin_download_script(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        users = st.get("users", {})
        if not users:
            await c.message.answer("No users found.")
            return await c.answer()

        kb = InlineKeyboardMarkup(row_width=1)
        for uid in users.keys():
            kb.add(InlineKeyboardButton(f"User {uid}", callback_data=f"dl_user:{uid}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin:main"))

        await c.message.answer("Select user to *download* project:", parse_mode="Markdown", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("dl_user:"))
    async def dl_choose_user(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        uid = c.data.split(":", 1)[1]
        st = load_json()
        user = st.get("users", {}).get(uid, {})
        projects = user.get("projects", [])
        if not projects:
            await c.message.answer(f"User `{uid}` has no projects.", parse_mode="Markdown")
            return await c.answer()

        kb = InlineKeyboardMarkup(row_width=1)
        for proj in projects:
            kb.add(InlineKeyboardButton(proj, callback_data=f"dl_proj:{uid}:{proj}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_download_script"))

        await c.message.answer(f"Select project of user `{uid}` to *download*:", parse_mode="Markdown", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("dl_proj:"))
    async def dl_choose_project(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        _, uid, proj = c.data.split(":", 2)
        proj_dir = _user_proj_dir(uid, proj)
        if not os.path.exists(proj_dir):
            await c.message.answer("Project not found.")
            return await c.answer()

        tmp = f"/tmp/{uid}_{proj}.zip"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for r, d, fs in os.walk(proj_dir):
                for f in fs:
                    p = os.path.join(r, f)
                    z.write(p, os.path.relpath(p, proj_dir))

        await c.message.reply_document(open(tmp, "rb"), caption=f"Project `{proj}` of user `{uid}`")
        os.remove(tmp)
        await c.answer()

    # =============== OWNER COMMANDS (KEEPED) ===============

    @dp.message_handler(commands=['startproj'])
    async def cmd_start(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return
        try:
            _, uid, proj = msg.text.split()
            start_script(int(uid), proj)
            await msg.reply(f"Started `{proj}` for `{uid}`", parse_mode="Markdown")
        except:
            await msg.reply("Usage: /startproj <user_id> <project>")

    @dp.message_handler(commands=['stopproj'])
    async def cmd_stop(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return
        try:
            _, uid, proj = msg.text.split()
            stop_script(int(uid), proj)
            await msg.reply(f"Stopped `{proj}`", parse_mode="Markdown")
        except:
            await msg.reply("Usage: /stopproj <user_id> <project>")

    @dp.message_handler(commands=['downloadproj'])
    async def cmd_dl(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return
        try:
            _, uid, proj = msg.text.split()
            proj_dir = _user_proj_dir(uid, proj)
            if not os.path.exists(proj_dir):
                return await msg.reply("Not exist.")
            tmp = f"/tmp/{uid}_{proj}.zip"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as a:
                for r, d, fs in os.walk(proj_dir):
                    for f in fs:
                        a.write(os.path.join(r, f), os.path.relpath(os.path.join(r, f), proj_dir))
            await msg.reply_document(open(tmp, "rb"), caption="Your requested script")
            os.remove(tmp)
        except:
            await msg.reply("Usage: /downloadproj <user_id> <project>")

    # =============== BACK BUTTON ===============

    @dp.callback_query_handler(lambda c: c.data == "main_menu")
    async def back(c: types.CallbackQuery):
        from handlers.start_handler import main_menu, WELCOME
        await c.message.edit_text(WELCOME, reply_markup=main_menu(c.from_user.id))
        await c.answer()
