import os, zipfile, shutil, tempfile, time, hmac, hashlib
from datetime import datetime, timezone

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile

from utils.helpers import (
    load_json,
    save_json,
    ensure_state_user,
    STATE_FILE,
    is_premium
)

from utils.installer import install_requirements_if_present, detect_imports_and_install
from utils.runner import start_script, stop_script, restart_script, read_logs, get_status

BASE_URL = os.getenv("BASE_URL", "")

# ----------------------- PATH HELPERS ----------------------- #

def user_project_dir(uid, proj):
    return os.path.join("data", "users", str(uid), proj)


def file_manager_link(uid, proj):
    """
    Generates a secure HMAC link for web file manager.
    Link rotates every hour.
    """
    secret = (os.getenv("FILEMANAGER_SECRET") or "madara_secret_key_786").encode()
    ts = str(int(time.time()) // 3600)
    token = hmac.new(secret, f"{uid}:{proj}:{ts}".encode(), hashlib.sha256).hexdigest()
    return f"{BASE_URL}/fm?uid={uid}&proj={proj}&token={token}"


# ----------------------- INLINE KEYBOARD ----------------------- #

def project_keyboard(uid, proj):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("▶️ Run", callback_data=f"run::{proj}"),
        InlineKeyboardButton("⏹ Stop", callback_data=f"stop::{proj}"),
        InlineKeyboardButton("🔁 Restart", callback_data=f"restart::{proj}")
    )
    kb.add(
        InlineKeyboardButton("📜 Logs", callback_data=f"logs::{proj}"),
        InlineKeyboardButton("📂 File Manager", url=file_manager_link(uid, proj)),
        InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh::{proj}")
    )
    kb.add(
        InlineKeyboardButton("⬇️ Download", url=f"{BASE_URL}/download/{uid}/{proj}"),
        InlineKeyboardButton("🗑 Delete", callback_data=f"delete::{proj}"),
        InlineKeyboardButton("🔙 Back", callback_data="menu:projects")
    )
    return kb


# ----------------------- STATUS FORMAT ----------------------- #

def project_status(uid, proj):
    st = load_json()
    proc_info = st.get("procs", {}).get(str(uid), {})

    entry = None
    for k, v in proc_info.items():
        if k.startswith(f"{proj}:"):
            entry = v
            break

    s = get_status(uid, proj)
    running = s["running"]
    pid = s["pid"] or "N/A"

    if entry:
        start_ts = entry.get("start", 0)
        uptime = int(time.time() - start_ts) if start_ts else 0
        h = uptime // 3600
        m = (uptime % 3600) // 60
        sec = uptime % 60

        last_run = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        cmd = entry.get("cmd", "python3 main.py")

        return (
            f"Project Status for {proj}\n\n"
            f"🔹 Status: {'🟢 Running' if running else '🔴 Stopped'}\n"
            f"🔹 PID: {pid}\n"
            f"🔹 Uptime: {h:02d}:{m:02d}:{sec:02d}\n"
            f"🔹 Last Run: {last_run}\n"
            f"🔹 Run Command: {cmd}"
        )

    return (
        f"Project Status for {proj}\n\n"
        f"🔹 Status: {'🟢 Running' if running else '🔴 Stopped'}\n"
        f"🔹 PID: {pid}\n"
        f"🔹 Uptime: {'N/A' if not running else '00:00:00'}\n"
        f"🔹 Last Run: Never\n"
        f"🔹 Run Command: auto-detected"
    )


# ----------------------- CLEAN MESSAGE HELP ----------------------- #

async def clean_messages(msgs):
    for m in msgs:
        try:
            await m.delete()
        except Exception:
            pass


# ----------------------- MAIN REGISTER FUNCTION ----------------------- #

