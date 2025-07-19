import os
import re
import json
import openai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

def extract_numbers(text):
    return re.findall(r'\b\d{7,15}\b', text)

async def extract_info_from_ai(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Extract contact names and phone numbers from the input. Respond in JSON like: [{\"name\": \"Rahul\", \"number\": \"9876543210\"}]"},
                {"role": "user", "content": text}
            ],
            temperature=0.2,
        )
        content = response['choices'][0]['message']['content']
        return json.loads(content)
    except Exception as e:
        print("AI Error:", str(e))
        return []

def generate_vcf(entries):
    data = ""
    for idx, item in enumerate(entries, start=1):
        name = item.get("name", f"Contact{idx}")
        number = item.get("number")
        if number:
            data += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{number}\nEND:VCARD\n"
    return data

def generate_txt(entries):
    return "\n".join([f"{e.get('name', '')} {e.get('number', '')}" for e in entries if e.get('number')])

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    file = update.message.document
    file_content = ""

    if file:
        file_path = f"/tmp/{file.file_unique_id}_{file.file_name}"
        await (await context.bot.get_file(file.file_id)).download_to_drive(file_path)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            file_content = f.read()
        os.remove(file_path)

    source = file_content if file_content else text
    entries = await extract_info_from_ai(source)

    if not entries:
        await update.message.reply_text("😔 Kuch samajh nahi aaya. Thoda clearly likho.")
        return

    if "txt" in text.lower():
        content = generate_txt(entries)
        file_name = "contacts.txt"
    else:
        content = generate_vcf(entries)
        file_name = "contacts.vcf"

    with open(file_name, "w") as f:
        f.write(content)

    await update.message.reply_document(open(file_name, "rb"))
    os.remove(file_name)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle))
    app.run_polling()
