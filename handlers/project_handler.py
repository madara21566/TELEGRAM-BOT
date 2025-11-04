# handlers/project_handler.py
import os
import time
import zipfile
import tempfile
import shutil
import traceback
from datetime import datetime, timezone

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile

from utils.helpers import load_json, save_json, ensure_state_user
from utils.installer import install_requirements_if_present, detect_imports_and_install, safe_install_packages
from utils.runner import start_script, stop_script, restart_script, read_logs, get_status

STATE_FILE = "data/state.json"
USERS_ROOT = "data/users"

# -------------------------
# Helpers: keyboard builders
# -------------------------
def main_kb(uid, owner_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton('🆕 New Project', callback_data='deploy:start'),
           InlineKeyboardButton('📂 My Projects', callback_data='menu:my_projects'))
    kb.add(InlineKeyboardButton('💬 Help', callback_data='menu:help'),
           InlineKeyboardButton('⭐ Premium', callback_data='upgrade:premium'))
    if uid == owner_id:
        kb.add(InlineKeyboardButton('🛠 Admin Panel', callback_data='admin:main'))
    return kb

def project_kb(uid, proj, base_url):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton('▶️ Run', callback_data=f'run::{proj}'),
        InlineKeyboardButton('⏹ Stop', callback_data=f'stop::{proj}'),
        InlineKeyboardButton('🔁 Restart', callback_data=f'restart::{proj}')
    )
    kb.add(
        InlineKeyboardButton('📜 Logs', callback_data=f'logs::{proj}'),
        InlineKeyboardButton('📂 File Manager', callback_data=f'fm::{proj}'),
        InlineKeyboardButton('🔄 Refresh', callback_data=f'status_refresh::{proj}')
    )
    kb.add(
        InlineKeyboardButton('⬇️ Download', callback_data=f'download::{proj}'),
        InlineKeyboardButton('🗑 Delete', callback_data=f'delete::{proj}'),
        InlineKeyboardButton('🔙 Back', callback_data='back_home')
    )
    return kb

def projects_list_kb(uid, projects):
    kb = InlineKeyboardMarkup(row_width=1)
    for p in projects:
        kb.add(InlineKeyboardButton(p, callback_data=f'proj:open:{p}'))
    kb.add(InlineKeyboardButton('🔙 Back', callback_data='back_home'))
    return kb

# -------------------------
# Status block generator
# -------------------------
def format_status_block_exact(uid, proj):
    """
    Returns a multi-line status string for the given user's project.
    """
    try:
        st = load_json(STATE_FILE, {})
        procs = st.get("procs", {}).get(str(uid), {})
        entry = None
        entry_key = None
        for k, v in procs.items():
            # keys are stored as "<proj>:<filename>"
            if k.startswith(f"{proj}:"):
                entry = v
                entry_key = k
                break

        if entry:
            pid = entry.get("pid")
            start_ts = entry.get("start", 0)
            uptime_seconds = int(time.time() - start_ts) if start_ts else 0
            hrs = uptime_seconds // 3600
            mins = (uptime_seconds % 3600) // 60
            secs = uptime_seconds % 60
            uptime_str = f"{hrs}:{mins:02d}:{secs:02d}"
            last_run = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if start_ts else "Unknown"
            return (f"Project Status for {proj}\n\n"
                    f"🔹 Status: 🟢 Running\n"
                    f"🔹 PID: {pid}\n"
                    f"🔹 Uptime: {uptime_str}\n"
                    f"🔹 Last Run: {last_run}\n"
                    f"🔹 Last Exit Code: None\n"
                    f"🔹 Run Command: python3 main.py")
        else:
            last_run = st.get('last_run', 'Never')
            return (f"Project Status for {proj}\n\n"
                    f"🔹 Status: 🔴 Stopped\n"
                    f"🔹 PID: N/A\n"
                    f"🔹 Uptime: N/A\n"
                    f"🔹 Last Run: {last_run}\n"
                    f"🔹 Last Exit Code: None\n"
                    f"🔹 Run Command: python3 main.py")
    except Exception as e:
        traceback.print_exc()
        return f"Error reading status for {proj}: {e}"

