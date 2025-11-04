\
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.helpers import ensure_state_user

START_MESSAGE = """👋 Welcome to the Python Project Hoster!

I'm your personal bot for securely deploying and managing your Python scripts and applications, right here from Telegram.

━━━━━━━━━━━━━━━━━━━
⚡ Key Features:
🚀 Deploy Instantly — Upload your code as a .zip or .py file and I'll handle the rest.
📂 Easy Management — Use the built-in web file manager to edit your files live.
🤖 Full Control — Start, stop, restart, and view logs for all your projects.
🪄 Auto Setup — No need for a requirements file; I automatically install everything required!
💾 Backup System — Your project data is automatically backed up every 10 minutes.
━━━━━━━━━━━━━━━━━━━

🆓 Free Tier:
• You can host up to 2 projects.
• Each project runs for 12 hours per session.

⭐ Premium Tier:
• Host up to 10 projects.
• Run your scripts 24/7 nonstop.
• Automatic daily backup retention.

Need more power? You can upgrade to Premium anytime by contacting the bot owner!

━━━━━━━━━━━━━━━━━━━
👇 Get Started Now:
1️⃣ Tap \"🆕 New Project\" below.
2️⃣ Set your project name.
3️⃣ Upload your Python script (.py) or .zip file.
4️⃣ Control everything from your dashboard!
━━━━━━━━━━━━━━━━━━━

🧑‍💻 Powered by: @freehostinggbot
🔒 Secure • Fast • Easy to Use
"""


def main_kb(uid, owner_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton('🆕 New Project', callback_data='deploy:start'))
    kb.add(InlineKeyboardButton('📂 My Projects', callback_data='menu:my_projects'))
    kb.add(InlineKeyboardButton('💬 Help', callback_data='menu:help'))
    kb.add(InlineKeyboardButton('⭐ Premium', callback_data='upgrade:premium'))
    if uid == owner_id:
        kb.add(InlineKeyboardButton('🛠 Admin Panel', callback_data='admin:main'))
    return kb

def register_start_handlers(dp, bot, owner_id):
    @dp.message_handler(commands=['start'])
    async def cmd_start(message: types.Message):
        uid = message.from_user.id
        ensure_state_user(uid)
        await message.answer(START_MESSAGE, reply_markup=main_kb(uid, owner_id))

    @dp.callback_query_handler(lambda c: c.data == 'menu:help')
    async def cb_help(c: types.CallbackQuery):
        await c.message.edit_text("Help:\\n• New Project → name → upload .py/.zip (send as document)\\n• My Projects → manage your projects", reply_markup=main_kb(c.from_user.id, owner_id))
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == 'upgrade:premium')
    async def cb_premium(c: types.CallbackQuery):
        await c.answer()
        await c.message.answer("To get Premium contact: @MADARAXHEREE")
