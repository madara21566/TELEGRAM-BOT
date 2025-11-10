import os, subprocess, signal, time
from utils.helpers import load_json, save_json, STATE_FILE, is_premium, running_count

processes = {}
LOGS_DIR = "data/users"

def _project_dir(uid, proj):
    return f"{LOGS_DIR}/{uid}/{proj}"

def pick_entry_py(base):
    for root, dirs, files in os.walk(base):
        if "main.py" in files:
            return os.path.join(root, "main.py")
        for f in files:
            if f.endswith(".py"):
                return os.path.join(root, f)
    return None

def start_script(uid, proj, cmd=None):
    # Enforce running limit also here (free can’t run >2 simultaneously)
    if not is_premium(uid) and running_count(uid) >= 2:
        raise RuntimeError("Free plan running limit reached (max 2). Upgrade for 24/7 & more slots.")

    base = _project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)

    entry = pick_entry_py(base)
    if not entry and not cmd:
        raise RuntimeError("❌ No Python entry file found in project!")

    if not cmd:
        cmd = f"python3 {os.path.basename(entry)}"

    # stop if already running
    stop_script(uid, proj)

    log_path = os.path.join(base, "logs.txt")
    logf = open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore")

    proc = subprocess.Popen(
        cmd, shell=True, cwd=os.path.dirname(entry),
        stdout=logf, stderr=subprocess.STDOUT, preexec_fn=os.setsid
    )
    processes[(uid, proj)] = proc

    st = load_json()
    suid = str(uid)
    st.setdefault("procs", {}).setdefault(suid, {})[f"{proj}:entry"] = {
        "pid": proc.pid,
        "start": int(time.time()),
        "cmd": cmd
    }
    # runtime limit for FREE users (12h), premium unlimited
    if suid not in st.get("premium_users", []):
        st["procs"][suid][f"{proj}:entry"]["expire"] = int(time.time()) + (12 * 3600)
    else:
        st["procs"][suid][f"{proj}:entry"]["expire"] = None

    save_json(STATE_FILE, st)
    return proc.pid

def stop_script(uid, proj):
    key = (uid, proj)
    proc = processes.get(key)
    if proc and proc.poll() is None:
        try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception: pass
    processes.pop(key, None)
    # Also clear from state to not show stale running
    st = load_json()
    suid = str(uid)
    if suid in st.get("procs", {}) and f"{proj}:entry" in st["procs"][suid]:
        del st["procs"][suid][f"{proj}:entry"]
        if not st["procs"][suid]:
            del st["procs"][suid]
        save_json(STATE_FILE, st)

def restart_script(uid, proj, cmd=None):
    stop_script(uid, proj)
    time.sleep(0.5)
    return start_script(uid, proj, cmd)

def get_status(uid, proj):
    key = (uid, proj)
    proc = processes.get(key)
    if not proc:
        return {"running": False, "pid": None}
    running = proc.poll() is None
    return {"running": running, "pid": proc.pid if running else None}

def read_logs(uid, proj, lines=500):
    path = os.path.join(_project_dir(uid, proj), "logs.txt")
    if not os.path.exists(path): return "No logs yet."
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.readlines()
    return "".join(data[-lines:])