def register_project_handlers(dp, bot, owner_id, base_url):
    global BASE_URL
    BASE_URL = base_url

    # ---------------- NEW PROJECT ---------------- #

    @dp.callback_query_handler(lambda c: c.data == "project:new")
    async def new_project_start(c: types.CallbackQuery):
        st = ensure_state_user(c.from_user.id)
        st.setdefault("await_name", {})[str(c.from_user.id)] = True
        save_json(STATE_FILE, st)

        await c.message.edit_text(
            "📌 Send your **project name**:",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Back", callback_data="menu:projects")
            ),
            parse_mode="Markdown"
        )
        await c.answer()

    @dp.message_handler(content_types=types.ContentType.TEXT)
    async def receive_project_name(msg: types.Message):
        st = load_json()
        uid = str(msg.from_user.id)

        # Waiting for project name
        if st.get("await_name", {}).get(uid):
            name = msg.text.strip().replace(" ", "_")

            st["await_name"].pop(uid, None)
            st.setdefault("users", {}).setdefault(uid, {}).setdefault("projects", [])

            # LIMIT CHECK — FREE / PREMIUM
            max_allowed = 10 if is_premium(uid) else 2
            current_count = len(st["users"][uid]["projects"])

            if current_count >= max_allowed:
                await msg.reply(f"⚠️ Project limit reached ({max_allowed}). Upgrade to Premium for 10 projects.")
                return

            # Create project
            if name not in st["users"][uid]["projects"]:
                st["users"][uid]["projects"].append(name)

            save_json(STATE_FILE, st)

            os.makedirs(user_project_dir(uid, name), exist_ok=True)

            await msg.answer(
                f"✅ Project `{name}` created.\n\nNow send your **.py** or **.zip** file.",
                parse_mode="Markdown"
            )
            return

    # ---------------- ZIP EXTRACT ---------------- #

    def extract_zip(zip_path, dest):
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(dest)

        items = os.listdir(dest)
        if len(items) == 1 and os.path.isdir(os.path.join(dest, items[0])):
            inner = os.path.join(dest, items[0])
            for f in os.listdir(inner):
                shutil.move(os.path.join(inner, f), os.path.join(dest, f))
            shutil.rmtree(inner, ignore_errors=True)

    # ---------------- FILE UPLOAD ---------------- #

    @dp.message_handler(content_types=types.ContentType.DOCUMENT)
    async def receive_project_file(msg: types.Message):
        uid = msg.from_user.id
        st = load_json()

        if "users" not in st or str(uid) not in st["users"]:
            await msg.reply("⚠️ First create a project using *New Project*.", parse_mode="Markdown")
            return

        proj = st["users"][str(uid)]["projects"][-1]
        base = user_project_dir(uid, proj)

        # Progress messages
        p1 = await msg.reply("📦 Saving file...")
        file_path = os.path.join(base, msg.document.file_name)
        await msg.document.download(destination_file=file_path)

        p2 = await msg.reply("🔧 Extracting...")

        if file_path.endswith(".zip"):
            try:
                extract_zip(file_path, base)
                os.remove(file_path)
            except Exception as e:
                await msg.reply(f"❌ Zip Error: `{e}`", parse_mode="Markdown")
                return

        p3 = await msg.reply("⚙️ Installing dependencies...")

        if os.path.exists(os.path.join(base, "requirements.txt")):
            install_requirements_if_present(base)
        else:
            py = None
            for f in os.listdir(base):
                if f.endswith(".py"):
                    py = os.path.join(base, f)
                    break
            if py:
                detect_imports_and_install(py)

        await clean_messages([p1, p2, p3])

        await msg.answer("✅ Upload complete.\nGo to **MY PROJECTS** to manage it.", parse_mode="Markdown")

    # ---------------- PROJECT LIST ---------------- #

    @dp.callback_query_handler(lambda c: c.data == "menu:projects")
    async def show_projects(c: types.CallbackQuery):
        st = load_json()
        uid = str(c.from_user.id)
        projs = st.get("users", {}).get(uid, {}).get("projects", [])

        kb = InlineKeyboardMarkup(row_width=1)

        for p in projs:
            kb.add(InlineKeyboardButton(p, callback_data=f"open::{p}"))

        kb.add(InlineKeyboardButton("🆕 New Project", callback_data="project:new"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="main_menu"))

        await c.message.edit_text("📂 **Your Projects:**", reply_markup=kb, parse_mode="Markdown")
        await c.answer()

    # ---------------- OPEN PROJECT ---------------- #

    @dp.callback_query_handler(lambda c: c.data.startswith("open::"))
    async def open_project(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        await c.message.edit_text(
            project_status(c.from_user.id, proj),
            reply_markup=project_keyboard(c.from_user.id, proj)
        )
        await c.answer()

    # ---------------- REFRESH ---------------- #

    @dp.callback_query_handler(lambda c: c.data.startswith("refresh::"))
    async def refresh_status(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        await c.message.edit_text(
            project_status(c.from_user.id, proj),
            reply_markup=project_keyboard(c.from_user.id, proj)
        )
        await c.answer("🔄 Refreshed")

    # ---------------- RUN ---------------- #

    @dp.callback_query_handler(lambda c: c.data.startswith("run::"))
    async def run_project(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        uid = c.from_user.id
        try:
            start_script(uid, proj)
            await c.message.answer("🚀 Project started!")
        except Exception as e:
            await c.message.answer(f"❌ Start error: `{e}`", parse_mode="Markdown")

        await c.answer()

    # ---------------- STOP ---------------- #

    @dp.callback_query_handler(lambda c: c.data.startswith("stop::"))
    async def stop_project_cb(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        stop_script(c.from_user.id, proj)
        await c.message.answer("🛑 Project stopped.")
        await c.answer()

    # ---------------- RESTART ---------------- #

    @dp.callback_query_handler(lambda c: c.data.startswith("restart::"))
    async def restart_project_cb(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        restart_script(c.from_user.id, proj)
        await c.message.answer("🔁 Restarted.")
        await c.answer()

    # ---------------- LOGS ---------------- #

    @dp.callback_query_handler(lambda c: c.data.startswith("logs::"))
    async def send_logs(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        uid = c.from_user.id
        content = read_logs(uid, proj)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        with open(tmp.name, "w", encoding="utf-8") as f:
            f.write(content)

        await c.message.answer_document(InputFile(tmp.name, filename=f"{proj}_logs.txt"))
        os.unlink(tmp.name)
        await c.answer()

    # ---------------- DELETE ---------------- #

    @dp.callback_query_handler(lambda c: c.data.startswith("delete::"))
    async def delete_confirm(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("❌ Cancel", callback_data=f"open::{proj}"),
            InlineKeyboardButton("🗑 Confirm Delete", callback_data=f"delete_yes::{proj}")
        )

        await c.message.edit_text(f"⚠️ Delete project **{proj}**?", reply_markup=kb, parse_mode="Markdown")
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith("delete_yes::"))
    async def delete_yes(c: types.CallbackQuery):
        proj = c.data.split("::", 1)[1]
        base = user_project_dir(c.from_user.id, proj)

        try:
            shutil.rmtree(base, ignore_errors=True)
            st = load_json()
            st["users"][str(c.from_user.id)]["projects"].remove(proj)
            save_json(STATE_FILE, st)
            await c.message.edit_text("🗑 Deleted successfully.")
        except Exception as e:
            await c.message.edit_text(f"❌ Delete failed: `{e}`", parse_mode="Markdown")

        await c.answer()
