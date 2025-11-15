import os
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.helpers import generate_redeem_code, redeem_code

OWNER_ID = int(os.getenv('OWNER_ID', '0'))
BASE_URL = os.getenv('BASE_URL', '')

WELCOME = (
    "👋 Welcome to the Python Project Hoster!\n\n"
    "I'm your personal bot for securely deploying and managing your Python scripts and applications, right here from Telegram.\n\n"
    "━━━━━━━━━━━━━━━━━━━\n"
    "⚡ Key Features:\n"
    "🚀 Deploy Instantly — Upload your code as a .zip or .py file and I'll handle the rest.\n"
    "📂 Easy Management — Use the built-in web file manager to edit your files live.\n"
    "🤖 Full Control — Start, stop, restart, and view logs for all your projects.\n"
    "🪄 Auto Setup — No need for a requirements file; I automatically install everything required!\n"
    "💾 Backup System — Your project data is automatically backed up every 10 minutes.\n"
    "━━━━━━━━━━━━━━━━━━━\n\n"
    "🆓 Free Tier:\n"
    "• You can host up to 2 projects.\n"
    "• Each project runs for 12 hours per session.\n\n"
    "⭐ Premium Tier:\n"
    "• Host up to 10 projects.\n"
    "• Run your scripts 24/7 nonstop.\n"
    "• Automatic daily backup retention.\n\n"
    "Need more power? You can upgrade to Premium anytime by contacting the bot owner!\n"
    "━━━━━━━━━━━━━━━━━━━\n"
    "👇 Get Started Now:\n"
    "1️⃣ Tap \"🆕 New Project\" below.\n"
    "2️⃣ Set your project name.\n"
    "3️⃣ Upload your Python script (.py) or .zip file.\n"
    "4️⃣ Control everything from your dashboard!\n"
    "━━━━━━━━━━━━━━━━━━━\n\n"
    "🧑‍💻 Powered by: @MADARAXHEREE\n"
    "🔒 Secure • Fast • Easy to Use"
)

def main_menu(uid: int):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🆕 New Project", callback_data="deploy:start"),
        InlineKeyboardButton("📂 My Projects", callback_data="menu:my_projects"),
        InlineKeyboardButton("💬 Help", callback_data="menu:help"),
        InlineKeyboardButton("⭐ Premium", callback_data="menu:premium"),
    )
    if uid == OWNER_ID and BASE_URL:
        kb.add(
            InlineKeyboardButton("🌐 Admin Dashboard", url=f"{BASE_URL}/admin/dashboard?key={OWNER_ID}"),
            InlineKeyboardButton("🛠 Admin Panel", callback_data="admin:main"),
        )
    return kb

def register_start_handlers(dp, bot, owner_id, base_url):
    @dp.message_handler(commands=['start'])
    async def start_cmd(msg: types.Message):
        await msg.answer(WELCOME, reply_markup=main_menu(msg.from_user.id))

    @dp.callback_query_handler(lambda c: c.data == "menu:premium")
    async def premium_cb(c: types.CallbackQuery):
        text = (
            "⭐ *Premium Info*\n\n"
            "To get premium, contact @MADARAXHEREE.\n"
            "If you already have a code, use:\n"
            "`/redeem YOUR_CODE_HERE`"
        )
        await c.message.edit_text(text, parse_mode="Markdown", reply_markup=main_menu(c.from_user.id))
        await c.answer()

    @dp.message_handler(commands=['redeem'])
    async def redeem_cmd(msg: types.Message):
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            return await msg.reply("Send like: `/redeem CODE`", parse_mode="Markdown")
        code = parts[1].strip()
        ok, info = redeem_code(code, msg.from_user.id)
        if ok:
            await msg.reply(f"✅ Redeemed premium for *{info}* days.", parse_mode="Markdown")
        else:
            await msg.reply(f"❌ {info}")

    @dp.message_handler(commands=['generate'])
    async def gen_cmd(msg: types.Message):
        if msg.from_user.id != owner_id:
            return await msg.reply("Owner only.")
        parts = msg.text.split()
        days = 7
        if len(parts) > 1:
            try:
                days = int(parts[1])
            except:
                days = 7
        code = generate_redeem_code(days)
        await msg.reply(
            f"Generated key:\n`{code}`\nValid for *{days}* days.",
            parse_mode='Markdown'
)
