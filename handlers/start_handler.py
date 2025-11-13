from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.helpers import generate_redeem_code, redeem_code, is_premium, ensure_state_user, load_json, save_json, STATE_FILE

WELCOME = """
👋 **Welcome to the Python Project Hoster!**

I'm your personal bot for securely deploying and managing your Python scripts and applications, right here from Telegram.

━━━━━━━━━━━━━━━━━━━
⚡ **Key Features:**
🚀 Deploy Instantly — Upload your code as a .zip or .py file and I'll handle the rest.  
📂 Easy Management — Use the built-in file manager to edit your files.  
🤖 Full Control — Start, stop, restart & view logs for all projects.  
🪄 Auto Setup — I auto-install missing libraries!  
💾 Auto Backup — Every 10 minutes.
━━━━━━━━━━━━━━━━━━━

🆓 **Free Tier**
• 2 projects  
• Max 12-hour runtime per project  

⭐ **Premium Tier**
• 10 projects  
• 24/7 continuous runtime  
• Priority speed  
• Fast backups  
• Restore anytime  
━━━━━━━━━━━━━━━━━━━

🔐 Need Premium? Tap **“⭐ Premium”**
━━━━━━━━━━━━━━━━━━━

👇 **Choose an option**:
"""

def main_menu(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🆕 New Project", callback_data="deploy:start"),
        InlineKeyboardButton("📂 My Projects", callback_data="menu:my_projects"),
    )
    kb.add(
        InlineKeyboardButton("💬 Help", callback_data="help"),
        InlineKeyboardButton("⭐ Premium", callback_data="premium_info")
    )
    return kb

def register_start_handlers(dp, bot, OWNER_ID, BASE_URL):

    @dp.message_handler(commands=["start"])
    async def start_cmd(msg: types.Message):
        ensure_state_user(msg.from_user.id)
        await msg.answer(WELCOME, reply_markup=main_menu(msg.from_user.id), parse_mode="Markdown")

    @dp.callback_query_handler(lambda c: c.data == "help")
    async def help_cb(c: types.CallbackQuery):
        await c.message.edit_text(
            "📘 *Help Menu*\n\n"
            "1️⃣ Create project → Upload code (.zip/.py)\n"
            "2️⃣ Open *My Projects* → Manage (Run/Stop/Logs)\n"
            "3️⃣ Premium → Redeem code for 24/7\n",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Back", callback_data="back_home")
            )
        )
        await c.answer()

    @dp.callback_query_handler(lambda c: c.data == "back_home")
    async def back_home(c: types.CallbackQuery):
        await c.message.edit_text(WELCOME, reply_markup=main_menu(c.from_user.id), parse_mode="Markdown")
        await c.answer()

    # ---------------- PREMIUM INFO ---------------- #

    @dp.callback_query_handler(lambda c: c.data == "premium_info")
    async def premium_info(c: types.CallbackQuery):
        text = (
            "⭐ **Premium Benefits:**\n"
            "• Host 10 projects\n"
            "• 24/7 runtime\n"
            "• Fast backups\n"
            "• Auto-restore\n\n"
            "👉 **To Buy Premium:** Contact @MADARAXHEREE\n\n"
            "Already bought a code?\nTap *Redeem Premium* 👇"
        )
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("🔑 Redeem Code", callback_data="redeem_menu"),
            InlineKeyboardButton("🔙 Back", callback_data="back_home")
        )
        await c.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        await c.answer()

    # ---------------- REDEEM MENU ---------------- #

    @dp.callback_query_handler(lambda c: c.data == "redeem_menu")
    async def redeem_menu(c: types.CallbackQuery):
        st = load_json()
        st.setdefault("awaiting_redeem", {})[str(c.from_user.id)] = True
        save_json(STATE_FILE, st)
        await c.message.edit_text(
            "🔑 *Send your premium redeem code now*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Cancel", callback_data="back_home")
            )
        )
        await c.answer()

    @dp.message_handler()
    async def redeem_or_text(msg: types.Message):
        st = load_json()
        if st.get("awaiting_redeem", {}).get(str(msg.from_user.id)):
            code = msg.text.strip()
            st["awaiting_redeem"].pop(str(msg.from_user.id), None)
            save_json(STATE_FILE, st)

            ok, res = redeem_code(code, msg.from_user.id)
            if ok:
                await msg.answer(f"🎉 *Premium Activated for {res} days!*\nEnjoy 24/7 runtime.", parse_mode="Markdown")
            else:
                await msg.answer("❌ Invalid code!", parse_mode="Markdown")
            return
