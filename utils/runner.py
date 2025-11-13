import os, subprocess, signal, time

# Active running process dictionary
processes = {}

# Base folder where user projects are stored
LOGS_DIR = "data/users"


# --------------------------------------------------------
#  PATH HELPERS
# --------------------------------------------------------

def _project_dir(uid, proj):
    """Return absolute project folder path."""
    return f"{LOGS_DIR}/{uid}/{proj}"


def pick_entry_py(base):
    """
    Detect the correct entry Python file inside the project folder.
    Priority:
        1) main.py
        2) First .py file
    """
    for root, dirs, files in os.walk(base):
        if "main.py" in files:
            return os.path.join(root, "main.py")

        for f in files:
            if f.endswith(".py"):
                return os.path.join(root, f)

    return None


# --------------------------------------------------------
#  START / STOP / RESTART SCRIPT
# --------------------------------------------------------

def start_script(uid, proj, cmd=None):
    """
    Start a Python project in a subprocess.
    Saves PID and start time in state.json
    """
    base = _project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)

    entry = pick_entry_py(base)
    if not entry and not cmd:
        raise RuntimeError("❌ No Python entry file found!")

    # Default command
    if not cmd:
        cmd = f"python3 {os.path.basename(entry)}"

    # Stop old instance if running
    stop_script(uid, proj)

    # Log file
    log_path = os.path.join(base, "logs.txt")
    logf = open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore")

    # Start subprocess
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=os.path.dirname(entry),
        stdout=logf,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid
    )

    processes[(uid, proj)] = proc

    # Save state
    from utils.helpers import load_json, save_json, STATE_FILE, is_premium
    st = load_json()
    suid = str(uid)

    st.setdefault("procs", {}).setdefault(suid, {})[f"{proj}:entry"] = {
        "pid": proc.pid,
        "start": int(time.time()),
        "cmd": cmd,
        "expire": None if is_premium(uid) else int(time.time()) + (12 * 3600)
    }

    save_json(STATE_FILE, st)
    return proc.pid


def stop_script(uid, proj):
    """Stop a running script using killpg."""
    key = (uid, proj)
    proc = processes.get(key)

    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass

    processes.pop(key, None)


def restart_script(uid, proj, cmd=None):
    """Restart script cleanly."""
    stop_script(uid, proj)
    time.sleep(0.5)
    return start_script(uid, proj, cmd)


# --------------------------------------------------------
#  STATUS + LOG READING
# --------------------------------------------------------

def get_status(uid, proj):
    """
    Return process status, running or not + PID
    """
    key = (uid, proj)
    proc = processes.get(key)

    if not proc:
        return {"running": False, "pid": None}

    running = proc.poll() is None
    return {"running": running, "pid": proc.pid if running else None}


def read_logs(uid, proj, lines=500):
    """
    Return last N lines of logs
    """
    path = os.path.join(_project_dir(uid, proj), "logs.txt")

    if not os.path.exists(path):
        return "No logs yet."

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.readlines()

    return "".join(data[-lines:])
