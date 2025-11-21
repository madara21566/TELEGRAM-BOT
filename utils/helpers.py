# utils/helpers.py

import json, os, shutil, time, secrets

STATE_FILE = "data/state.json"


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
    st = load_json()
    suid = str(uid)
    st.setdefault("users", {}).setdefault(suid, {}).setdefault("projects", [])
    save_json(STATE_FILE, st)
    return st


# ---------- PREMIUM / CODE SYSTEM ----------

def generate_redeem_code(days: int):
    st = load_json()
    codes = st.setdefault("redeem_codes", {})
    code = secrets.token_hex(8)
    codes[code] = {
        "days": int(days),
        "created": int(time.time())
    }
    save_json(STATE_FILE, st)
    return code


def list_redeem_codes():
    st = load_json()
    return st.get("redeem_codes", {})


def redeem_code(code: str, uid: int):
    st = load_json()
    codes = st.get("redeem_codes", {})
    data = codes.get(code)
    if not data:
        return False, "Invalid code"

    days = data["days"]
    suid = str(uid)

    st.setdefault("premium_users", {})
    expires = int(time.time()) + days * 24 * 3600
    st["premium_users"][suid] = expires

    # code use ho gaya, remove
    del codes[code]
    save_json(STATE_FILE, st)
    return True, days


def is_premium(uid: int) -> bool:
    st = load_json()
    suid = str(uid)
    pu = st.get("premium_users", {})
    if suid in pu:
        exp = pu.get(suid)
        if exp is None or time.time() < exp:
            return True
        # expired – hata do
        del pu[suid]
        save_json(STATE_FILE, st)
    return False


# ---------- BACKUP HELPERS ----------

def backup_latest_path():
    root = "data/backups"
    if not os.path.exists(root):
        return None
    files = [
        os.path.join(root, f)
        for f in os.listdir(root)
        if f.endswith(".zip")
    ]
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def restore_from_zip(zip_path: str):
    import zipfile, tempfile
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp)

    for rootdir, dirs, files in os.walk(tmp):
        for file in files:
            rel = os.path.relpath(os.path.join(rootdir, file), tmp)
            dest = os.path.join(".", rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(os.path.join(rootdir, file), dest)

    shutil.rmtree(tmp, ignore_errors=True)
    return True
```0
