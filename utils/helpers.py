import os
import json

STATE_FILE = "data/state.json"

def load_json():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def ensure_state_user(uid):
    uid = str(uid)
    data = load_json()
    data.setdefault("users", {})
    data["users"].setdefault(uid, {"premium": False, "projects": []})
    save_json(STATE_FILE, data)
    return data

def is_premium(uid):
    uid = str(uid)
    data = load_json()
    user = data.get("users", {}).get(uid, {})
    return user.get("premium", False)

def is_banned(uid):
    uid = str(uid)
    data = load_json()
    banned = data.get("banned", [])
    return uid in banned

def add_project(uid, project):
    uid = str(uid)
    data = load_json()
    data.setdefault("users", {})
    user = data["users"].setdefault(uid, {"premium": False, "projects": []})

    # Limit: Free = 2 projects, Premium = 10
    limit = 10 if user.get("premium", False) else 2
    if len(user["projects"]) >= limit:
        return False  # limit exceeded

    if project not in user["projects"]:
        user["projects"].append(project)

    save_json(STATE_FILE, data)
    return True

def remove_project(uid, project):
    uid = str(uid)
    data = load_json()
    if project in data.get("users", {}).get(uid, {}).get("projects", []):
        data["users"][uid]["projects"].remove(project)
        save_json(STATE_FILE, data)

def mark_premium(uid, status=True):
    uid = str(uid)
    data = load_json()
    data.setdefault("users", {})
    data["users"].setdefault(uid, {"premium": False, "projects": []})
    data["users"][uid]["premium"] = status
    save_json(STATE_FILE, data)

def ban_user(uid):
    uid = str(uid)
    data = load_json()
    banned = data.setdefault("banned", [])
    if uid not in banned:
        banned.append(uid)
    save_json(STATE_FILE, data)

def unban_user(uid):
    uid = str(uid)
    data = load_json()
    banned = data.setdefault("banned", [])
    if uid in banned:
        banned.remove(uid)
    save_json(STATE_FILE, data)
