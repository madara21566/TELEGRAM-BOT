
from flask import Flask, request
from telegram import Update, Bot'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    await application.process_update(update)
    return 'ok'

if __name__ == "__main__":
    app.run(debug=True, port=5000)
