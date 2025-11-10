import time
import os
from datetime import datetime, timezone

from utils.helpers import load_json, save_json, STATE_FILE
from utils.runner import start_script, stop_script, get_status


# Free users: max 12h runtime
FREE_LIMIT_SECONDS = 12 * 60 * 60

# Premium users: unlimited (24/7)
# Just auto-restart if stopped


def check_expired():
    """Stop free-user projects that exceeded allowed runtime."""
    st = load_json()
    procs = st.get("procs", {})

    for uid, projects in procs.items():
        for proj, entry in projects.items():
            start_time = entry.get("start", None)
            if not start_time:
                continue

            user_id = int(uid)
            is_premium = str(user_id) in st.get("premium", [])

            # If premium -> no time limit
            if is_premium:
                continue

            # If free user -> stop if > 12h
            uptime = int(time.time()) - int(start_time)
            if uptime >= FREE_LIMIT_SECONDS:
                stop_script(user_id, proj.split(":")[0])
                print(f"[Auto-Stop] Free user project stopped: {proj} (User {user_id})")

    save_json(STATE_FILE, st)


def restore_processes_after_restart():
    """Restart projects that were running before restart for Premium users."""
    time.sleep(4)  # wait until bot & system fully initialize

    st = load_json()
    procs = st.get("procs", {})

    for uid, projects in procs.items():
        for proj, entry in projects.items():
            user_id = int(uid)
            proj_name = proj.split(":")[0]

            is_premium = str(user_id) in st.get("premium", [])
            status = get_status(user_id, proj_name).get("running", False)

            # If already running, ignore
            if status:
                continue

            # Only restore for premium users
            if is_premium:
                try:
                    start_script(user_id, proj_name)
                    print(f"[Auto-Restore] Restarted project {proj_name} for premium user {user_id}")
                except Exception as e:
                    print(f"[Auto-Restore Error] {proj_name}: {e}")

    save_json(STATE_FILE, st)
