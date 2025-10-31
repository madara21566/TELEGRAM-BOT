#!/bin/bash
set -e


# Start FastAPI (dashboard) in background
uvicorn web.main:app --host 0.0.0.0 --port ${WEB_PORT:-8000} &


# Start Telegram bot (long-running)
python bot.py
