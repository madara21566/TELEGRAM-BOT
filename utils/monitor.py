import time, os, signal
from utils.helpers import load_json, save_json, STATE_FILE
from utils.runner import start_script

def check_expired():
    st = load_json()
    changed = False
    for uid, procs in list(st.get("procs", {}).items()):
        for key, meta in list(procs.items()):
            exp = meta.get("expire")
            if exp and time.time() > exp:
                pid = meta.get("pid")
                try: os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception: pass
                del procs[key]
                changed = True
    if changed: save_json(STATE_FILE, st)

def ensure_restart_on_boot():
    st = load_json()
    for uid, procs in st.get("procs", {}).items():
        for key, meta in procs.items():
            proj = key.split(':')[0]
            exp = meta.get("expire")
            if exp and time.time() > exp: continue
            try: start_script(int(uid), proj, meta.get("cmd"))
            except Exception: pass
