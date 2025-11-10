# utils/restore.py
import os, zipfile, time
from utils.helpers import load_json
from utils.runner import start_script

def _user_proj_dir(uid, proj):
    return os.path.join("data", "users", str(uid), proj)

def _latest_backup_zip(uid, proj):
    root = os.path.join("data", "backups", str(uid))
    if not os.path.isdir(root): 
        return None
    zips = [f for f in os.listdir(root) if f.endswith(".zip") and f.startswith(f"{proj}_")]
    if not zips:
        return None
    zips.sort(reverse=True)
    return os.path.join(root, zips[0])

def _ensure_from_backup(uid, proj):
    base = _user_proj_dir(uid, proj)
    if os.path.isdir(base) and os.listdir(base):
        return  # already exists with content
    z = _latest_backup_zip(uid, proj)
    if not z:
        return
    os.makedirs(base, exist_ok=True)
    with zipfile.ZipFile(z, "r") as f:
        f.extractall(base)

def restore_running_after_restart():
    """
    On boot: restore folders from latest backups (if needed) and
    restart any projects that were marked running in state.json.
    """
    st = load_json()
    procs = st.get("procs", {})
    for suid, entries in procs.items():
        uid = int(suid)
        for key, meta in entries.items():
            proj = key.split(":")[0]
            _ensure_from_backup(uid, proj)
            try:
                # Restart with detected entry (runner will auto-detect main)
                start_script(uid, proj, None)
            except Exception:
                pass
