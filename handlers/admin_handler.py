from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_kb():
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("👥 User List", callback_data="admin:users"),
        InlineKeyboardButton("🟢 Add Premium", callback_data="admin:addprem"),
        InlineKeyboardButton("🔴 Remove Premium", callback_data="admin:rmprem"),
        InlineKeyboardButton("🚫 Ban User", callback_data="admin:ban"),
        InlineKeyboardButton("✅ Unban User", callback_data="admin:unban"),
        InlineKeyboardButton("📨 Broadcast", callback_data="admin:broadcast"),
        InlineKeyboardButton("🟩 Running Scripts", callback_data="admin:running"),
        InlineKeyboardButton("⛔ Stop Script", callback_data="admin:stop"),
        InlineKeyboardButton("▶️ Start Script", callback_data="admin:start"),
        InlineKeyboardButton("📂 Backup Manager", callback_data="admin:backup"),
        InlineKeyboardButton("🔙 Back", callback_data="admin:back"),
    )
    return kb

def register_admin_handlers(dp, bot, owner_id, base_url):
    @dp.callback_query_handler(lambda c: c.data == "admin:main")
    async def admin_main(c: types.CallbackQuery):
        if c.from_user.id != owner_id:
            await c.answer("Owner only", show_alert=True); return
        await c.message.edit_text("🛠 Admin Control Panel", reply_markup=admin_kb())
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "admin:back")
    async def admin_back(c: types.CallbackQuery):
        from handlers.start_handler import main_menu, WELCOME
        await c.message.edit_text(WELCOME, reply_markup=main_menu(c.from_user.id))
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith("admin:"))
    async def other_admin(c: types.CallbackQuery):
        if c.from_user.id != owner_id:
            await c.answer("Owner only", show_alert=True); return
        await c.answer("Admin feature shell ready. Implement specific action as needed.", show_alert=True)
