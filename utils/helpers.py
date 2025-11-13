    import os, json, time, shutil, zipfile, secrets, re
from datetime import datetime

STATE_FILE = "data/state.json"


# ======================================================
#  BASIC JSON HANDLERS
# ======================================================

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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_state_user(uid):
    """Ensure user object exists in state.json"""
    st = load_json()
    suid = str(uid)

    st.setdefault("users", {})
    st["users"].setdefault(suid, {})
    st["users"][suid].setdefault("projects", [])

    save_json(STATE_FILE, st)
    return st


# ======================================================
#  PREMIUM SYSTEM (REDEEM CODES + EXPIRY)
# ======================================================

def generate_redeem_code(days):
    """
    Owner generates redeem code.
    Each code is single-use and has custom validity.
    """
    st = load_json()
    codes = st.setdefault("redeem_codes", {})

    code = secrets.token_hex(8)
    codes[code] = {
        "days": int(days),
        "created": int(time.time())
    }

    save_json(STATE_FILE, st)
    return code


def redeem_code(code, uid):
    """Apply premium from a redeem code."""
    st = load_json()
    codes = st.get("redeem_codes", {})

    if code not in codes:
        return False, "Invalid or expired code."

    days = codes[code]["days"]
    expires_at = int(time.time()) + (days * 24 * 3600)

    suid = str(uid)
    st.setdefault("premium_users", {})
    st["premium_users"][suid] = expires_at

    # remove code after use
    del codes[code]

    save_json(STATE_FILE, st)
    return True, days


def is_premium(uid):
    """Check whether user currently premium."""
    st = load_json()
    suid = str(uid)

    pu = st.get("premium_users", {})

    if suid not in pu:
        return False

    expires = pu[suid]

    # permanent premium
    if expires is None:
        return True

    # still valid
    if time.time() < expires:
        return True

    # expired → remove
    del pu[suid]
    save_json(STATE_FILE, st)
    return False


def premium_expiry(uid):
    """Return human readable expiry string."""
    st = load_json()
    suid = str(uid)
    exp = st.get("premium_users", {}).get(suid)
    if not exp:
        return "Free User"
    if exp is None:
        return "Lifetime Premium"
    return datetime.utcfromtimestamp(exp).strftime("%Y-%m-%d %H:%M:%S UTC")


# ======================================================
#  PATH CLEANER (IMPORTANT FOR ZIP EXTRACTION BUG)
# ======================================================

def normalize_path(path):
    """Fix double paths like /data/users/uid/proj/data/users/uid/proj"""
    parts = path.split("/")
    new = []
    for p in parts:
        if p and p not in new:
            new.append(p)
    return "/".join(new)


# ======================================================
#  BACKUP & RESTORE
# ======================================================

def backup_latest_path():
    """Return path of latest backup ZIP"""
    root = "data/backups"
    if not os.path.exists(root):
        return None
    files = [os.path.join(root, f) for f in os.listdir(root) if f.endswith(".zip")]
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def restore_from_zip(zip_path):
    """Restore all data from backup.zip"""
    if not zip_path or not os.path.exists(zip_path):
        return False

    tmp = "data/restore_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp)

        # Move extracted folders back to /data
        for root, dirs, files in os.walk(tmp):
            for file in files:
                rel = os.path.relpath(os.path.join(root, file), tmp)
                dest = os.path.join("data", rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(os.path.join(root, file), dest)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return True


def create_backup_zip():
    """Return path to new backup file."""
    ts = int(time.time())
    out = f"data/backups/backup_{ts}.zip"
    os.makedirs("data/backups", exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk("data"):
            for file in files:
                fpath = os.path.join(folder, file)
                rel = os.path.relpath(fpath, "data")
                z.write(fpath, rel)

    return out


# ======================================================
#  USER / PROJECT LIMIT SYSTEM
# ======================================================

def can_create_project(uid):
    """Check free/premium project limit."""
    st = load_json()
    suid = str(uid)
    projects = st.get("users", {}).get(suid, {}).get("projects", [])

    if is_premium(uid):
        return len(projects) < 10
    return len(projects) < 2


def project_limit_text(uid):
    """Return string describing remaining project slots."""
    st = load_json()
    suid = str(uid)
    projects = st.get("users", {}).get(suid, {}).get("projects", [])

    if is_premium(uid):
        remaining = 10 - len(projects)
        return f"Premium User — {remaining} of 10 slots remaining"
    else:
        remaining = 2 - len(projects)
        return f"Free User — {remaining} of 2 slots remaining"


# ======================================================
#  PROCESS STATE CLEANUP
# ======================================================

def cleanup_stale_process(uid, proj):
    """Remove process entry if script was killed or crashed."""
    st = load_json()
    suid = str(uid)
    key = f"{proj}:entry"

    if suid in st.get("procs", {}) and key in st["procs"][suid]:
        del st["procs"][suid][key]
        save_json(STATE_FILE, st)


# ======================================================
#  JSON SAFE UPDATE UTILS
# ======================================================

def add_project(uid, project_name):
    st = ensure_state_user(uid)
    suid = str(uid)
    arr = st["users"][suid]["projects"]
    if project_name not in arr:
        arr.append(project_name)
        save_json(STATE_FILE, st)


def delete_project(uid, project_name):
    st = load_json()
    suid = str(uid)
    arr = st.get("users", {}).get(suid, {}).get("projects", [])
    if project_name in arr:
        arr.remove(project_name)
        save_json(STATE_FILE, st)
