import os, zipfile, datetime
from aiogram import types

def make_backup_zip():
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = f"data/backups/backup_{ts}.zip"
    os.makedirs("data/backups", exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk("data"):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, p)
    return out

def register_backup_handlers(dp, bot, owner_id, base_url):
    @dp.message_handler(commands=['backup'])
    async def backup_now(msg: types.Message):
        if msg.from_user.id != owner_id:
            await msg.reply("❌ Owner only."); return
        path = make_backup_zip()
        await msg.reply_document(open(path,"rb"), caption="📦 Backup ready.")
