# utils/db.py

import os
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB", "madara_hosting_bot")

_client = None
_db = None

if MONGO_URI:
    try:
        _client = MongoClient(MONGO_URI)
        _db = _client[MONGO_DB_NAME]
    except Exception as e:
        # Agar connect nahi hua to bhi bot file-mode me chalega
        print("Mongo connect error:", e)


def get_db():
    """
    Mongo DB instance return karega.
    Agar Mongo configure nahi hai to error dega.
    """
    if _db is None:
        raise RuntimeError("MongoDB not configured. Set MONGO_URI in env.")
    return _db
