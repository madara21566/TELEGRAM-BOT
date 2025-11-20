import os
import time
import zipfile
import shutil


BACKUP_DIR = "data/backups"
USERS_DIR = "data/users"
STATE_FILE = "data/state.json"


# Ensure folders exist
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(USERS_DIR, exist_ok=True)


def backup_projects():
    """Create full backup of users folder + state.json"""
    ts = int(time.time())
    backup_path = os.path.join(BACKUP_DIR, f"backup_{ts}.zip")

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as z:
        # Add state.json
        if os.path.exists(STATE_FILE):
            z.write(STATE_FILE, "state.json")

        # Add full users directory
        for root, dirs, files in os.walk(USERS_DIR):
            for file in files:
                full_path = os.path.join(root, file)
                relative = os.path.relpath(full_path, USERS_DIR)
                z.write(full_path, os.path.join("users", relative))

    return backup_path


def backup_latest_path():
    """Return the latest backup zip path"""
    files = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")]
    if not files:
        return None

    latest = max(files, key=lambda x: os.path.getmtime(os.path.join(BACKUP_DIR, x)))
    return os.path.join(BACKUP_DIR, latest)


def restore_from_zip(zip_path):
    """Extract backup zip contents safely"""
    if not zip_path or not os.path.exists(zip_path):
        raise Exception("Backup file not found")

    # Temp extract folder
    tmp_folder = "data/tmp_restore"
    if os.path.exists(tmp_folder):
        shutil.rmtree(tmp_folder)
    os.makedirs(tmp_folder, exist_ok=True)

    # Extract Zip
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp_folder)

    # Restore state.json
    restored_state = os.path.join(tmp_folder, "state.json")
    if os.path.exists(restored_state):
        shutil.copy2(restored_state, STATE_FILE)

    # Restore users data
    restored_users = os.path.join(tmp_folder, "users")
    if os.path.exists(restored_users):
        shutil.rmtree(USERS_DIR, ignore_errors=True)
        shutil.copytree(restored_users, USERS_DIR)

    # Cleanup temp folder
    shutil.rmtree(tmp_folder, ignore_errors=True)

    return True
