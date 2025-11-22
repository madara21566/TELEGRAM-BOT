# utils/backup.py

import os
import time
import zipfile

from pymongo import MongoClient
from bson import Binary

BACKUP_DIR = "data/backups"
STATE_PATH = "data/state.json"
USERS_DIR = "data/users"

# --- Mongo config (env se lega) ---
MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB = os.getenv("MONGO_DB", "madara_hosting_bot")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "backups")

_client = None
_collection = None

if MONGO_URI:
    try:
        _client = MongoClient(MONGO_URI)
        _db = _client[MONGO_DB]
        _collection = _db[MONGO_COLLECTION]
    except Exception:
        _client = None
        _collection = None


def backup_projects() -> str:
    """
    Pure bot ka local ZIP backup banata hai:
    - data/state.json
    - data/users/ ke andar sab user projects

    Return: backup zip ka path (local)
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

    # MongoDB par bhi push karo (agar configured hai)
    if _collection is not None:
        try:
            upload_backup_to_mongo(backup_path)
        except Exception:
            # Agar Mongo fail ho gaya to bhi local backup bana hua rahega
            pass

    return backup_path


def upload_backup_to_mongo(zip_path: str) -> None:
    """
    backup ZIP ko MongoDB collection me binary form me store karta hai.
    Sirf last 2 backup Mongo me rakhta, purane delete.
    """
    if _collection is None:
        return

    with open(zip_path, "rb") as f:
        data = f.read()

    doc = {
        "created_at": int(time.time()),
        "filename": os.path.basename(zip_path),
        "data": Binary(data),
    }
    _collection.insert_one(doc)

    # sirf last 2 backup rakho
    cur = _collection.find({}, sort=[("created_at", -1)])
    docs = list(cur)
    if len(docs) > 2:
        for old in docs[2:]:
            _collection.delete_one({"_id": old["_id"]})


def restore_latest_from_mongo(target_dir: str = "data") -> bool:
    """
    MongoDB se latest backup nikalke unzip karta hai.
    Return: True = success, False = kuch nahi / fail.
    """
    if _collection is None:
        return False

    doc = _collection.find_one({}, sort=[("created_at", -1)])
    if not doc:
        return False

    # temp zip likho
    os.makedirs(BACKUP_DIR, exist_ok=True)
    tmp_path = os.path.join(BACKUP_DIR, "mongo_latest_tmp.zip")
    with open(tmp_path, "wb") as f:
        f.write(doc["data"])

    import shutil

    # purana data/state/users hatao
    state_path = os.path.join(target_dir, "state.json")
    users_dir = os.path.join(target_dir, "users")

    if os.path.exists(state_path):
        os.remove(state_path)
    if os.path.exists(users_dir):
        shutil.rmtree(users_dir, ignore_errors=True)

    with zipfile.ZipFile(tmp_path, "r") as z:
        z.extractall(target_dir)

    os.remove(tmp_path)
    return True
