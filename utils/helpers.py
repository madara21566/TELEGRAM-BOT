# utils/helpers.py
import json, os, threading, time
from typing import Dict, Any, List

STATE_FILE = "data/state.json"
_lock = threading.Lock()

def _ensure_dirs():
    os.makedirs("data/users", exist_ok=True)
    os.makedirs("data/backups", exist_ok=True)
    if not os.path.exists(STATE_FILE):
        # minimal skeleton
        save_json(STATE_FILE, {
            "users": {},           # { uid: {"projects": [...]} }
            "premium_users": [],   # [uid_str, ...]
            "banned": [],          # [uid_str, ...]
            "procs": {}            # { uid_str: { "proj:entry": {...} } }
        })
_ensure_dirs()

# ---------------- JSON helpers ---------------- #

def load_json(path: str = STATE_FILE, default: Dict[str, Any] = None) -> Dict[str, Any]:
    """Thread-safe read of state.json"""
    if default is None:
        default = {}
    try:
        with _lock:
            if not os.path.exists(path):
                return default
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return default

def save_json(path: str, data: Dict[str, Any]) -> None:
    """Thread-safe write (atomic) of state.json"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

def ensure_state_user(uid: int) -> Dict[str, Any]:
    """Guarantee user bucket exists and return whole state."""
    st = load_json()
    suid = str(uid)
    st.setdefault("users", {}).setdefault(suid, {}).setdefault("projects", [])
    save_json(STATE_FILE, st)
    return st

# ---------------- User registry + flags ---------------- #

def register_user(uid: int) -> None:
    """Create a user record if missing (idempotent)."""
    ensure_state_user(uid)

def get_users() -> List[str]:
    st = load_json()
    return sorted(list(st.get("users", {}).keys()))

def is_premium(uid: int) -> bool:
    st = load_json()
    return str(uid) in st.get("premium_users", [])

def set_premium(uid: int) -> None:
    st = load_json()
    suid = str(uid)
    st.setdefault("premium_users", [])
    if suid not in st["premium_users"]:
        st["premium_users"].append(suid)
        save_json(STATE_FILE, st)

def remove_premium(uid: int) -> None:
    st = load_json()
    suid = str(uid)
    arr = st.setdefault("premium_users", [])
    if suid in arr:
        arr.remove(suid)
        save_json(STATE_FILE, st)

def is_banned(uid: int) -> bool:
    st = load_json()
    return str(uid) in st.get("banned", [])

def ban_user(uid: int) -> None:
    st = load_json()
    suid = str(uid)
    st.setdefault("banned", [])
    if suid not in st["banned"]:
        st["banned"].append(suid)
        save_json(STATE_FILE, st)

def unban_user(uid: int) -> None:
    st = load_json()
    suid = str(uid)
    arr = st.setdefault("banned", [])
    if suid in arr:
        arr.remove(suid)
        save_json(STATE_FILE, st)

# ---------------- Project helpers ---------------- #

def get_user_projects(uid: int) -> List[str]:
    st = load_json()
    return st.get("users", {}).get(str(uid), {}).get("projects", [])

def add_project(uid: int, name: str) -> bool:
    """Add project name if not present. Returns True if added."""
    st = ensure_state_user(uid)
    suid = str(uid)
    arr = st["users"][suid]["projects"]
    if name not in arr:
        arr.append(name)
        save_json(STATE_FILE, st)
        return True
    return False

def remove_project(uid: int, name: str) -> None:
    st = load_json()
    suid = str(uid)
    arr = st.get("users", {}).get(suid, {}).get("projects", [])
    if name in arr:
        arr.remove(name)
        save_json(STATE_FILE, st)

# ---------------- Process bookkeeping ---------------- #

def remember_process(uid: int, proj: str, pid: int, cmd: str, start_ts: int, expire_ts: int = None) -> None:
    """Persist process metadata so status/dashboard/restore can use it."""
    st = load_json()
    suid = str(uid)
    st.setdefault("procs", {}).setdefault(suid, {})[f"{proj}:entry"] = {
        "pid": pid,
        "cmd": cmd,
        "start": start_ts,
        "expire": expire_ts,  # None for unlimited (premium)
    }
    save_json(STATE_FILE, st)

def forget_process(uid: int, proj: str) -> None:
    st = load_json()
    suid = str(uid)
    bucket = st.get("procs", {}).get(suid, {})
    key = f"{proj}:entry"
    if key in bucket:
        del bucket[key]
        save_json(STATE_FILE, st)

def all_recorded_processes() -> Dict[str, Dict[str, Any]]:
    """Return st['procs']"""
    st = load_json()
    return st.get("procs", {})

# ---------------- Restore after restart ---------------- #
# (Called from main.py startup if you want to relaunch what was running.)

def restore_processes_after_restart(spawn_cb) -> int:
    """
    Try to re-run previously running projects.
    `spawn_cb(uid:int, proj:str, cmd:str|None) -> None` must actually start the process.
    Returns count of restored processes.
    """
    st = load_json()
    restored = 0
    for suid, items in list(st.get("procs", {}).items()):
        uid = int(suid)
        for key, meta in list(items.items()):
            proj = key.split(":", 1)[0]
            # optionally skip expired FREE processes
            exp = meta.get("expire")
            if exp and time.time() > exp:
                continue
            try:
                spawn_cb(uid, proj, meta.get("cmd"))
                restored += 1
            except Exception:
                # ignore and continue
                pass
    return restored
