import os
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)

# Store per-user settings in memory (for small bots)
user_settings = {}

BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Replace with your BotFather token

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to the VCF Bot!\n\nCommands:\n"
        "/rename PREFIX\n"
        "/setgroup GROUPNAME\n"
        "/setfilename FILENAME\n"
        "/txttovcf – Send a .txt file\n"
        "/vcftotxt – Send a .vcf file"
    )

def get_user_config(user_id):
    return user_settings.setdefault(user_id, {
        "prefix": "",
        "group": "",
        "filename": "contacts"
    })

async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prefix = ' '.join(context.args)
    get_user_config(user_id)["prefix"] = prefix
    await update.message.reply_text(f"✅ Prefix set to: {prefix}")

async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    group = ' '.join(context.args)
    get_user_config(user_id)["group"] = group
    await update.message.reply_text(f"✅ Group set to: {group}")

async def setfilename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    filename = ' '.join(context.args).strip()
    if filename:
        get_user_config(user_id)["filename"] = filename
        await update.message.reply_text(f"✅ Filename set to: {filename}.vcf")
    else:
        await update.message.reply_text("⚠️ Usage: /setfilename mycontacts")

async def txttovcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 Please upload a .txt file now.")

async def vcftotxt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 Please upload a .vcf file now.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file = update.message.document
    if not file:
        return

    file_name = file.file_name.lower()
    file_path = f"temp_{user_id}_{file.file_name}"

    new_file = await file.get_file()
    await new_file.download_to_drive(file_path)

    config = get_user_config(user_id)
    prefix = config["prefix"]
    group = config["group"]
    filename = config["filename"]

    if file_name.endswith(".txt"):
        # Each line in .txt is assumed: Name,Number
        vcf_lines = []
        with open(file_path, "r") as f:
            lines = f.readlines()
            for line in lines:
                if ',' not in line:
                    continue
                name, number = map(str.strip, line.split(",", 1))
                full_name = f"{prefix} {name} {group}".strip()
                vcf_lines.append(
                    f"BEGIN:VCARD\nVERSION:3.0\nFN:{full_name}\nTEL:{number}\nEND:VCARD"
                )

        vcf_data = '\n'.join(vcf_lines)
        vcf_file = f"{filename}.vcf"
        with open(vcf_file, "w") as f:
            f.write(vcf_data)

        await update.message.reply_document(InputFile(vcf_file))
        os.remove(vcf_file)

    elif file_name.endswith(".vcf"):
        # Extract names & numbers from vcf to txt
        output_txt = f"{filename}.txt"
        with open(file_path, "r") as f, open(output_txt, "w") as out:
            name, number = "", ""
            for line in f:
                line = line.strip()
                if line.startswith("FN:"):
                    name = line[3:].strip()
                elif line.startswith("TEL"):
                    number = line.split(":")[1].strip()
                    out.write(f"{name}, {number}\n")

        await update.message.reply_document(InputFile(output_txt))
        os.remove(output_txt)

    os.remove(file_path)

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("rename", rename))
app.add_handler(CommandHandler("setgroup", setgroup))
app.add_handler(CommandHandler("setfilename", setfilename))
app.add_handler(CommandHandler("txttovcf", txttovcf))
app.add_handler(CommandHandler("vcftotxt", vcftotxt))
app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

app.run_polling()
