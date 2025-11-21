# utils/backup.py

import os
import zipfile
import shutil

BACKUP_DIR = "data/backups"
STATE_PATH = "data/state.json"
USERS_DIR = "data/users"


def backup_projects() -> str:
    """
    Create complete bot backup:
    - data/state.json
    - data/users/*
    Returns: backup zip file path
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # state.json ka last modified time use karke naam banaya
    # taki same time wale backup overwrite na ho
    if os.path.exists(STATE_PATH):
        ts = int(os.path.getmtime(STATE_PATH))
    else:
        ts = int(os.path.getmtime(USERS_DIR)) if os.path.exists(USERS_DIR) else 0

    name = f"backup_{ts}.zip"
    backup_path = os.path.join(BACKUP_DIR, name)

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as z:
        # state.json
        if os.path.exists(STATE_PATH):
            z.write(STATE_PATH, "state.json")

        # data/users/*
        if os.path.exists(USERS_DIR):
            for root, dirs, files in os.walk(USERS_DIR):
                for f in files:
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, "data")  # users/... ke naam se
                    z.write(abs_path, rel_path)

    return backup_path


def restore_from_zip(zip_path: str) -> bool:
    """
    Restore full bot backup from ZIP file.
    Pehle purana data delete, phir naya extract.
    """
    if not os.path.exists(zip_path):
        return False

    # purana data hatao
    if os.path.exists(USERS_DIR):
        shutil.rmtree(USERS_DIR)
    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)

    os.makedirs("data", exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall("data")
        return True
    except Exception:
        return False


def backup_latest_path():
    """Latest created backup ZIP ka path return karega, warna None."""
    if not os.path.exists(BACKUP_DIR):
        return None

    files = [
        os.path.join(BACKUP_DIR, f)
        for f in os.listdir(BACKUP_DIR)
        if f.endswith(".zip")
    ]
    if not files:
        return None

    return max(files, key=os.path.getmtime)
