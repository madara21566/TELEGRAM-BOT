# Telegram Hosting Bot Deployment Guide

## Overview
This is a full-featured Telegram bot for hosting Python projects, similar to Render.com. Features include user tiers, project management, admin controls, file manager, and auto-backup.

## Setup
1. Create a Telegram bot via @BotFather and get BOT_TOKEN.
2. Get your Telegram user ID (ADMIN_ID) from @userinfobot.
3. Set environment variables: BOT_TOKEN, ADMIN_ID, WEB_PASSWORD (default: admin123), SECRET_KEY (random string).

## Deployment Options

### Render (Recommended)
1. Sign up at render.com.
2. Create a new Web Service.
3. Upload the ZIP file.
4. Set env vars.
5. Deploy. Auto-starts via Procfile.

### Replit (Free 24/7)
1. Import ZIP to replit.com.
2. Use replit.nix for Python 3.11.
3. Run `python app.py`.
4. Enable "Always On" for 24/7.

### Railway (Free Credits)
1. Sign up at railway.app.
2. Upload ZIP, set env vars.
3. Deploy.

### VPS Docker
1. Build: `docker build -t bot .`
2. Run: `docker run -p 5000:5000 -e BOT_TOKEN=... bot`

## Testing Locally
- `pip install -r requirements.txt`
- `python app.py`
- Set env vars.

## Features Recap
- User: Free (12h), Premium (24/7).
- Upload Python/ZIP, auto-deploy.
- Admin panel: Stats, manage users/admins, ban/unban, lock/unlock, broadcast, backup, etc.
- File manager: Web-based with login.
- Auto-backup every hour + on restart.

For issues, check logs or contact.
