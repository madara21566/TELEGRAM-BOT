import os
import re
import json
import openai
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

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

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    entries = await extract_info_from_ai(text)

    if not entries:
        await update.message.reply_text("😔 Naam ya number samajh nahi aaya. Thoda clearly likho.")
        return

    if "txt" in text.lower():
        content = generate_txt(entries)
        filename = "contacts.txt"
    else:
        content = generate_vcf(entries)
        filename = "contacts.vcf"

    with open(filename, "w") as f:
        f.write(content)

    await update.message.reply_document(open(filename, "rb"))
    os.remove(filename)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    file_path = f"/tmp/{file.file_unique_id}_{file.file_name}"
    await (await context.bot.get_file(file.file_id)).download_to_drive(file_path)
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    os.remove(file_path)

    await handle_text(update, context=type("obj", (object,), {"message": type("obj", (object,), {"text": content})}))
