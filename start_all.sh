#!/bin/bash
# Simple runner for Replit: run deployer, dashboard, and bot in background
python3 deployer/deployer.py &> /tmp/deployer.log &
python3 dashboard/app.py &> /tmp/dashboard.log &
python3 bot/bot.py &> /tmp/bot.log &
tail -f /tmp/bot.log
