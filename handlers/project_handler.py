# handlers/project_handler.py

import os
import zipfile
import shutil
import tempfile
import time
import hmac
import hashlib
import asyncio
from datetime import datetime, timezone

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile

from utils.helpers import (
    load_json,
    save_json,
    ensure_state_user,
    STATE_FILE,
)
from utils.installer import (
    install_requirements_if_present,
    detect_imports_and_install,
)
from utils.runner import (
    start_script,
    stop_script,
    restart_script,
    read_logs,
    get_status,
)

BASE_URL = os.getenv("BASE_URL", "")
OWNER_ID = None  # register_project_handlers me set hoga


def _user_proj_dir(uid, proj):
    return os.path.join("data", "users", str(uid), proj)


def _fm_link(uid, proj):
    secret = (os.getenv("FILEMANAGER_SECRET") or "madara_secret_key_786").encode()
    ts = str(int(time.time()) // 3600)
    token = hmac.new(
        secret, f"{uid}:{proj}:{ts}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{BASE_URL}/fm?uid={uid}&proj={proj}&token={token}"


def project_kb(uid, proj):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("▶️ Run", callback_data=f"run::{proj}"),
        InlineKeyboardButton("⛔ Stop", callback_data=f"stop::{proj}"),
        InlineKeyboardButton("🔁 Restart", callback_data=f"restart::{proj}"),
    )
    kb.add(
        InlineKeyboardButton("📜 Logs", callback_data=f"logs::{proj}"),
        InlineKeyboardButton("📂 File Manager", url=_fm_link(uid, proj)),
        InlineKeyboardButton("🔄 Refresh", callback_data=f"status_refresh::{proj}"),
    )
    kb.add(
        InlineKeyboardButton(
            "⬇️ Download", url=f"{BASE_URL}/download/{uid}/{proj}"
        ),
        InlineKeyboardButton("🗑 Delete", callback_data=f"delete::{proj}"),
        InlineKeyboardButton("🔙 Back", callback_data="menu:my_projects"),
    )
    return kb


def status_text(uid, proj):
    st = load_json()
    procs_for_user = st.get("procs", {}).get(str(uid), {})
    entry = None
    for k, v in procs_for_user.items():
        if k.startswith(f"{proj}:"):
            entry = v
            break

    s = get_status(uid, proj)
    running = s.get("running", False)
    pid = s.get("pid") or "N/A"

    if entry:
        start_ts = entry.get("start", 0)
        uptime = int(time.time() - start_ts) if start_ts else 0
        h = uptime // 3600
        m = (uptime % 3600) // 60
        s2 = uptime % 60
        last_run = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        cmd = entry.get("cmd", "python3 main.py")
        return (
            f"FASTBOT Status for `{proj}`\n\n"
            f"Status: {'🟢 Running' if running else '🔴 Stopped'}\n"
            f"PID: `{pid}`\n"
            f"Uptime: `{h:02d}:{m:02d}:{s2:02d}`\n"
            f"Last Run: `{last_run}`\n"
            f"Run Command: `{cmd}`"
        )
    else:
        return (
            f"FASTBOT Status for `{proj}`\n\n"
            f"Status: {'🟢 Running' if running else '🔴 Stopped'}\n"
            f"PID: `{pid if running else 'N/A'}`\n"
            f"Uptime: `N/A`\n"
            f"Last Run: `Never`\n"
            f"Run Command: `auto-detected`"
        )


async def _clean_progress(messages):
    for m in messages:
        try:
            await m.delete()
        except:
            pass


def _extract_zip(zip_path, dest):
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest)

    # Agar zip ke andar ek hi root folder ho toh usko flatten kar do
    while True:
        items = os.listdir(dest)
        if len(items) == 1 and os.path.isdir(os.path.join(dest, items[0])):
            inner = os.path.join(dest, items[0])
            for fn in os.listdir(inner):
                shutil.move(os.path.join(inner, fn), os.path.join(dest, fn))
            shutil.rmtree(inner, ignore_errors=True)
        else:
            break


