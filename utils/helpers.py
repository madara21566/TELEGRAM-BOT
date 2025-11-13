import json, os, shutil, time, secrets, zipfile, tempfile

STATE_FILE = "data/state.json"

# ------------------------------
# LOAD / SAVE STATE
# ------------------------------

def load_json(path=STATE_FILE, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_state_user(uid):
    st = load_json()
    suid = str(uid)

    st.setdefault("users", {})
    st["users"].setdefault(suid, {})
    st["users"][suid].setdefault("projects", [])

    st.setdefault("premium_users", {})
    st.setdefault("redeem_codes", {})
    st.setdefault("procs", {})

    save_json(STATE_FILE, st)
    return st


# ------------------------------
# PREMIUM SYSTEM
# ------------------------------

def generate_redeem_code(days):
    """Generate a redeem code for premium activation."""
    st = load_json()
    codes = st.setdefault("redeem_codes", {})

    code = secrets.token_hex(6)
    codes[code] = {
        "days": int(days),
        "created": int(time.time())
    }

    save_json(STATE_FILE, st)
    return code


def redeem_code(code, uid):
    """Redeem a premium code and activate premium."""
    st = load_json()
    codes = st.get("redeem_codes", {})

    if code not in codes:
        return False, "❌ Invalid or expired code!"

    days = codes[code]["days"]
    suid = str(uid)

    st.setdefault("premium_users", {})

    expires = int(time.time()) + (days * 24 * 3600)
    st["premium_users"][suid] = expires

    del codes[code]
    save_json(STATE_FILE, st)

    return True, days


def is_premium(uid):
    """Check if user is premium."""
    st = load_json()
    suid = str(uid)

    premium = st.get("premium_users", {})

    if suid not in premium:
        return False

    exp = premium[suid]
    if exp is None:
        return True

    if time.time() < exp:
        return True

    del premium[suid]
    save_json(STATE_FILE, st)
    return False


# ------------------------------
# PROJECT LIMITS
# ------------------------------

def user_project_limit(uid):
    """Return max projects allowed for user."""
    return 10 if is_premium(uid) else 2


# ------------------------------
# BACKUP SYSTEM
# ------------------------------

def backup_latest_path():
    """Return path of latest backup ZIP."""
    root = "data/backups"
    if not os.path.exists(root):
        return None

    zips = [f for f in os.listdir(root) if f.endswith(".zip")]
    if not zips:
        return None

    zips.sort(key=lambda x: os.path.getmtime(os.path.join(root, x)), reverse=True)
    return os.path.join(root, zips[0])


def restore_from_zip(zip_path):
    """Restore entire data folder from uploaded backup zip."""
    if not os.path.exists(zip_path):
        return False, "ZIP file not found!"

    tmp = tempfile.mkdtemp()

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp)

        extracted_data = os.path.join(tmp, "data")
        if not os.path.exists(extracted_data):
            return False, "ZIP missing /data folder!"

        if os.path.exists("data"):
            shutil.rmtree("data")

        shutil.copytree(extracted_data, "data")

        return True, "Restored successfully"

    except Exception as e:
        return False, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------
# PROCESS STATE
# ------------------------------

def record_process(uid, proj, pid, cmd, expire):
    st = load_json()
    suid = str(uid)

    st.setdefault("procs", {})
    st["procs"].setdefault(suid, {})

    st["procs"][suid][f"{proj}:entry"] = {
        "pid": pid,
        "start": int(time.time()),
        "cmd": cmd,
        "expire": expire
    }

    save_json(STATE_FILE, st)


def remove_process(uid, proj):
    st = load_json()
    suid = str(uid)

    procs = st.get("procs", {}).get(suid, {})
    key = f"{proj}:entry"

    if key in procs:
        del procs[key]

    save_json(STATE_FILE, st)


# ------------------------------
# EXPORT COMPLETE STATE FOR ZIP
# ------------------------------

def export_state_zip():
    """Create a ZIP of entire data folder & return path."""
    os.makedirs("data/backups", exist_ok=True)
    ts = int(time.time())
    out = f"data/backups/auto_state_{ts}.zip"

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk("data"):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, "."))

    return out
