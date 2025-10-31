Render Deployment Guide
-----------------------

1) Upload this ZIP to Render as a new Web Service (choose 'Deploy a stashed Git repo' or 'Deploy from repo' and upload files).
2) In Environment variables set:
   - BOT_TOKEN = your_telegram_bot_token
   - OWNER_ID = your_numeric_telegram_user_id
3) Ensure runtime.txt is present (forces Python 3.11 on Render).
4) Deploy and watch logs. Bot will start and begin polling.
5) Use Telegram: send /start to bot, create project, upload files, use inline buttons.

Notes:
- This bot runs user-uploaded Python code: run on a trusted account and monitor usage.
- Backups are stored in backups/ and DB is in db.json.
