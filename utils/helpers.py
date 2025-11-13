import json
import os
import time
import secrets
import shutil

# Single source of truth for state
STATE_FILE = "data/state.json"

# ---------------- Basic JSON helpers ----------------

def _ensure_dir_for(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def load_json(path=STATE_FILE, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    _ensure_dir_for(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------- State initialization ----------------

def _ensure_state():
    st = load_json(STATE_FILE, default={})
    changed = False
    if "users" not in st:
        st["users"] = {}
        changed = True
    if "procs" not in st:
        st["procs"] = {}
        changed = True
    if "premium_users" not in st:
        st["premium_users"] = {}  # uid -> expiry_ts or None
        changed = True
    if "banned" not in st:
        st["banned"] = []  # list of user ids
        changed = True
    if "redeem_codes" not in st:
        st["redeem_codes"] = {}  # code -> {"days":N,"created":ts}
        changed = True
    if changed:
        save_json(STATE_FILE, st)
    return st

# Ensure file exists on import
_ensure_state()

# ---------------- User & project helpers ----------------

def register_user(uid):
    """Ensure user record exists (returns state and user dict)."""
    st = load_json(STATE_FILE, default={})
    suid = str(uid)
    st.setdefault("users", {})
    if suid not in st["users"]:
        st["users"][suid] = {"projects": [], "created": int(time.time())}
        save_json(STATE_FILE, st)
    return st, st["users"][suid]

def add_project_for_user(uid, project_name):
    st, user = register_user(uid)
    if project_name not in user["projects"]:
        user["projects"].append(project_name)
        save_json(STATE_FILE, st)
    return user["projects"]

def remove_project_for_user(uid, project_name):
    st = load_json(STATE_FILE)
    suid = str(uid)
    if suid in st.get("users", {}):
        projs = st["users"][suid].get("projects", [])
        if project_name in projs:
            projs.remove(project_name)
            save_json(STATE_FILE, st)
            # remove project folder if exists
            proj_path = os.path.join("data", "users", suid, project_name)
            try:
                shutil.rmtree(proj_path, ignore_errors=True)
            except Exception:
                pass
            return True
    return False

def list_users():
    st = load_json(STATE_FILE)
    return list(st.get("users", {}).keys())

# ---------------- Premium helpers ----------------

def set_premium(uid, days=None):
    """Set premium for user. days=None => permanent."""
    st = load_json(STATE_FILE)
    suid = str(uid)
    st.setdefault("premium_users", {})
    if days is None:
        st["premium_users"][suid] = None
    else:
        st["premium_users"][suid] = int(time.time()) + int(days) * 24 * 3600
    save_json(STATE_FILE, st)

def remove_premium(uid):
    st = load_json(STATE_FILE)
    suid = str(uid)
    if st.get("premium_users") and suid in st["premium_users"]:
        del st["premium_users"][suid]
        save_json(STATE_FILE, st)

def is_premium(uid):
    st = load_json(STATE_FILE)
    suid = str(uid)
    pu = st.get("premium_users", {})
    if suid not in pu:
        return False
    exp = pu.get(suid)
    if exp is None:
        return True
    if time.time() < exp:
        return True
    # expired → cleanup
    del pu[suid]
    save_json(STATE_FILE, st)
    return False

def list_premium_users():
    st = load_json(STATE_FILE)
    pu = st.get("premium_users", {})
    out = []
    for suid, exp in pu.items():
        if exp is None:
            out.append({"user_id": suid, "expires": None})
        else:
            out.append({"user_id": suid, "expires": int(exp)})
    return out

# ---------------- Ban helpers ----------------

def ban_user(uid):
    st = load_json(STATE_FILE)
    st.setdefault("banned", [])
    suid = str(uid)
    if suid not in st["banned"]:
        st["banned"].append(suid)
        save_json(STATE_FILE, st)
        return True
    return False

def unban_user(uid):
    st = load_json(STATE_FILE)
    suid = str(uid)
    if suid in st.get("banned", []):
        st["banned"].remove(suid)
        save_json(STATE_FILE, st)
        return True
    return False

def is_banned(uid):
    st = load_json(STATE_FILE)
    return str(uid) in st.get("banned", [])

# ---------------- Redeem / codes ----------------

def generate_redeem_code(days):
    """Owner can generate a redeem code that gives 'days' premium when redeemed."""
    st = load_json(STATE_FILE)
    code = secrets.token_hex(8)
    st.setdefault("redeem_codes", {})
    st["redeem_codes"][code] = {"days": int(days), "created": int(time.time())}
    save_json(STATE_FILE, st)
    return code

def redeem_code(code, uid):
    st = load_json(STATE_FILE)
    codes = st.get("redeem_codes", {})
    info = codes.get(code)
    if not info:
        return False, "Invalid code"
    days = info.get("days", 0)
    # set premium
    set_premium(uid, days=days if days > 0 else None)
    # remove code after use
    try:
        del codes[code]
        save_json(STATE_FILE, st)
    except Exception:
        pass
    return True, days

# ---------------- Backup / restore helpers ----------------

def backup_latest_path():
    root = "data/backups"
    if not os.path.exists(root):
        return None
    zips = [os.path.join(root, f) for f in os.listdir(root) if f.endswith(".zip")]
    if not zips:
        return None
    zips.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return zips[0]

def restore_from_zip(zip_path):
    """Extract backup zip into project tree (overwrites)."""
    import zipfile, tempfile
    if not os.path.exists(zip_path):
        return False, "zip not found"
    tmp = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp)
        # Copy files back into repo root (data/ etc.)
        for root, dirs, files in os.walk(tmp):
            for file in files:
                src = os.path.join(root, file)
                rel = os.path.relpath(src, tmp)
                dest = os.path.join(".", rel)
                _ensure_dir_for(dest)
                shutil.copy2(src, dest)
        return True, "restored"
    except Exception as e:
        return False, str(e)
    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass

# ---------------- Small utilities ----------------

def user_project_count(uid):
    st = load_json(STATE_FILE)
    suid = str(uid)
    return len(st.get("users", {}).get(suid, {}).get("projects", []))

def total_users():
    st = load_json(STATE_FILE)
    return len(st.get("users", {}))

def total_projects():
    st = load_json(STATE_FILE)
    return sum(len(u.get("projects", [])) for u in st.get("users", {}).values())

# ---------------- Convenience: ensure user & projects exist ----------------

def ensure_state_user(uid):
    st = load_json(STATE_FILE)
    suid = str(uid)
    st.setdefault("users", {}).setdefault(suid, {}).setdefault("projects", [])
    save_json(STATE_FILE, st)
    return st

# ---------------- End of helpers.py ----------------
