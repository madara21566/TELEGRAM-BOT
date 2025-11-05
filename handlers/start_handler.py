import os
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

OWNER_ID = int(os.getenv("OWNER_ID","0"))

WELCOME = (
"👋 Welcome to MADARA Python Hosting Bot!\n\n"
"Deploy & run Python scripts directly from Telegram.\n"
"No VPS • No Terminal • No Setup • Just Upload & Run 🚀\n\n"
"━━━━━━━━━━━━━━━━━━━\n"
"⚡ Features:\n"
"• Upload & run any .py or .zip project\n"
"• Auto-install missing libraries\n"
"• Start • Stop • Restart controls\n"
"• Live Logs & File Manager Web Dashboard\n"
"• Automatic Backup System\n"
"━━━━━━━━━━━━━━━━━━━\n\n"
"🆓 Free Tier:\n"
"• Host up to 2 projects\n"
"• Max runtime 12 hours each session\n\n"
"⭐ Premium Tier:\n"
"• Host up to 10 projects\n"
"• 24/7 Infinite Runtime\n"
"• Priority CPU & Fast Processing\n\n"
"Upgrade: @MADARAXHEREE\n"
"━━━━━━━━━━━━━━━━━━━\n"
"👇 Choose what to do:\n"
)

def main_menu(uid:int):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🆕 New Project", callback_data="deploy:start"),
        InlineKeyboardButton("📂 My Projects", callback_data="menu:my_projects"),
        InlineKeyboardButton("💬 Help", callback_data="menu:help"),
        InlineKeyboardButton("⭐ Premium", callback_data="menu:premium"),
    )
    if uid == OWNER_ID:
        kb.add(InlineKeyboardButton("🛠 Admin Panel", callback_data="admin:main"))
    return kb

def register_start_handlers(dp, bot, owner_id, base_url):
    @dp.message_handler(commands=['start'])
    async def start_cmd(msg: types.Message):
        await msg.answer(WELCOME, reply_markup=main_menu(msg.from_user.id))

    @dp.callback_query_handler(lambda c: c.data == "menu:help")
    async def help_cb(c: types.CallbackQuery):
        await c.message.edit_text(
            "📘 Help\n\n"
            "1) New Project → send name → upload .py/.zip\n"
            "2) My Projects → Run/Stop/Restart/Logs/File Manager/Delete\n"
            "3) Admin Panel → owner-only controls\n",
            reply_markup=main_menu(c.from_user.id)
        )
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "menu:premium")
    async def premium_cb(c: types.CallbackQuery):
        await c.message.edit_text("⭐ For premium upgrade, contact @MADARAXHEREE", reply_markup=main_menu(c.from_user.id))
        await c.answer()
