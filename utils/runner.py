import subprocess
import os
import signal
import time

# Dictionary to track running processes
processes = {}

# Folder for logs
LOGS_DIR = "data/users"

# -----------------------------
# 🟢 Start Script
# -----------------------------
def start_script(user_id, project_name, cmd):
    """
    Starts a user's Python project script as a subprocess
    and stores its PID for later control.
    """
    stop_script(user_id, project_name)  # stop old if running

    # Ensure log directory exists
    log_path = f"{LOGS_DIR}/{user_id}/{project_name}/logs.txt"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # Open log file for writing
    log_file = open(log_path, "a", buffering=1)

    # Start process
    process = subprocess.Popen(
        cmd,
        shell=True,
        cwd=f"{LOGS_DIR}/{user_id}/{project_name}",
        stdout=log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid  # allows killing all child processes
    )

    processes[(user_id, project_name)] = process

    print(f"[RUNNER] ✅ Started {project_name} for user {user_id} (PID {process.pid})")
    return process.pid


# -----------------------------
# 🔴 Stop Script
# -----------------------------
def stop_script(user_id, project_name):
    """
    Stops a running process cleanly if active.
    """
    proc = processes.get((user_id, project_name))
    if proc:
        try:
            if proc.poll() is None:  # still running
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                time.sleep(0.5)
                print(f"[RUNNER] ⛔ Stopped {project_name} for user {user_id}")
        except Exception as e:
            print(f"[RUNNER] ⚠️ Stop error for {project_name}: {e}")
        finally:
            processes.pop((user_id, project_name), None)
    else:
        # Fallback: check system for leftover PID (old session)
        pid_file = f"{LOGS_DIR}/{user_id}/{project_name}/pid.txt"
        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                print(f"[RUNNER] Cleaned old PID {pid}")
            except:
                pass
            os.remove(pid_file)


# -----------------------------
# 🔁 Restart Script
# -----------------------------
def restart_script(user_id, project_name, cmd):
    """
    Restarts a user's script: stop then start again.
    """
    print(f"[RUNNER] 🔁 Restarting {project_name} for user {user_id}...")
    stop_script(user_id, project_name)
    time.sleep(1)
    return start_script(user_id, project_name, cmd)


# -----------------------------
# 🧠 Check Script Status
# -----------------------------
def get_status(user_id, project_name):
    """
    Returns dict with process status info.
    """
    proc = processes.get((user_id, project_name))
    if not proc:
        return {
            "running": False,
            "pid": None,
            "status": "Stopped",
        }

    running = proc.poll() is None
    return {
        "running": running,
        "pid": proc.pid if running else None,
        "status": "Running" if running else "Stopped",
    }


# -----------------------------
# 📜 Read Logs
# -----------------------------
def read_logs(user_id, project_name, lines=500):
    """
    Reads the last N lines from logs.txt.
    """
    log_path = f"{LOGS_DIR}/{user_id}/{project_name}/logs.txt"
    if not os.path.exists(log_path):
        return "No logs found."

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.readlines()
    return "".join(content[-lines:])


# -----------------------------
# 💾 Save PID File (optional)
# -----------------------------
def save_pid(user_id, project_name):
    """
    Save current process PID to a file (for recovery).
    """
    proc = processes.get((user_id, project_name))
    if proc:
        pid_file = f"{LOGS_DIR}/{user_id}/{project_name}/pid.txt"
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
        print(f"[RUNNER] 💾 PID saved for {project_name}: {proc.pid}")
