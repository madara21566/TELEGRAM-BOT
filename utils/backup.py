import os
import time
import zipfile
import shutil
import logging
import tempfile

# Base data paths
BASE_DIR = "data"
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
STATE_FILE = os.path.join(BASE_DIR, "state.json")

os.makedirs(BACKUP_DIR, exist_ok=True)


def _zipdir(zip_obj: zipfile.ZipFile, folder: str, arc_prefix: str = ""):
    """
    Helper: add complete folder to zip.
    arc_prefix = path inside zip (usually empty).
    """
    for root, dirs, files in os.walk(folder):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, folder)
            arcname = os.path.join(arc_prefix, rel_path)
            zip_obj.write(full_path, arcname)


def backup_projects() -> str:
    """
    Make a full backup zip of bot data.
    Returns absolute path to created zip.
    Includes:
      - data/state.json
      - data/users/ (all users & projects)
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    ts = int(time.time())
    backup_name = f"backup_{ts}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as z:
            # state.json
            if os.path.exists(STATE_FILE):
                z.write(STATE_FILE, "state.json")

            # users directory (if exists)
            users_dir = os.path.join(BASE_DIR, "users")
            if os.path.isdir(users_dir):
                _zipdir(z, users_dir, arc_prefix="users")

        logging.info("Backup created at %s", backup_path)
    except Exception as e:
        logging.error("backup_projects error: %s", e)
        raise

    return backup_path


def backup_latest_path() -> str | None:
    """
    Return path of newest backup zip in data/backups, or None if none.
    """
    if not os.path.isdir(BACKUP_DIR):
        return None

    zips = [
        os.path.join(BACKUP_DIR, f)
        for f in os.listdir(BACKUP_DIR)
        if f.endswith(".zip")
    ]
    if not zips:
        return None

    latest = max(zips, key=os.path.getmtime)
    return latest


def restore_from_zip(zip_path: str) -> None:
    """
    Restore data from given backup zip.
    Expects same layout as backup_projects() created.
    """
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f"Backup zip not found: {zip_path}")

    tmp_dir = tempfile.mkdtemp(prefix="restore_tmp_")
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp_dir)

        # 1) restore state.json
        extracted_state = os.path.join(tmp_dir, "state.json")
        if os.path.exists(extracted_state):
            os.makedirs(BASE_DIR, exist_ok=True)
            shutil.move(extracted_state, STATE_FILE)

        # 2) restore users directory
        extracted_users = os.path.join(tmp_dir, "users")
        if os.path.isdir(extracted_users):
            final_users_dir = os.path.join(BASE_DIR, "users")
            # clear old users
            if os.path.isdir(final_users_dir):
                shutil.rmtree(final_users_dir, ignore_errors=True)
            shutil.move(extracted_users, final_users_dir)

        logging.info("Restore from %s completed", zip_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def save_uploaded_backup(uploaded_path: str) -> str:
    """
    Old-API helper expected by some code:
    - copies uploaded zip into BACKUP_DIR with timestamp name
    - calls restore_from_zip() on the saved copy
    Returns path of saved backup zip.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    ts = int(time.time())
    dest = os.path.join(BACKUP_DIR, f"uploaded_{ts}.zip")

    # copy the file into backups folder
    shutil.copy2(uploaded_path, dest)

    # restore immediately
    try:
        restore_from_zip(dest)
    except Exception as e:
        logging.error("save_uploaded_backup restore error: %s", e)
        raise

    logging.info("Uploaded backup saved and restored from %s", dest)
    return dest
