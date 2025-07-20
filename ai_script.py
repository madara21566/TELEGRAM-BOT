import os
import re
import json
import openai
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# 🔁 Detect if message is for contact generation or general chat
def is_vcf_request(text):
    return any(keyword in text.lower() for keyword in ["vcf", "contact", "number", "txt"])

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

async def extract_contacts_from_text(text):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Extract contacts in JSON format: [{\"name\": \"Rahul\", \"number\": \"9876543210\"}]"},
            {"role": "user", "content": text}
        ]
    )
    content = response['choices'][0]['message']['content']
    return json.loads(content)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if is_vcf_request(text):
        entries = await extract_contacts_from_text(text)

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
    else:
        # ChatGPT style response
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": text}]
        )
        reply = response['choices'][0]['message']['content']
        await update.message.reply_text(reply)
