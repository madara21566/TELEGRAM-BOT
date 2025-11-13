import os, subprocess, signal, time

# Stores active running processes in RAM
processes = {}

LOGS_DIR = "data/users"


# ---------------------------------------------------------
#  PATH HELPERS
# ---------------------------------------------------------

def _project_dir(uid, proj):
    """
    Returns full directory path of a user's project.
    Example: data/users/76403/MYAPP
    """
    return f"{LOGS_DIR}/{uid}/{proj}"


def pick_entry_py(base):
    """
    Detects which Python file should be executed.
    Priority:
    1. main.py
    2. Any .py file found

    Returns full path of the entry point.
    """
    # Try main.py first
    for root, dirs, files in os.walk(base):
        if "main.py" in files:
            return os.path.join(root, "main.py")

    # Otherwise pick any .py
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".py"):
                return os.path.join(root, f)

    # None found
    return None


# ---------------------------------------------------------
#  START SCRIPT
# ---------------------------------------------------------

def start_script(uid, proj, cmd=None):
    """
    Starts a Python script inside the project folder.
    Tracks PID, logs, uptime, expiration (12h free).
    """

    base = _project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)

    entry = pick_entry_py(base)

    if not entry and not cmd:
        raise RuntimeError("❌ No Python file found to run!")

    # Build auto command
    if not cmd:
        file_name = os.path.basename(entry)
        cmd = f"python3 {file_name}"

    # Stop if running already
    stop_script(uid, proj)

    # Log path
    log_path = os.path.join(base, "logs.txt")
    logf = open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore")

    # Start the process
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=os.path.dirname(entry),
        stdout=logf,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid
    )

    # Save process in RAM
    processes[(uid, proj)] = proc

    # Save process to DB for restore
    from utils.helpers import load_json, save_json, STATE_FILE, is_premium
    st = load_json()
    suid = str(uid)

    st.setdefault("procs", {}).setdefault(suid, {})[f"{proj}:entry"] = {
        "pid": proc.pid,
        "start": int(time.time()),
        "cmd": cmd,
    }

    # Free user = 12 hour expiry
    if not is_premium(uid):
        st["procs"][suid][f"{proj}:entry"]["expire"] = int(time.time()) + (12 * 3600)
    else:
        st["procs"][suid][f"{proj}:entry"]["expire"] = None  # No expiry

    save_json(STATE_FILE, st)

    return proc.pid


# ---------------------------------------------------------
#  STOP SCRIPT
# ---------------------------------------------------------

def stop_script(uid, proj):
    """
    Stop a running script safely using SIGTERM.
    """
    key = (uid, proj)
    proc = processes.get(key)

    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass  # Already closed

    if key in processes:
        processes.pop(key)


# ---------------------------------------------------------
#  RESTART SCRIPT
# ---------------------------------------------------------

def restart_script(uid, proj, cmd=None):
    stop_script(uid, proj)
    time.sleep(0.4)
    return start_script(uid, proj, cmd)


# ---------------------------------------------------------
#  STATUS / STATS
# ---------------------------------------------------------

def get_status(uid, proj):
    """
    Returns running status & PID.
    """
    key = (uid, proj)
    proc = processes.get(key)

    if not proc:
        return {"running": False, "pid": None}

    running = proc.poll() is None
    return {"running": running, "pid": proc.pid if running else None}


# ---------------------------------------------------------
#  READ LOGS
# ---------------------------------------------------------

def read_logs(uid, proj, lines=500):
    """
    Returns the last X lines of logs.txt
    """
    path = os.path.join(_project_dir(uid, proj), "logs.txt")
    if not os.path.exists(path):
        return "No logs found yet."

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.readlines()

    return "".join(data[-lines:])
