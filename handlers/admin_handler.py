\
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from utils.helpers import load_json, save_json
from pathlib import Path
import os, traceback

STATE_FILE = "data/state.json"
BACKUPS_DIR = Path("data/backups")

def admin_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("👥 User List", callback_data="admin:users"))
    kb.add(InlineKeyboardButton("🟢 Running Scripts", callback_data="admin:running"))
    kb.add(InlineKeyboardButton("⭐ Add Premium", callback_data="admin:add_premium"))
    kb.add(InlineKeyboardButton("🔴 Remove Premium", callback_data="admin:remove_premium"))
    kb.add(InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast"))
    kb.add(InlineKeyboardButton("💾 Last Backups", callback_data="admin:backups"))
    kb.add(InlineKeyboardButton("🚫 Ban", callback_data="admin:ban"))
    kb.add(InlineKeyboardButton("✅ Unban", callback_data="admin:unban"))
    kb.add(InlineKeyboardButton("⬇️ Download Script", callback_data="admin:download"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="back_home"))
    return kb

def register_admin_handlers(dp, bot, owner_id, base_url):
    @dp.callback_query_handler(lambda c: c.data == 'admin:main')
    async def admin_main(c: types.CallbackQuery):
        try:
            if c.from_user.id != owner_id:
                await c.answer("Owner only", show_alert=True); return
            await c.message.edit_text("Admin Panel", reply_markup=admin_kb()); await c.answer()
        except Exception as e:
            await c.answer('Admin error'); traceback.print_exc()

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('admin:'))
    async def admin_panel(c: types.CallbackQuery):
        try:
            if c.from_user.id != owner_id:
                await c.answer("Owner only", show_alert=True); return
            cmd = c.data.split(':',1)[1]
            if cmd == 'users':
                st = load_json(STATE_FILE, {})
                users = st.get('users', {}).keys()
                text = "Users:\n" + "\n".join(users)
                await c.message.answer(text); await c.answer(); return
            if cmd == 'running':
                st = load_json(STATE_FILE, {})
                procs = st.get('procs', {})
                text = "Running processes:\n"
                for uid, entries in procs.items():
                    for k,v in entries.items():
                        text += f"User {uid} — {k} → PID {v.get('pid')}\n"
                await c.message.answer(text); await c.answer(); return
            if cmd == 'backups':
                files = sorted(BACKUPS_DIR.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
                if not files:
                    await c.message.answer("No backups found."); await c.answer(); return
                for f in files[:10]:
                    await c.message.answer(f"Backup: {f.name} — download via server") 
                await c.answer(); return
            if cmd == 'broadcast':
                await c.message.answer("Send the broadcast message now (text):")
                st = load_json(STATE_FILE, {}); st['awaiting_broadcast'] = True; save_json(STATE_FILE, st); await c.answer(); return
            if cmd == 'add_premium':
                await c.message.answer("Reply with user id to add premium:")
                st = load_json(STATE_FILE, {}); st['awaiting_add_premium'] = True; save_json(STATE_FILE, st); await c.answer(); return
            if cmd == 'remove_premium':
                await c.message.answer("Reply with user id to remove premium:")
                st = load_json(STATE_FILE, {}); st['awaiting_remove_premium'] = True; save_json(STATE_FILE, st); await c.answer(); return
            if cmd == 'ban':
                await c.message.answer("Reply with user id to ban:"); await c.answer(); return
            if cmd == 'unban':
                await c.message.answer("Reply with user id to unban:"); await c.answer(); return
            if cmd == 'download':
                await c.message.answer("Reply with path to user file to download (e.g. data/users/1234/proj/main.py):"); st = load_json(STATE_FILE, {}); st['awaiting_download'] = True; save_json(STATE_FILE, st); await c.answer(); return
        except Exception as e:
            await c.answer('Admin command error'); traceback.print_exc()
