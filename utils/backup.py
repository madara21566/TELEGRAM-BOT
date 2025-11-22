# utils/backup.py

import os
import time
import zipfile

BACKUP_DIR = "data/backups"
STATE_PATH = "data/state.json"
USERS_DIR = "data/users"


def backup_projects() -> str:
    """
    Pure bot ka backup banata hai:
    - data/state.json
    - data/users/ ke andar sab user projects

    Return: backup zip ka path
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    ts = int(time.time())
    backup_name = f"backup_{ts}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as z:
        # state.json
        if os.path.exists(STATE_PATH):
            z.write(STATE_PATH, "state.json")

        # data/users/*
        if os.path.exists(USERS_DIR):
            for root, dirs, files in os.walk(USERS_DIR):
                for f in files:
                    full = os.path.join(root, f)
                    # zip ke andar relative path "users/..." ke naam se
                    rel = os.path.relpath(full, "data")
                    z.write(full, rel)

    return backup_path
