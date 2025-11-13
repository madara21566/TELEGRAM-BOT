import os, subprocess, signal, time

# Stores active running processes in memory
processes = {}

LOGS_DIR = "data/users"


def _project_dir(uid, proj):
    return f"{LOGS_DIR}/{uid}/{proj}"


def pick_entry_py(base):
    """
    Detect correct Python entry file:
    1) Prefer main.py if present
    2) else first .py in directory
    3) else search inside nested folders
    """
    main_path = os.path.join(base, "main.py")
    if os.path.exists(main_path):
        return main_path

    # Check any .py inside main folder
    for f in os.listdir(base):
        if f.endswith(".py"):
            return os.path.join(base, f)

    # Deep search inside ZIP extracted folder
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".py"):
                return os.path.join(root, f)

    return None


def start_script(uid, proj, cmd=None):
    """
    Starts project script safely, writes logs, saves runtime metadata,
    sets expiration rule:
        - Free user = 12 hours
        - Premium user = No expiry
    """
    base = _project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)

    entry = pick_entry_py(base)
    if not entry and not cmd:
        raise RuntimeError("No Python entry file found!")

    # Use folder-relative command for Render/Replit compatibility
    if not cmd:
        cmd = f"python3 {os.path.basename(entry)}"

    # Stop existing process if running
    stop_script(uid, proj)

    # Logger file
    log_path = os.path.join(base, "logs.txt")
    logf = open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore")

    # Start subprocess with correct CWD
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=os.path.dirname(entry),
        stdout=logf,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid
    )

    # Store in memory
    processes[(uid, proj)] = proc

    # Store in persistent JSON
    from utils.helpers import load_json, save_json, STATE_FILE, is_premium
    st = load_json()
    suid = str(uid)

    st.setdefault("procs", {}).setdefault(suid, {})[f"{proj}:entry"] = {
        "pid": proc.pid,
        "start": int(time.time()),
        "cmd": cmd,
        # Expiry: Free = 12h, Premium = None
        "expire": None if is_premium(uid) else int(time.time()) + (12 * 3600)
    }

    save_json(STATE_FILE, st)
    return proc.pid


def stop_script(uid, proj):
    """
    Stops running script safely.
    """
    key = (uid, proj)
    proc = processes.get(key)

    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass

    # Remove from memory but leave JSON state intact (needed for restore)
    processes.pop(key, None)


def restart_script(uid, proj, cmd=None):
    stop_script(uid, proj)
    time.sleep(0.5)
    return start_script(uid, proj, cmd)


def get_status(uid, proj):
    """
    Returns running + PID status
    """
    key = (uid, proj)
    proc = processes.get(key)

    if not proc:
        return {"running": False, "pid": None}

    running = proc.poll() is None
    return {"running": running, "pid": proc.pid if running else None}


def read_logs(uid, proj, lines=500):
    """
    Reads last 500 lines of logs
    """
    path = os.path.join(_project_dir(uid, proj), "logs.txt")
    if not os.path.exists(path):
        return "No logs yet."

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.readlines()

    return "".join(data[-lines:])
