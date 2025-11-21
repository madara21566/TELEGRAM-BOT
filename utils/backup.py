import os
import time
import zipfile
from mega import Mega

BACKUP_DIR = "data/backups"
STATE_PATH = "data/state.json"
USERS_DIR = "data/users"


def create_backup_zip() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = int(time.time())
    backup_name = f"backup_{ts}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(STATE_PATH):
            z.write(STATE_PATH, "state.json")

        if os.path.exists(USERS_DIR):
            for root, dirs, files in os.walk(USERS_DIR):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, "data")
                    z.write(full, rel)

    return backup_path


def mega_login():
    email = os.getenv("MEGA_EMAIL")
    password = os.getenv("MEGA_PASSWORD")
    if not email or not password:
        raise Exception("MEGA credentials missing (.env)")
    m = Mega()
    return m.login(email, password)


def upload_backup_to_mega(path: str) -> str:
    m = mega_login()
    folder = m.find("BOT_BACKUPS")
    if folder is None:
        folder = m.create_folder("BOT_BACKUPS")
        folder = folder[0]

    file = m.upload(path, folder)
    link = m.get_upload_link(file)

    clean_old_backups(m, folder)

    return link


def clean_old_backups(m, folder):
    files = m.get_files_in_node(folder)
    if len(files) <= 2:
        return

    sorted_files = sorted(files.items(), key=lambda x: int(x[1]['ts']))
    old, _ = sorted_files[0]
    m.delete(old)  # delete oldest backup


def auto_backup() -> str:
    zip_path = create_backup_zip()
    link = upload_backup_to_mega(zip_path)
    return link


def list_backups():
    m = mega_login()
    folder = m.find("BOT_BACKUPS")
    if folder is None:
        return []
    files = m.get_files_in_node(folder)
    backups = []
    for k, v in files.items():
        backups.append((k, v["a"]["n"], v["ts"]))
    return sorted(backups, key=lambda x: x[2], reverse=True)


def restore_latest_from_mega() -> bool:
    m = mega_login()
    folder = m.find("BOT_BACKUPS")
    if folder is None:
        return False

    backups = list_backups()
    if not backups:
        return False

    file_id, name, _ = backups[0]
    local = os.path.join(BACKUP_DIR, name)
    m.download(file_id, local)

    with zipfile.ZipFile(local, 'r') as z:
        z.extractall("data")

    return True