# -------------------------
# Register handlers
# -------------------------
def register_project_handlers(dp, bot, owner_id, base_url):
    """
    Registers message and callback handlers onto the Dispatcher `dp`.
    This keeps this module self-contained.
    """

    if not base_url:
        base_url = os.getenv("BASE_URL", "") or "http://localhost:10000"

    # ---- Start new deployment (ask for name) ----
    @dp.callback_query_handler(lambda c: c.data == 'deploy:start')
    async def deploy_start(c: types.CallbackQuery):
        uid = c.from_user.id
        ensure_state_user(uid)
        st = load_json(STATE_FILE, {})
        st.setdefault('awaiting_name', {})[str(uid)] = True
        save_json(STATE_FILE, st)
        await bot.send_message(uid, "📦 Send the project name (single word, no spaces).")
        await c.answer()

    # ---- Receive project name (text) ----
    @dp.message_handler(content_types=types.ContentType.TEXT)
    async def receive_name(msg: types.Message):
        uid = msg.from_user.id
        st = load_json(STATE_FILE, {})
        if st.get('awaiting_name', {}).get(str(uid)):
            # create project record and folder
            name = msg.text.strip().replace(' ', '_')
            st['awaiting_name'].pop(str(uid), None)
            st.setdefault('users', {}).setdefault(str(uid), {}).setdefault('projects', [])
            if name in st['users'][str(uid)]['projects']:
                await msg.reply(f"Project `{name}` already exists. Send a different name.", parse_mode="Markdown")
                save_json(STATE_FILE, st)
                return
            st['users'][str(uid)]['projects'].append(name)
            save_json(STATE_FILE, st)
            path = os.path.join(USERS_ROOT, str(uid), name)
            os.makedirs(path, exist_ok=True)
            await msg.reply(f"Project `{name}` created. Now upload a .py file or a .zip file as a DOCUMENT.", parse_mode="Markdown")

    # ---- Receive uploaded document (.py or .zip) ----
    @dp.message_handler(content_types=types.ContentType.DOCUMENT)
    async def receive_doc(msg: types.Message):
        uid = msg.from_user.id
        st = load_json(STATE_FILE, {})
        projects = st.get('users', {}).get(str(uid), {}).get('projects', [])
        if not projects:
            await msg.reply("You have no project. Create one using 🆕 New Project first.")
            return
        proj = projects[-1]  # last created project (upload target)
        base = os.path.join(USERS_ROOT, str(uid), proj)
        os.makedirs(base, exist_ok=True)

        # download file
        await msg.reply("📤 Uploading...")
        file_info = await bot.get_file(msg.document.file_id)
        fname = msg.document.file_name
        target_path = os.path.join(base, fname)
        await msg.document.download(destination_file=target_path)

        # if zip -> extract
        if fname.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(target_path, 'r') as z:
                    z.extractall(path=base)
                os.remove(target_path)
            except Exception as e:
                await msg.reply(f"Zip extraction error: {e}")
                return

        # auto-install requirements if present or try to detect imports
        req_path = os.path.join(base, 'requirements.txt')
        if os.path.exists(req_path):
            await msg.reply("Installing from requirements.txt (this may take a while)...")
            install_requirements_if_present(base)
        else:
            # detect imports from first .py file if any
            py_files = [p for p in os.listdir(base) if p.endswith('.py')]
            if py_files:
                main_py = os.path.join(base, py_files[0])
                await msg.reply("Detecting imports and installing missing packages (best-effort)...")
                pkgs = detect_imports_and_install(main_py)
                if pkgs:
                    await msg.reply(f"Installing detected packages: {', '.join(pkgs)}")
                    safe_install_packages(pkgs)

        await msg.reply("✅ Project uploaded and ready. Open My Projects to manage it.", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton('📂 My Projects', callback_data='menu:my_projects')))

    # ---- Show user's projects list ----
    @dp.callback_query_handler(lambda c: c.data == 'menu:my_projects')
    async def cb_my_projects(c: types.CallbackQuery):
        uid = c.from_user.id
        st = load_json(STATE_FILE, {})
        projects = st.get('users', {}).get(str(uid), {}).get('projects', [])
        if not projects:
            from handlers.start_handler import START_MESSAGE, main_kb
            await c.message.edit_text("You have no projects. Use New Project to create one.", reply_markup=main_kb(uid, owner_id))
            await c.answer()
            return
        kb = InlineKeyboardMarkup(row_width=1)
        for p in projects:
            kb.add(InlineKeyboardButton(p, callback_data=f'proj:open:{p}'))
        kb.add(InlineKeyboardButton('🔙 Back', callback_data='back_home'))
        await c.message.edit_text("Your projects:", reply_markup=kb)
        await c.answer()

    # ---- Open a single project dashboard ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('proj:open:'))
    async def proj_open(c: types.CallbackQuery):
        proj = c.data.split(':', 2)[2]
        uid = c.from_user.id
        text = format_status_block_exact(uid, proj)
        await c.message.edit_text(text, reply_markup=project_kb(uid, proj, base_url))
        await c.answer()

    # ---- Refresh status inline ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('status_refresh::'))
    async def status_refresh(c: types.CallbackQuery):
        try:
            proj = c.data.split('::', 1)[1]
            uid = c.from_user.id
            text = format_status_block_exact(uid, proj)
            await c.message.edit_text(text, reply_markup=project_kb(uid, proj, base_url))
            await c.answer('✅ Status refreshed')
        except Exception as e:
            await c.answer('Error refreshing status')
            print("Refresh error:", e)

    # ---- Run project ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('run::'))
    async def run_cb(c: types.CallbackQuery):
        try:
            proj = c.data.split('::', 1)[1]
            uid = c.from_user.id
            base = os.path.join(USERS_ROOT, str(uid), proj)
            py_files = [p for p in os.listdir(base) if p.endswith('.py')] if os.path.exists(base) else []
            if not py_files:
                await c.message.answer("No .py file found to run. Upload your script first.")
                await c.answer()
                return

            # friendly start message
            await c.message.answer(f"✅ {proj} starting... I will auto-install dependencies and initialize the environment.\nYou can check logs via 📜 Logs or manage files via 📂 File Manager.")
            main_py = py_files[0]
            cmd = f"python3 {os.path.join(base, main_py)}"
            pid = start_script(uid, proj, cmd)

            # update last_run time
            st = load_json(STATE_FILE, {})
            st['last_run'] = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            save_json(STATE_FILE, st)

            await c.message.answer(format_status_block_exact(uid, proj), reply_markup=project_kb(uid, proj, base_url))
            await c.answer()
        except Exception as e:
            await c.answer('Error starting project')
            print("Run error:", e)

    # ---- Stop project ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('stop::'))
    async def stop_cb(c: types.CallbackQuery):
        try:
            proj = c.data.split('::', 1)[1]
            uid = c.from_user.id
            base = os.path.join(USERS_ROOT, str(uid), proj)
            py_files = [p for p in os.listdir(base) if p.endswith('.py')] if os.path.exists(base) else []
            if not py_files:
                await c.answer('No script found')
                return
            stop_script(uid, proj)
            await c.message.answer("⛔ Stopped.")
            await c.answer()
        except Exception as e:
            await c.answer('Error stopping project')
            print("Stop error:", e)

    # ---- Restart project ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('restart::'))
    async def restart_cb(c: types.CallbackQuery):
        try:
            proj = c.data.split('::', 1)[1]
            uid = c.from_user.id
            base = os.path.join(USERS_ROOT, str(uid), proj)
            py_files = [p for p in os.listdir(base) if p.endswith('.py')] if os.path.exists(base) else []
            if not py_files:
                await c.answer("No script found to restart."); return
            main_py = py_files[0]
            cmd = f"python3 {os.path.join(base, main_py)}"
            restart_script(uid, proj, cmd)
            await c.message.answer(f"🔁 {proj} restarted successfully!")
            await c.answer()
        except Exception as e:
            await c.answer('Error restarting project')
            print("Restart error:", e)

    # ---- Logs: send last 500 lines as a .txt file ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('logs::'))
    async def logs_cb(c: types.CallbackQuery):
        try:
            proj = c.data.split('::', 1)[1]
            uid = c.from_user.id
            base = os.path.join(USERS_ROOT, str(uid), proj)
            py_files = [p for p in os.listdir(base) if p.endswith('.py')] if os.path.exists(base) else []
            if not py_files:
                await c.answer("No script found"); return
            main_py = py_files[0]
            log_file_candidates = [
                os.path.join(base, main_py + '.out.log'),
                os.path.join(base, main_py + '.err.log'),
                os.path.join(base, 'logs.txt')
            ]
            found = None
            for p in log_file_candidates:
                if os.path.exists(p):
                    found = p
                    break
            if not found:
                await c.message.answer("No logs yet."); await c.answer(); return
            with open(found, 'r', encoding='utf-8', errors='ignore') as fh:
                lines = fh.read().splitlines()
            tail = lines[-500:]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
            tmp.write(("\n".join(tail)).encode('utf-8'))
            tmp.flush(); tmp.close()
            await bot.send_document(uid, InputFile(tmp.name, filename=f"{proj}_last500.txt"))
            os.unlink(tmp.name)
            await c.answer()
        except Exception as e:
            await c.answer('Error sending logs')
            print("Logs error:", e)

    # ---- Open File Manager (generate secure token via web.app) ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('fm::'))
    async def fm_open(c: types.CallbackQuery):
        try:
            proj = c.data.split('::', 1)[1]
            uid = c.from_user.id
            # create token using web.app function (present in web/app.py)
            try:
                from web.app import create_fm_token
            except Exception:
                create_fm_token = None
            if create_fm_token:
                token = create_fm_token(uid, proj, lifetime_seconds=3600)
                link = f"{base_url}/fm?uid={uid}&proj={proj}&token={token}"
                await c.message.answer(f"Open File Manager: {link}")
            else:
                await c.message.answer("File manager is not available on the server.")
            await c.answer()
        except Exception as e:
            await c.answer('Error opening file manager')
            print("FM error:", e)

    # ---- Download project archive (routes handled by Flask) ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('download::'))
    async def download_cb(c: types.CallbackQuery):
        proj = c.data.split('::', 1)[1]
        uid = c.from_user.id
        # Provide friendly link to web endpoint
        link = f"{base_url}/download/{uid}/{proj}"
        await c.message.answer(f"Download your project: {link}")
        await c.answer()

    # ---- Delete project: ask for confirmation ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('delete::'))
    async def delete_project(c: types.CallbackQuery):
        proj = c.data.split('::', 1)[1]
        uid = c.from_user.id
        path = os.path.join(USERS_ROOT, str(uid), proj)
        if not os.path.exists(path):
            await c.answer("❌ Project not found", show_alert=True)
            return
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton("✅ Confirm Delete", callback_data=f'confirm_delete::{proj}'),
               InlineKeyboardButton("❌ Cancel", callback_data=f'cancel_delete::{proj}'))
        await c.message.edit_text(f"⚠️ Are you sure you want to permanently delete project `{proj}`? This action cannot be undone.", reply_markup=kb, parse_mode="Markdown")
        await c.answer()

    # ---- Confirm delete handler ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('confirm_delete::'))
    async def confirm_delete(c: types.CallbackQuery):
        proj = c.data.split('::', 1)[1]
        uid = c.from_user.id
        path = os.path.join(USERS_ROOT, str(uid), proj)
        try:
            # safety: ensure path is inside data/users/<uid> only
            base_allowed = os.path.abspath(os.path.join(USERS_ROOT, str(uid)))
            real_target = os.path.abspath(path)
            if not real_target.startswith(base_allowed):
                await c.answer("❌ Unsafe path. Deletion aborted.", show_alert=True)
                return
            shutil.rmtree(path)
            # remove from state.json
            st = load_json(STATE_FILE, {})
            user_projects = st.get('users', {}).get(str(uid), {}).get('projects', [])
            if proj in user_projects:
                user_projects.remove(proj)
                save_json(STATE_FILE, st)
            await c.message.edit_text(f"🗑 Project `{proj}` deleted successfully.", parse_mode="Markdown")
            await c.answer("✅ Deleted", show_alert=True)
        except Exception as e:
            await c.answer(f"❌ Failed to delete: {e}", show_alert=True)
            print("Delete error:", e)

    # ---- Cancel delete handler ----
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('cancel_delete::'))
    async def cancel_delete(c: types.CallbackQuery):
        proj = c.data.split('::', 1)[1]
        uid = c.from_user.id
        text = format_status_block_exact(uid, proj)
        await c.message.edit_text(text, reply_markup=project_kb(uid, proj, base_url))
        await c.answer("Deletion cancelled")

    # ---- Back home handler ----
    @dp.callback_query_handler(lambda c: c.data == 'back_home')
    async def back_home(c: types.CallbackQuery):
        try:
            from handlers.start_handler import START_MESSAGE
            await c.message.edit_text(START_MESSAGE, reply_markup=main_kb(c.from_user.id, owner_id))
            await c.answer()
        except Exception as e:
            await c.answer('Error going back')
            print("Back error:", e)

    # ---- Fallback uncaught callback handler to prevent 'no handler' errors ----
    @dp.callback_query_handler(lambda c: True)
    async def generic_cb(c: types.CallbackQuery):
        # This catches stray callbacks that were not matched earlier.
        # We keep minimal behavior: notify user and delete stale buttons if needed.
        try:
            data = c.data or ""
            if data.startswith("ignore:"):
                await c.answer()
                return
            # otherwise, let user know the button is old or invalid
            await c.answer("Button expired or invalid. Open your project again from My Projects.", show_alert=True)
        except Exception:
            pass

# end of file
