import time, os, signal
from utils.helpers import load_json, save_json, STATE_FILE

def check_expired():
    st = load_json()
    changed = False
    now = time.time()
    for uid, procs in list(st.get("procs", {}).items()):
        for key, meta in list(procs.items()):
            exp = meta.get("expire")
            if exp and now > exp:
                pid = meta.get("pid")
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception:
                    pass
                del procs[key]
                changed = True
        if uid in st.get("procs", {}) and not st["procs"][uid]:
            del st["procs"][uid]
            changed = True
    if changed:
        save_json(STATE_FILE, st)
