from aiogram import types
from utils.backup import backup_projects

def register_backup_handlers(dp, bot, owner_id, base_url):
    @dp.message_handler(commands=['backup'])
    async def backup_now(msg: types.Message):
        if msg.from_user.id != owner_id:
            return await msg.reply('Owner only')
        path = backup_projects()
        await msg.reply_document(open(path, 'rb'), caption='Manual backup')
