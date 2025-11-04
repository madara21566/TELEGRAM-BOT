MADARA_HOSTING_BOT_V7 - Render-ready Package (24/7)
Generated: 2025-11-04T07:54:19.548792 UTC

Render Deployment Quick Steps:
1. Create a GitHub repo with this project or upload directly to Render from zip.
2. In Render create new Web Service, connect repo or upload zip.
3. Set Environment variables in Render Dashboard: BOT_TOKEN, OWNER_ID, BASE_URL (https://your-app.onrender.com)
4. Set health check/port if required (PORT default 10000).
5. Deploy — Render will install requirements and start the app (Procfile: web: python main.py).

Notes:
- Flask runs on port from $PORT (default 10000) and bot polling runs in same process.
- If aiogram callback issues occur, ensure aiogram==3.4.1 is installed.
