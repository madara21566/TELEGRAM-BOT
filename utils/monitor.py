import os, time, signal, zipfile, glob, shutil
from utils.helpers import load_json, save_json, STATE_FILE
from utils.runner import start_script

def check_expired():
    """Stop FREE users' processes after 12h (expire set by runner)."""
    st = load_json(); changed = False
    for uid, procs in list(st.get("procs", {}).items()):
        for key, meta in list(procs.items()):
            exp = meta.get("expire")
            pid = meta.get("pid")
            if exp and time.time() > exp:
                try: os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception: pass
                del procs[key]; changed = True
    if changed: save_json(STATE_FILE, st)

def _latest_backup_for(uid, proj):
    pattern = f"data/backups/{uid}/{proj}_*.zip"
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None

def _ensure_project_files(uid, proj):
    base = f"data/users/{uid}/{proj}"
    os.makedirs(base, exist_ok=True)
    # if project seems empty, restore from latest backup
    contents = [f for f in os.listdir(base) if not f.startswith("logs")]
    if contents: return False
    zip_path = _latest_backup_for(uid, proj)
    if not zip_path: return False
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(base)
        # flatten one-level nested folder
        items = os.listdir(base)
        if len(items) == 1 and os.path.isdir(os.path.join(base, items[0])):
            inner = os.path.join(base, items[0])
            for fn in os.listdir(inner):
                shutil.move(os.path.join(inner, fn), os.path.join(base, fn))
            shutil.rmtree(inner, ignore_errors=True)
        return True
    except Exception:
        return False

def restore_processes_after_restart():
    """
    Recreate running processes on boot from state.json.
    If project files are missing, restore from latest backup first.
    """
    st = load_json()
    restored = 0
    for uid, procs in st.get("procs", {}).items():
        for key in list(procs.keys()):
            proj = key.split(":")[0]
            try:
                _ensure_project_files(uid, proj)
                start_script(int(uid), proj, None)
                restored += 1
            except Exception:
                # If start fails, drop the stale entry
                procs.pop(key, None)
    if restored:
        save_json(STATE_FILE, st)
    return restored
