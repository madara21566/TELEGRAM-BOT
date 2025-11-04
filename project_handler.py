\
import os, time, zipfile, shutil, tempfile, traceback
from pathlib import Path
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from utils.helpers import load_json, save_json, ensure_state_user
from utils.installer import install_requirements_if_present, detect_imports_and_install, safe_install_packages
from utils.runner import start_user_process, stop_user_process
from datetime import datetime, timezone

STATE_FILE = "data/state.json"
USERS_DIR = Path("data/users")

def format_status_block_exact(uid, proj):
    try:
        st = load_json(STATE_FILE, {})
        procs = st.get("procs", {}).get(str(uid), {})
        entry = None
        fname = None
        for k,v in procs.items():
            if k.startswith(f"{proj}:"):
                entry = v; fname = k.split(":",1)[1]; break
        if entry:
            pid = entry.get("pid")
            start_ts = entry.get("start", 0)
            uptime = int(time.time() - start_ts) if start_ts else 0
            hrs = uptime//3600; mins = (uptime%3600)//60; secs = uptime%60
            uptime_str = f"{hrs}:{mins:02d}:{secs:02d}"
            last_run = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
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

def project_kb(uid, proj, base_url):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton('▶️ Run', callback_data=f'run::{proj}'),
           InlineKeyboardButton('⏹ Stop', callback_data=f'stop::{proj}'),
           InlineKeyboardButton('🔁 Restart', callback_data=f'restart::{proj}'))
    kb.add(InlineKeyboardButton('📜 Logs', callback_data=f'logs::{proj}'),
           InlineKeyboardButton('📂 File Manager', callback_data=f'fm::{proj}'),
           InlineKeyboardButton('🔄 Refresh', callback_data=f'status_refresh::{proj}'))
    kb.add(InlineKeyboardButton('⬇️ Download', callback_data=f'download::{proj}'),
           InlineKeyboardButton('🔙 Back', callback_data='back_home'))
    return kb

