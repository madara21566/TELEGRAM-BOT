# Render-like Telegram Bot Hosting

This is a starter repo for a Render-like Telegram bot hosting system.
It includes three services: bot, deployer, and dashboard.

Run locally with Docker Compose:
1. Copy `.env.example` to `.env` and set values.
2. `docker-compose up --build -d`
3. Create admin: `docker exec -it <dashboard_container> python scripts/create_admin.py`

Notes: Mounting docker.sock into the deployer container is convenient but insecure for production.
