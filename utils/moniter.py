import time, os
from utils.helpers import load_json, save_json, STATE_FILE
from utils.runner import stop_script, start_script

# Free user limits
FREE_PROJECT_LIMIT = 2
FREE_RUNTIME_LIMIT = 12 * 3600  # 12 hours in seconds

# Premium user limits
PREMIUM_PROJECT_LIMIT = 10
PREMIUM_RUNTIME_LIMIT = None  # Unlimited (24/7)

def check_expired():
    state = load_json()
    users = state.get("users", {})
    procs = state.get("procs", {})

    for uid, projects in procs.items():
        uid_str = str(uid)

        # Is user premium?
        is_premium = users.get(uid_str, {}).get("premium", False)

        # Set correct limits
        project_limit = PREMIUM_PROJECT_LIMIT if is_premium else FREE_PROJECT_LIMIT
        runtime_limit = PREMIUM_RUNTIME_LIMIT if is_premium else FREE_RUNTIME_LIMIT

        # Check project count
        user_projects = users.get(uid_str, {}).get("projects", [])
        if len(user_projects) > project_limit:
            extra = user_projects[project_limit:]
            for project in extra:
                stop_script(uid_str, project)

        # Check runtime expiration
        for proj_key, info in list(projects.items()):
            proj = proj_key.split(":")[0]
            start_time = info.get("start", 0)

            if runtime_limit and start_time and (time.time() - start_time > runtime_limit):
                stop_script(uid_str, proj)

    save_json(STATE_FILE, state)


def restore_processes_after_restart():
    state = load_json()
    procs = state.get("procs", {})

    for uid, projects in procs.items():
        for proj_key, info in projects.items():
            proj = proj_key.split(":")[0]
            cmd = info.get("cmd", None)
            try:
                start_script(uid, proj, cmd)
            except:
                pass
