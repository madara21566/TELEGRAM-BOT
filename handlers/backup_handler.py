from aiogram import types
from utils.backup import restore_from_zip, save_uploaded_backup

# Enable manual backup upload mode
upload_backup_enabled = False

def enable_backup_upload():
    global upload_backup_enabled
    upload_backup_enabled = True

def disable_backup_upload():
    global upload_backup_enabled
    upload_backup_enabled = False

def register_backup_handlers(dp, bot, OWNER_ID):

    # When Admin clicks Upload Backup button
    @dp.callback_query_handler(lambda c: c.data == "admin_backup_upload")
    async def ask_upload_zip(c: types.CallbackQuery):
        if c.from_user.id != OWNER_ID:
            return
        enable_backup_upload()
        await c.message.answer("📤 Send backup ZIP file now:")
        await c.answer()

    # Handle uploaded backup .zip file
    @dp.message_handler(content_types=['document'])
    async def handle_backup_zip(msg: types.Message):
        global upload_backup_enabled
        if not upload_backup_enabled:
            return  # ignore if not in upload mode

        if msg.from_user.id != OWNER_ID:
            return

        doc = msg.document
        if not doc.file_name.endswith(".zip"):
            return await msg.reply("❌ Please upload a ZIP backup file.")

        # download zip
        file = await bot.get_file(doc.file_id)
        path = "data/manual_restore.zip"
        await bot.download_file(file.file_path, path)

        try:
            restore_from_zip(path)
            disable_backup_upload()
            await msg.reply("✅ Backup restored successfully!\n\nRestart bot if needed.")
        except Exception as e:
            await msg.reply(f"❌ Restore failed:\n`{e}`")
            disable_backup_upload()
