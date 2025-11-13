import time, os, signal
from utils.helpers import load_json, save_json, STATE_FILE
from utils.runner import start_script

def check_expired():
    """
    Stops free user projects after 12 hours.
    Premium projects have expire=None → never stops.
    """
    st = load_json()
    changed = False

    for uid, procs in st.get("procs", {}).items():
        for key, meta in list(procs.items()):
            expire = meta.get("expire")
            if expire and time.time() > expire:
                pid = meta.get("pid")

                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception:
                    pass

                del procs[key]
                changed = True

    if changed:
        save_json(STATE_FILE, st)


def ensure_restart_on_boot():
    """
    Called once on bot start.
    Restarts all premium user projects automatically.
    Free user scripts restart only if they were NOT expired.
    """
    st = load_json()

    for uid, procs in st.get("procs", {}).items():
        for key, meta in list(procs.items()):
            proj = key.split(":")[0]
            expire = meta.get("expire")

            if expire and time.time() > expire:
                continue  # free user period expired

            try:
                start_script(int(uid), proj, meta.get("cmd"))
            except Exception:
                pass
