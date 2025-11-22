# utils/mongo_state.py

import os
import datetime
from typing import Optional, Dict, Any

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None  # agar pymongo install nahi hai toh silently ignore


MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "madara_hosting_bot")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "state_snapshots")

_client = None


def _get_collection():
    """
    Mongo collection return karta hai.
    Agar MONGO_URI ya pymongo missing ho toh None return.
    """
    global _client

    if not MONGO_URI or MongoClient is None:
        return None

    if _client is None:
        _client = MongoClient(MONGO_URI, tz_aware=True)

    db = _client[MONGO_DB_NAME]
    return db[MONGO_COLLECTION]


def save_state_snapshot(state: Dict[str, Any]) -> None:
    """
    state.json ka pura content MongoDB me snapshot ke form me save karta hai.
    Sirf latest ~50 snapshots rakhta hai (purane delete).
    """
    col = _get_collection()
    if not col:
        return  # Mongo configure nahi hai → silently skip

    doc = {
        "created_at": datetime.datetime.utcnow(),
        "state": state,
    }
    col.insert_one(doc)

    # sirf last 50 snapshots rakho
    count = col.count_documents({})
    limit = 50
    if count > limit:
        extra = count - limit
        old_ids = [
            d["_id"]
            for d in col.find({}, {"_id": 1}).sort("created_at", 1).limit(extra)
        ]
        if old_ids:
            col.delete_many({"_id": {"$in": old_ids}})


def get_latest_state() -> Optional[Dict[str, Any]]:
    """
    MongoDB se latest state snapshot nikalta hai.
    Agar kuch nahi mila / Mongo off hai toh None.
    """
    col = _get_collection()
    if not col:
        return None

    doc = col.find_one(sort=[("created_at", -1)])
    if not doc:
        return None
    return doc.get("state") or {}
