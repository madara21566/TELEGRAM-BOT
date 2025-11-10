import os
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.helpers import load_json, save_json, STATE_FILE
from utils.runner import start_script, stop_script

PENDING = {}

def _admin_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("👥 User List", callback_data="admin_user_list"),
        InlineKeyboardButton("🟢 Add Premium", callback_data="admin_add_premium"),
        InlineKeyboardButton("🔴 Remove Premium", callback_data="admin_remove_premium"),
        InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban_user"),
        InlineKeyboardButton("✅ Unban User", callback_data="admin_unban_user"),
        InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"),
        InlineKeyboardButton("🟩 Running Scripts", callback_data="admin_running"),
        InlineKeyboardButton("⛔ Stop Script", callback_data="admin_stop_script"),
        InlineKeyboardButton("▶️ Start Script", callback_data="admin_start_script"),
        InlineKeyboardButton("📂 Backup Manager", callback_data="admin_backup"),
        InlineKeyboardButton("🔙 Back", callback_data="main_menu"),
    )
    return kb

def register_admin_handlers(dp, bot, OWNER_ID, BASE_URL):
    def _ensure_arrays(st):
        st.setdefault("premium_users", [])
        st.setdefault("banned", [])
        return st

    @dp.callback_query_handler(lambda c: c.data == "admin:main")
    async def admin_main(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return await c.answer("Owner only", show_alert=True)
        await c.message.edit_text("🛠 Admin Control Panel", reply_markup=_admin_kb()); await c.answer()

    @dp.message_handler(commands=["admin"])
    async def admin_cmd(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return await msg.answer("❌ Not authorized.")
        await msg.answer("🛠 Admin Control Panel", reply_markup=_admin_kb())

    @dp.callback_query_handler(lambda c: c.data == "admin_user_list")
    async def admin_user_list(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        st = load_json(); users = st.get("users", {})
        if not users: return await c.message.answer("😶 No users yet.")
        lines = ["👥 Registered Users:\n", *[f"• `{uid}`" for uid in users.keys()]]
        await c.message.answer("\n".join(lines), parse_mode="Markdown")

    # ---- Premium / Ban / Unban ----
    @dp.callback_query_handler(lambda c: c.data in ("admin_add_premium","admin_remove_premium","admin_ban_user","admin_unban_user"))
    async def admin_request_id(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        label = {
            "admin_add_premium": "🟢 Send the **User ID** to make Premium:",
            "admin_remove_premium": "🔴 Send the **User ID** to remove Premium:",
            "admin_ban_user": "🚫 Send the **User ID** to ban:",
            "admin_unban_user": "✅ Send the **User ID** to unban:"
        }[c.data]
        PENDING[OWNER_ID] = {"mode": c.data}
        await c.message.answer(label); await c.answer()

    @dp.message_handler(content_types=types.ContentType.TEXT)
    async def admin_text_pipe(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        pend = PENDING.get(OWNER_ID)
        if not pend: return
        uid = msg.text.strip()
        if not uid.isdigit(): return await msg.answer("Please send numeric Telegram User ID.")
        st = _ensure_arrays(load_json())

        if pend["mode"] == "admin_add_premium":
            if uid not in st["premium_users"]: st["premium_users"].append(uid)
            save_json(STATE_FILE, st); await msg.answer(f"✅ `{uid}` is now **Premium**.", parse_mode="Markdown")

        elif pend["mode"] == "admin_remove_premium":
            if uid in st["premium_users"]: st["premium_users"].remove(uid)
            save_json(STATE_FILE, st); await msg.answer(f"✅ Premium removed from `{uid}`.", parse_mode="Markdown")

        elif pend["mode"] == "admin_ban_user":
            if uid not in st["banned"]: st["banned"].append(uid)
            save_json(STATE_FILE, st); await msg.answer(f"⛔ `{uid}` has been **banned**.", parse_mode="Markdown")

        elif pend["mode"] == "admin_unban_user":
            if uid in st["banned"]: st["banned"].remove(uid)
            save_json(STATE_FILE, st); await msg.answer(f"✅ `{uid}` has been **unbanned**.", parse_mode="Markdown")

        PENDING.pop(OWNER_ID, None)

    # ---- Broadcast ----
    @dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
    async def admin_broadcast(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "broadcast"}
        await c.message.answer("📨 Send your broadcast message (Markdown supported):"); await c.answer()

    @dp.message_handler(content_types=types.ContentType.ANY)
    async def admin_broadcast_pipe(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        pend = PENDING.get(OWNER_ID)
        if not pend or pend.get("mode") != "broadcast": return
        st = load_json(); users = list(st.get("users", {}).keys()); sent = 0
        for uid in users:
            try:
                if msg.text:
                    await bot.send_message(int(uid), msg.text, parse_mode="Markdown")
                elif msg.photo:
                    await bot.send_photo(int(uid), msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.document:
                    await bot.send_document(int(uid), msg.document.file_id, caption=msg.caption or "")
                else:
                    await bot.send_message(int(uid), "📢 Broadcast")
                sent += 1
            except Exception:
                pass
        PENDING.pop(OWNER_ID, None)
        await msg.answer(f"✅ Broadcast sent to {sent} users.")

    # ---- Running list / start / stop ----
    @dp.callback_query_handler(lambda c: c.data == "admin_running")
    async def admin_running(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        st = load_json(); procs = st.get("procs", {})
        if not procs: return await c.message.answer("😴 No scripts are running.")
        lines = ["🟩 Running Scripts:\n"]
        for suid, entries in procs.items():
            for key, meta in entries.items():
                proj = key.split(":")[0]
                lines.append(f"• `{suid}` — `{proj}` — PID `{meta.get('pid')}`")
        await c.message.answer("\n".join(lines), parse_mode="Markdown")

    @dp.callback_query_handler(lambda c: c.data == "admin_stop_script")
    async def admin_stop_any(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "stop_any"}
        await c.message.answer("⛔ Send: `<user_id> <project_name>`", parse_mode="Markdown")

    @dp.callback_query_handler(lambda c: c.data == "admin_start_script")
    async def admin_start_any(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "start_any"}
        await c.message.answer("▶️ Send: `<user_id> <project_name>`", parse_mode="Markdown")

    @dp.message_handler(content_types=types.ContentType.TEXT)
    async def admin_startstop_pipe(msg: types.Message):
        if msg.from_user.id != OWNER_ID: return
        pend = PENDING.get(OWNER_ID); 
        if not pend or pend["mode"] not in ("stop_any","start_any"): return
        try:
            uid_s, proj = msg.text.strip().split(maxsplit=1)
            uid = int(uid_s)
        except Exception:
            return await msg.answer("Format invalid. Use: `<user_id> <project_name>`", parse_mode="Markdown")
        try:
            if pend["mode"] == "stop_any":
                stop_script(uid, proj); await msg.answer(f"⛔ Stopped `{proj}` for `{uid}`.")
            else:
                start_script(uid, proj, None); await msg.answer(f"▶️ Started `{proj}` for `{uid}`.")
        except Exception as e:
            await msg.answer(f"Error: {e}")
        PENDING.pop(OWNER_ID, None)

    @dp.callback_query_handler(lambda c: c.data == "admin_backup")
    async def backup_view(c: types.CallbackQuery):
        await c.message.answer("📦 Backup system active.\nLatest backups in: `data/backups/`", parse_mode="Markdown")

    @dp.callback_query_handler(lambda c: c.data == "main_menu")
    async def main_menu_back(c: types.CallbackQuery):
        from handlers.start_handler import WELCOME, main_menu
        await c.message.edit_text(WELCOME, reply_markup=main_menu(c.from_user.id)); await c.answer()
