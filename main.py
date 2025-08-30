import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ========================
# BOT CONFIG
# ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Render/Heroku पर env var सेट करें

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ========================
# START COMMAND
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Use `/search <query>` to find results.\n\n"
        "Example: `/search 9876543210`"
    )

# ========================
# SEARCH COMMAND
# ========================
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /search <query>")
        return

    query = " ".join(context.args)

    try:
        # ========================
        # यहां आपका script (1).py वाला logic डालें
        # Example logic (आपके script से लिया जाएगा):
        # result = run_search(query)
        # ========================

        # अभी placeholder response
        result = f"🔍 You searched for: {query}\n\n(Result from your script will appear here)"

        await update.message.reply_text(result)

    except Exception as e:
        logging.error(f"Error in /search: {e}")
        await update.message.reply_text("⚠️ Something went wrong while processing your search.")

# ========================
# MAIN
# ========================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search))

    print("🚀 Bot is running...")
    app.run_polling()
        
    
