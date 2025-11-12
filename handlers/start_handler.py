import os, time
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.helpers import generate_redeem_code, redeem_code, is_premium

OWNER_ID = int(os.getenv('OWNER_ID','0'))
BASE_URL = os.getenv('BASE_URL','')

WELCOME = ("👋 Welcome to MADARA Python Hosting Bot!\n\n"
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
    kb.add(InlineKeyboardButton("🆕 New Project", callback_data="deploy:start"),
           InlineKeyboardButton("📂 My Projects", callback_data="menu:my_projects"),
           InlineKeyboardButton("💬 Help", callback_data="menu:help"),
           InlineKeyboardButton("⭐ Premium", callback_data="menu:premium"))
    if uid == OWNER_ID and BASE_URL:
        kb.add(InlineKeyboardButton("🌐 Admin Dashboard", url=f"{BASE_URL}/admin/dashboard?key={OWNER_ID}"))
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
        text = "To get premium, contact owner or use /redeem <code> if you have a code."
        await c.message.edit_text(text, reply_markup=main_menu(c.from_user.id))
        await c.answer()

    @dp.message_handler(commands=['redeem'])
    async def redeem_cmd(msg: types.Message):
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            return await msg.reply("Send: /redeem CODE")
        code = parts[1].strip()
        ok, info = redeem_code(code, msg.from_user.id)
        if ok:
            await msg.reply(f"✅ Redeemed premium for {info} days.")
        else:
            await msg.reply(f"❌ {info}")

    @dp.message_handler(commands=['generate'])
    async def gen_cmd(msg: types.Message):
        if msg.from_user.id != owner_id:
            return await msg.reply("Owner only")
        parts = msg.text.split()
        days = 7
        if len(parts) > 1:
            try: days = int(parts[1])
            except: days = 7
        code = generate_redeem_code(days)
        await msg.reply(f"Code: `{code}` valid for {days} days", parse_mode='Markdown')
