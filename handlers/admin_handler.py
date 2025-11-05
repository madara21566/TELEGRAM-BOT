from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from utils.user_manager import load_users, save_users
from utils.broadcast import start_broadcast
from utils.process_manager import list_running_processes, stop_project, start_project

# ---------------- MAIN ADMIN PANEL ---------------- #

def admin_panel():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
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
    return keyboard


async def open_admin_panel(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply("⛔ You are *not authorized* to access Admin Panel!")
    await message.reply("🛠 **Admin Control Panel**", reply_markup=admin_panel())


# ---------------- USER LIST ---------------- #

async def user_list(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    users = load_users()
    text = "👥 **Registered Users:**\n\n"
    for user_id in users:
        text += f"• `{user_id}`\n"
    await call.message.edit_text(text, reply_markup=admin_panel())


# ---------------- PREMIUM ADD ---------------- #

async def add_premium(call: types.CallbackQuery):
    await call.message.answer("🟢 Send the **User ID** to make premium:")


# ---------------- PREMIUM REMOVE ---------------- #

async def remove_premium(call: types.CallbackQuery):
    await call.message.answer("🔴 Send the **User ID** to remove premium:")


# ---------------- BAN USER ---------------- #

async def ban_user(call: types.CallbackQuery):
    await call.message.answer("🚫 Send the **User ID** to ban:")


# ---------------- UNBAN USER ---------------- #

async def unban_user(call: types.CallbackQuery):
    await call.message.answer("✅ Send the **User ID** to unban:")


# ---------------- BROADCAST ---------------- #

async def broadcast_menu(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    await call.message.answer("📨 Send your broadcast message:")
    start_broadcast(call.from_user.id)


# ---------------- RUNNING SCRIPTS ---------------- #

async def running_scripts(call: types.CallbackQuery):
    procs = list_running_processes()
    if not procs:
        return await call.message.answer("😴 No scripts are running...")
    txt = "🟩 **Running Scripts:**\n\n" + "\n".join(procs)
    await call.message.answer(txt)


# ---------------- STOP SCRIPT ---------------- #

async def force_stop_script(call: types.CallbackQuery):
    await call.message.answer("⛔ Send the project name to stop:")
    

# ---------------- START SCRIPT ---------------- #

async def start_script_action(call: types.CallbackQuery):
    await call.message.answer("▶️ Send the project name to start:")


# ---------------- BACKUP MANAGER ---------------- #

async def backup_manager(call: types.CallbackQuery):
    await call.message.answer("📂 Backup Manager coming soon...")


# ======================================================= #
#                    REGISTER HANDLERS                    #
# ======================================================= #

def register_admin_handlers(dp):
    dp.register_message_handler(open_admin_panel, commands=["admin"])
    dp.register_callback_query_handler(user_list, lambda c: c.data == "admin_user_list")
    dp.register_callback_query_handler(add_premium, lambda c: c.data == "admin_add_premium")
    dp.register_callback_query_handler(remove_premium, lambda c: c.data == "admin_remove_premium")
    dp.register_callback_query_handler(ban_user, lambda c: c.data == "admin_ban_user")
    dp.register_callback_query_handler(unban_user, lambda c: c.data == "admin_unban_user")
    dp.register_callback_query_handler(broadcast_menu, lambda c: c.data == "admin_broadcast")
    dp.register_callback_query_handler(running_scripts, lambda c: c.data == "admin_running")
    dp.register_callback_query_handler(force_stop_script, lambda c: c.data == "admin_stop_script")
    dp.register_callback_query_handler(start_script_action, lambda c: c.data == "admin_start_script")
    dp.register_callback_query_handler(backup_manager, lambda c: c.data == "admin_backup")
