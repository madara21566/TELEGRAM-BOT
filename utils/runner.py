import subprocess, os, signal, time
from utils.helpers import load_json, save_json, STATE_FILE

processes = {}
LOGS_DIR = "data/users"


def _project_dir(uid, proj):
    return f"{LOGS_DIR}/{uid}/{proj}"


def pick_entry_py(base):
    main = os.path.join(base, "main.py")
    if os.path.exists(main):
        return main

    candidates = []
    for name in os.listdir(base):
        if name.endswith(".py"):
            p = os.path.join(base, name)
            try:
                txt = open(p, "r", encoding="utf-8", errors="ignore").read()
            except Exception:
                txt = ""
            score = (1 if "__main__" in txt else 0, os.path.getsize(p))
            candidates.append((score, p))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def start_script(uid, proj, cmd=None):
    base = _project_dir(uid, proj)
    os.makedirs(base, exist_ok=True)
    entry = pick_entry_py(base)
    if not entry and not cmd:
        raise RuntimeError("No entry .py found")

    if not cmd:
        cmd = f"python3 {entry}"

    stop_script(uid, proj)

    log_path = os.path.join(base, "logs.txt")
    logf = open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore")
    proc = subprocess.Popen(cmd, shell=True, cwd=base,
                            stdout=logf, stderr=subprocess.STDOUT,
                            preexec_fn=os.setsid)

    processes[(uid, proj)] = proc

    st = load_json()
    suid = str(uid)
    st.setdefault("procs", {}).setdefault(suid, {})[f"{proj}:entry"] = {
        "pid": proc.pid,
        "start": int(time.time()),
        "cmd": cmd
    }

    # FREE VS PREMIUM RUNTIME LIMIT
    if suid not in st.get("premium_users", []):
        st["procs"][suid][f"{proj}:entry"]["expire"] = int(time.time()) + (12 * 3600)
    else:
        st["procs"][suid][f"{proj}:entry"]["expire"] = None

    # Mark desired run for auto-resume
    st.setdefault("desired_runs", {}).setdefault(suid, [])
    if proj not in st["desired_runs"][suid]:
        st["desired_runs"][suid].append(proj)

    save_json(STATE_FILE, st)
    return proc.pid


def stop_script(uid, proj):
    key = (uid, proj)
    proc = processes.get(key)

    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass

    processes.pop(key, None)

    # Remove from desired auto-resume list
    st = load_json()
    suid = str(uid)
    if proj in st.get("desired_runs", {}).get(suid, []):
        st["desired_runs"][suid].remove(proj)
    save_json(STATE_FILE, st)


def restart_script(uid, proj, cmd=None):
    stop_script(uid, proj)
    time.sleep(0.7)
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
    if not os.path.exists(path):
        return "No logs yet."
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.readlines()
    return "".join(data[-lines:])
