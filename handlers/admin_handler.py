import os, json
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.helpers import load_json, save_json, STATE_FILE
from utils.runner import get_status, start_script, stop_script

# simple in-memory action tracker for the owner
PENDING = {}  # {owner_id: {"mode": "..."}}

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

    # open via inline button (your Start menu uses admin:main)
    @dp.callback_query_handler(lambda c: c.data == "admin:main")
    async def admin_main(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return await c.answer("Owner only", show_alert=True)
        await c.message.edit_text("🛠 Admin Control Panel", reply_markup=_admin_kb())
        await c.answer()

    # open via /admin command (optional)
    @dp.message_handler(commands=["admin"])
    async def admin_cmd(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return await msg.answer("❌ Not authorized.")
        await msg.answer("🛠 Admin Control Panel", reply_markup=_admin_kb())

    # -------- USERS --------
    @dp.callback_query_handler(lambda c: c.data == "admin_user_list")
    async def admin_user_list(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        st = load_json()
        users = st.get("users", {})
        if not users:
            return await c.message.answer("😶 No users yet.")
        lines = ["👥 Registered Users:\n"]
        for uid in users.keys():
            lines.append(f"• `{uid}`")
        await c.message.answer("\n".join(lines), parse_mode="Markdown")

    # -------- PREMIUM / BAN STATE HELPERS --------
    def _ensure_arrays(st):
        st.setdefault("premium_users", [])
        st.setdefault("banned", [])
        return st

    # ask for an ID, then next text message will be processed
    @dp.callback_query_handler(lambda c: c.data == "admin_add_premium")
    async def admin_add_premium(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "add_premium"}
        await c.message.answer("🟢 Send the **User ID** to make Premium:")

    @dp.callback_query_handler(lambda c: c.data == "admin_remove_premium")
    async def admin_remove_premium(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "remove_premium"}
        await c.message.answer("🔴 Send the **User ID** to remove Premium:")

    @dp.callback_query_handler(lambda c: c.data == "admin_ban_user")
    async def admin_ban_user(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "ban_user"}
        await c.message.answer("🚫 Send the **User ID** to ban:")

    @dp.callback_query_handler(lambda c: c.data == "admin_unban_user")
    async def admin_unban_user(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "unban_user"}
        await c.message.answer("✅ Send the **User ID** to unban:")

    # catch owner’s next text to complete the action
    @dp.message_handler(content_types=types.ContentType.TEXT)
    async def admin_text_pipe(msg: types.Message):
        if msg.from_user.id != OWNER_ID: 
            return  # ignore others
        mode = PENDING.get(OWNER_ID, {}).get("mode")
        if not mode:
            return
        uid = msg.text.strip()
        if not uid.isdigit():
            return await msg.answer("Please send a numeric Telegram User ID.")
        st = load_json(); st = _ensure_arrays(st)

        if mode == "add_premium":
            if uid not in st["premium_users"]:
                st["premium_users"].append(uid)
            save_json(STATE_FILE, st)
            await msg.answer(f"✅ `{uid}` is now **Premium**.", parse_mode="Markdown")

        elif mode == "remove_premium":
            if uid in st["premium_users"]:
                st["premium_users"].remove(uid)
                save_json(STATE_FILE, st)
                await msg.answer(f"✅ Premium removed from `{uid}`.", parse_mode="Markdown")
            else:
                await msg.answer("User was not Premium.")

        elif mode == "ban_user":
            if uid not in st["banned"]:
                st["banned"].append(uid)
            save_json(STATE_FILE, st)
            await msg.answer(f"⛔ `{uid}` has been **banned**.", parse_mode="Markdown")

        elif mode == "unban_user":
            if uid in st["banned"]:
                st["banned"].remove(uid)
                save_json(STATE_FILE, st)
                await msg.answer(f"✅ `{uid}` has been **unbanned**.", parse_mode="Markdown")
            else:
                await msg.answer("User was not banned.")

        # clear pending
        PENDING.pop(OWNER_ID, None)

    # -------- BROADCAST --------
    @dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
    async def admin_broadcast(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "broadcast"}
        await c.message.answer("📨 Send your broadcast message (Markdown supported):")

    @dp.message_handler(content_types=types.ContentType.ANY)
    async def admin_broadcast_pipe(msg: types.Message):
        # allow text, photo, doc — forward to all users
        if msg.from_user.id != OWNER_ID:
            return
        mode = PENDING.get(OWNER_ID, {}).get("mode")
        if mode != "broadcast":
            return
        st = load_json()
        users = list(st.get("users", {}).keys())
        sent = 0
        for uid in users:
            try:
                if msg.text:
                    await bot.send_message(int(uid), msg.text, parse_mode="Markdown")
                elif msg.photo:
                    await bot.send_photo(int(uid), msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.document:
                    await bot.send_document(int(uid), msg.document.file_id, caption=msg.caption or "")
                else:
                    await bot.send_message(int(uid), "📢 (Unsupported content type in broadcast)")
                sent += 1
            except Exception:
                pass
        PENDING.pop(OWNER_ID, None)
        await msg.answer(f"✅ Broadcast sent to {sent} users.")

    # -------- RUNNING SCRIPTS VIEW --------
    @dp.callback_query_handler(lambda c: c.data == "admin_running")
    async def admin_running(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        st = load_json()
        procs = st.get("procs", {})
        if not procs:
            return await c.message.answer("😴 No scripts are running.")
        lines = ["🟩 Running Scripts:\n"]
        for suid, entries in procs.items():
            for key, meta in entries.items():
                proj = key.split(":")[0]
                pid = meta.get("pid")
                cmd = meta.get("cmd")
                lines.append(f"• user `{suid}` • project `{proj}` • pid `{pid}` • `{cmd}`")
        await c.message.answer("\n".join(lines), parse_mode="Markdown")

    # -------- STOP ANY PROJECT --------
    @dp.callback_query_handler(lambda c: c.data == "admin_stop_script")
    async def admin_stop_any(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "stop_any"}
        await c.message.answer("⛔ Send in this format:\n`<user_id> <project_name>`", parse_mode="Markdown")

    # -------- START ANY PROJECT --------
    @dp.callback_query_handler(lambda c: c.data == "admin_start_script")
    async def admin_start_any(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID: return
        PENDING[OWNER_ID] = {"mode": "start_any"}
        await c.message.answer("▶️ Send in this format:\n`<user_id> <project_name>`", parse_mode="Markdown")

    @dp.message_handler(content_types=types.ContentType.TEXT)
    async def admin_startstop_pipe(msg: types.Message):
        if msg.from_user.id != OWNER_ID:
            return
        mode = PENDING.get(OWNER_ID, {}).get("mode")
        if mode not in ("stop_any", "start_any"):
            return
        try:
            uid_s, proj = msg.text.strip().split(maxsplit=1)
            uid = int(uid_s)
        except Exception:
            return await msg.answer("Format invalid. Use: `<user_id> <project_name>`", parse_mode="Markdown")

        try:
            if mode == "stop_any":
                stop_script(uid, proj)
                await msg.answer(f"⛔ Stopped `{proj}` for `{uid}`.")
            else:
                start_script(uid, proj, None)
                await msg.answer(f"▶️ Started `{proj}` for `{uid}`.")
        except Exception as e:
            await msg.answer(f"Error: {e}")
        finally:
            PENDING.pop(OWNER_ID, None)

    # -------- BACK --------
    @dp.callback_query_handler(lambda c: c.data == "main_menu")
    async def main_menu(c: types.CallbackQuery):
        await c.message.delete()
        await bot.send_message(c.from_user.id, "/start")