def register_project_handlers(dp, bot, owner_id, base_url):
    global BASE_URL, OWNER_ID
    BASE_URL = base_url
    OWNER_ID = owner_id

    # -------------- NEW PROJECT START --------------

    @dp.callback_query_handler(lambda c: c.data == "deploy:start")
    async def start_deploy(c: types.CallbackQuery):
        st = ensure_state_user(c.from_user.id)
        awaiting = st.setdefault("awaiting_name", {})
        awaiting[str(c.from_user.id)] = True
        save_json(STATE_FILE, st)

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔙 Back", callback_data="menu:my_projects")
        )
        await c.message.edit_text("Send your project name:", reply_markup=kb)
        await c.answer()

    @dp.message_handler(content_types=types.ContentType.TEXT)
    async def receive_name(msg: types.Message):
        st = load_json()
        if not st.get("awaiting_name", {}).get(str(msg.from_user.id)):
            return

        name = msg.text.strip().replace(" ", "_")
        st["awaiting_name"].pop(str(msg.from_user.id), None)

        users = st.setdefault("users", {})
        u = users.setdefault(str(msg.from_user.id), {})
        projects = u.setdefault("projects", [])

        # free/premium limit
        is_prem = str(msg.from_user.id) in st.get("premium_users", {})
        limit = 10 if is_prem else 2
        if len(projects) >= limit:
            return await msg.answer("⚠️ Project limit reached. Upgrade to premium.")

        if name not in projects:
            projects.append(name)

        save_json(STATE_FILE, st)
        os.makedirs(_user_proj_dir(msg.from_user.id, name), exist_ok=True)

        await msg.answer(
            f"✅ Project `{name}` created.\n"
            f"Now send your `.py` or `.zip` file as DOCUMENT.",
            parse_mode="Markdown",
        )

    # -------------- PROJECT / BACKUP DOCUMENT UPLOAD --------------

    @dp.message_handler(content_types=types.ContentType.DOCUMENT)
    async def receive_doc(msg: types.Message):
        """
        Yahin pe do kaam hote hain:
        1) Agar admin backup upload mode ON ho → project upload ignore, admin_handler handle karega.
        2) Warna ye normal project upload handle karega.
        """
        st = load_json()

        # 🔥 1) Backup upload mode: isko yahan se skip karo, admin_handler handle karega
        if st.get("awaiting_backup_upload") and msg.from_user.id == OWNER_ID:
            # NOTE: is message ko admin_handler.handle_backup_upload hi process karega
            return

        # 2) Normal project upload
        uid = msg.from_user.id
        projects = st.get("users", {}).get(str(uid), {}).get("projects", [])
        if not projects:
            await msg.reply("Create a project first with New Project.")
            return

        proj = projects[-1]  # last created project
        base = _user_proj_dir(uid, proj)
        os.makedirs(base, exist_ok=True)

        m1 = await msg.reply("📥 Processing project...")
        filepath = os.path.join(base, msg.document.file_name)
        await msg.document.download(destination_file=filepath)

        m2 = await msg.reply("🔧 Extracting / saving files...")
        if filepath.lower().endswith(".zip"):
            try:
                _extract_zip(filepath, base)
                os.remove(filepath)
            except Exception as e:
                await msg.reply(f"Zip error: `{e}`", parse_mode="Markdown")
                return

        m3 = await msg.reply("⚙️ Installing dependencies...")

        # Heavy work ko background thread me daal dete hain taaki bot freeze na ho
        loop = asyncio.get_event_loop()

        async def _install():
            if os.path.exists(os.path.join(base, "requirements.txt")):
                await loop.run_in_executor(
                    None, install_requirements_if_present, base
                )
            else:
                py = None
                for n in os.listdir(base):
                    if n.endswith(".py"):
                        py = os.path.join(base, n)
                        break
                if py:
                    await loop.run_in_executor(
                        None, detect_imports_and_install, py
                    )

        try:
            await _install()
        except Exception as e:
            await msg.reply(f"Deps install error: `{e}`", parse_mode="Markdown")

        await _clean_progress([m1, m2, m3])

        # --- Upload complete message ko spam se bachao ---
        st = load_json()
        lu = st.setdefault("last_upload_msg_ts", {})
        now = int(time.time())
        last_ts = int(lu.get(str(uid), 0))

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📂 MY PROJECTS", callback_data="menu:my_projects")
        )

        # Agar 10 second ke andar already message bhej diya tha toh dobara mat bhejo
        if now - last_ts > 10:
            lu[str(uid)] = now
            save_json(STATE_FILE, st)
            await msg.reply(
                "🎉 Upload complete!\nGo to *MY PROJECTS* to run and manage.",
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            # sirf quietly update timestamp, extra spam nahi
            lu[str(uid)] = now
            save_json(STATE_FILE, st)

    # -------------- MY PROJECTS MENU --------------

    @dp.callback_query_handler(lambda c: c.data == "menu:my_projects")
    async def my_projects(c: types.CallbackQuery):
        st = load_json()
        projs = st.get("users", {}).get(str(c.from_user.id), {}).get(
            "projects", []
        )
        kb = InlineKeyboardMarkup(row_width=1)
        for p in projs:
            kb.add(InlineKeyboardButton(p, callback_data=f"proj:open:{p}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="back_home"))
        await c.message.edit_text("Your Projects:", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("proj:open:"))
    async def open_proj(c: types.CallbackQuery):
        proj = c.data.split(":", 2)[2]
        await c.message.edit_text(
            status_text(c.from_user.id, proj),
            reply_markup=project_kb(c.from_user.id, proj),
            parse_mode="Markdown",
        )
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("status_refresh::"))
    async def refresh(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        await c.message.edit_text(
            status_text(c.from_user.id, proj),
            reply_markup=project_kb(c.from_user.id, proj),
            parse_mode="Markdown",
        )
        await c.answer("Refreshed")

    # -------------- RUN / STOP / RESTART / LOGS / DELETE --------------

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("run::"))
    async def run_cb(c: types.CallbackQuery):
        uid = c.from_user.id
        proj = c.data.split("::", 1)[1]
        await c.message.answer("🚀 Launching project...")
        try:
            start_script(uid, proj, None)
            await c.message.answer(
                status_text(uid, proj),
                reply_markup=project_kb(uid, proj),
                parse_mode="Markdown",
            )
        except Exception as e:
            await c.message.answer(f"Start error: `{e}`", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("stop::"))
    async def stop_cb(c: types.CallbackQuery):
        uid = c.from_user.id
        proj = c.data.split("::", 1)[1]
        try:
            stop_script(uid, proj)
            await c.message.answer("⛔ Stopped.")
        except Exception as e:
            await c.message.answer(f"Stop error: `{e}`", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("restart::"))
    async def restart_cb(c: types.CallbackQuery):
        uid = c.from_user.id
        proj = c.data.split("::", 1)[1]
        try:
            restart_script(uid, proj, None)
            await c.message.answer("🔁 Restarted.")
        except Exception as e:
            await c.message.answer(f"Restart error: `{e}`", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("logs::"))
    async def logs_cb(c: types.CallbackQuery):
        uid = c.from_user.id
        proj = c.data.split("::", 1)[1]
        content = read_logs(uid, proj, lines=500)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        with open(tmp.name, "w", encoding="utf-8") as f:
            f.write(content or "")
        await c.message.answer_document(
            InputFile(tmp.name, filename=f"{proj}_logs.txt")
        )
        os.unlink(tmp.name)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("delete::"))
    async def delete_cb(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(
                "✅ Confirm Delete", callback_data=f"confirm_delete::{proj}"
            ),
            InlineKeyboardButton("❌ Cancel", callback_data=f"proj:open:{proj}"),
        )
        await c.message.edit_text(
            f"⚠️ Delete project `{proj}`?", parse_mode="Markdown", reply_markup=kb
        )
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith("confirm_delete::"))
    async def confirm_delete(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        try:
            shutil.rmtree(_user_proj_dir(c.from_user.id, proj), ignore_errors=True)
            st = load_json()
            lst = (
                st.get("users", {})
                .get(str(c.from_user.id), {})
                .get("projects", [])
            )
            if proj in lst:
                lst.remove(proj)
            save_json(STATE_FILE, st)
            await c.message.edit_text(
                f"🗑 Project `{proj}` deleted.", parse_mode="Markdown"
            )
        except Exception as e:
            await c.message.edit_text(f"Delete failed: `{e}`", parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "back_home")
    async def back_home(c: types.CallbackQuery):
        from handlers.start_handler import WELCOME, main_menu

        await c.message.edit_text(
            WELCOME, reply_markup=main_menu(c.from_user.id)
        )
        await c.answer()
