# Render Python Hosting Bot


Features
- Telegram bot (multi-user) to upload `.py` scripts and `requirements.txt`.
- Per-user script storage on a Render Persistent Disk (recommended).
- Per-user virtualenv isolation and pip install to isolated env.
- Controlled subprocess runner with timeouts and resource limits.
- FastAPI web file manager and dashboard for users to view/upload/manage files and running jobs.
- Start/stop/restart control for running scripts.


IMPORTANT SECURITY NOTE
Running arbitrary user-supplied Python code on a server is **inherently risky**. This example includes basic isolation (virtualenvs, timeouts, user-level process limits) but is **not production-safe** for untrusted users. If you plan to offer this service publicly, use strong sandboxing: container-per-job (Docker), seccomp, namespaces, cgroups, hardened kernel, network egress controls, and thorough input validation.


Deploy steps (summary)
1. Create a GitHub repo and push this project.
2. On Render, create a Web Service from the repo (FastAPI dashboard). Add a Persistent Disk and choose a mount path (e.g. `/persistent`).
3. Create a Background Worker service for the Telegram bot (or run the bot inside the web service as a background task). Attach same disk if needed.
4. Set environment variables in Render: `TELEGRAM_BOT_TOKEN`, `SECRET_KEY`, `DISK_MOUNT` (the mount path you set), `ALLOWED_USERS` (comma-separated user ids if you want whitelist), `WEB_PORT`.
5. Deploy and open the dashboard. Use the bot token to message the bot and upload scripts.


See `render.yaml` for an example Render service configuration.