def register_project_handlers(dp, bot, owner_id, base_url):
    if not base_url:
        base_url = os.getenv("BASE_URL", "") or "http://localhost:8080"

    @dp.callback_query_handler(lambda c: c.data == 'deploy:start')
    async def deploy_start(c: types.CallbackQuery):
        uid = c.from_user.id
        ensure_state_user(uid)
        st = load_json(STATE_FILE, {})
        st.setdefault('awaiting_name', {})[str(uid)] = True
        save_json(STATE_FILE, st)
        await bot.send_message(uid, "📦 Send the project name (single word, no spaces).")
        await c.answer()

    @dp.message_handler(content_types=types.ContentType.TEXT)
    async def receive_name(msg: types.Message):
        uid = msg.from_user.id
        st = load_json(STATE_FILE, {})
        if st.get('awaiting_name', {}).get(str(uid)):
            name = msg.text.strip().replace(' ', '_')
            st['awaiting_name'].pop(str(uid), None)
            st.setdefault('users', {}).setdefault(str(uid), {}).setdefault('projects', []).append(name)
            save_json(STATE_FILE, st)
            Path(USERS_DIR / str(uid) / name).mkdir(parents=True, exist_ok=True)
            await msg.reply(f"Project `{name}` created. Now upload a .py file or a .zip as DOCUMENT.")

    @dp.message_handler(content_types=types.ContentType.DOCUMENT)
    async def receive_doc(msg: types.Message):
        uid = msg.from_user.id
        st = load_json(STATE_FILE, {})
        projects = st.get('users', {}).get(str(uid), {}).get('projects', [])
        if not projects:
            await msg.reply("No project found. Use New Project first.")
            return
        proj = projects[-1]
        base = USERS_DIR / str(uid) / proj
        base.mkdir(parents=True, exist_ok=True)
        await msg.reply("📤 Uploading...")
        file_path = base / msg.document.file_name
        await msg.document.download(destination_file=str(file_path))
        if str(file_path).lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(str(file_path),'r') as z:
                    z.extractall(path=str(base))
                file_path.unlink()
            except Exception as e:
                await msg.reply(f"Zip error: {e}")
                return
        req = base / 'requirements.txt'
        if req.exists():
            await msg.reply("Installing from requirements.txt ...")
            install_requirements_if_present(base)
        else:
            mains = list(base.glob('*.py'))
            if mains:
                await msg.reply("Detecting imports and installing (best-effort)...")
                pkgs = detect_imports_and_install(str(mains[0]))
                # try safe install for detected packages
                if pkgs:
                    await msg.reply(f"Installing detected packages: {', '.join(pkgs)}")
                    safe_install_packages(pkgs)
        await msg.reply("✅ Project ready. Open My Projects to manage it.", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton('📂 My Projects', callback_data='menu:my_projects')))

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
        kb = types.InlineKeyboardMarkup(row_width=1)
        for p in projects:
            kb.add(types.InlineKeyboardButton(p, callback_data=f'proj:open:{p}'))
        kb.add(types.InlineKeyboardButton('🔙 Back', callback_data='back_home'))
        await c.message.edit_text("Your projects:", reply_markup=kb)
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('proj:open:'))
    async def proj_open(c: types.CallbackQuery):
        proj = c.data.split(':',2)[2]
        uid = c.from_user.id
        text = format_status_block_exact(uid, proj)
        await c.message.edit_text(text, reply_markup=project_kb(uid, proj, base_url))
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('status_refresh::'))
    async def status_refresh(c: types.CallbackQuery):
        try:
            proj = c.data.split('::',1)[1]
            uid = c.from_user.id
            text = format_status_block_exact(uid, proj)
            await c.message.edit_text(text, reply_markup=project_kb(uid, proj, base_url))
            await c.answer('✅ Status refreshed')
        except Exception as e:
            await c.answer('Error refreshing status')
            print("Refresh error:", e)

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('run::'))
    async def run_cb(c: types.CallbackQuery):
        try:
            proj = c.data.split('::',1)[1]
            uid = c.from_user.id
            base = USERS_DIR / str(uid) / proj
            mains = list(base.glob('*.py'))
            if not mains:
                await c.message.answer("No .py file found to run.")
                await c.answer()
                return
            # send custom start message
            await c.message.answer(f"✅ {proj} started successfully!\\nI’m now auto-installing dependencies and initializing your environment ⚙️\\nYou can check real-time logs via 📜 Logs or manage files via 📂 File Manager.")
            fname = mains[0].name
            pid = start_user_process(uid, proj, fname)
            # update last_run in state
            st = load_json(STATE_FILE, {})
            st['last_run'] = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            save_json(STATE_FILE, st)
            await c.message.answer(format_status_block_exact(uid, proj), reply_markup=project_kb(uid, proj, base_url))
            await c.answer()
        except Exception as e:
            await c.answer('Error starting project')
            print("Run error:", e)

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('stop::'))
    async def stop_cb(c: types.CallbackQuery):
        try:
            proj = c.data.split('::',1)[1]
            uid = c.from_user.id
            base = USERS_DIR / str(uid) / proj
            mains = list(base.glob('*.py'))
            if not mains:
                await c.answer('No script found')
                return
            ok = stop_user_process(uid, proj, mains[0].name)
            await c.message.answer("Stopped." if ok else "Not running.")
            await c.answer()
        except Exception as e:
            await c.answer('Error stopping project')
            print("Stop error:", e)

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('logs::'))
    async def logs_cb(c: types.CallbackQuery):
        try:
            proj = c.data.split('::',1)[1]
            uid = c.from_user.id
            base = USERS_DIR / str(uid) / proj
            mains = list(base.glob('*.py'))
            if not mains:
                await c.answer("No script found"); return
            p = base / (mains[0].name + '.out.log')
            if not p.exists():
                p = base / (mains[0].name + '.err.log')
            if not p.exists():
                await c.message.answer("No logs yet."); await c.answer(); return
            lines = p.read_text(errors='ignore').splitlines()
            tail = lines[-500:]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
            tmp.write(("\\n".join(tail)).encode('utf-8'))
            tmp.flush(); tmp.close()
            await bot.send_document(uid, InputFile(tmp.name, filename=f"{mains[0].name}_last500.txt"))
            os.unlink(tmp.name)
            await c.answer()
        except Exception as e:
            await c.answer('Error sending logs')
            print("Logs error:", e)

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('fm::'))
    async def fm_open(c: types.CallbackQuery):
        try:
            proj = c.data.split('::',1)[1]
            uid = c.from_user.id
            from web.app import create_fm_token
            token = create_fm_token(uid, proj, lifetime_seconds=3600)
            link = f"{base_url}/fm?uid={uid}&proj={proj}&token={token}"
            await c.message.answer(f"Open File Manager: {link}")
            await c.answer()
        except Exception as e:
            await c.answer('Error opening file manager')
            print("FM error:", e)

    @dp.callback_query_handler(lambda c: c.data == 'back_home')
    async def back_home(c: types.CallbackQuery):
        try:
            from handlers.start_handler import START_MESSAGE, main_kb
            uid = c.from_user.id
            await c.message.edit_text(START_MESSAGE, reply_markup=main_kb(uid, owner_id))
            await c.answer()
        except Exception as e:
            await c.answer('Error going back')
            print("Back error:", e)
