import os, psutil, time
from utils.helpers import load_json

def get_dashboard_data():
    """
    Returns full statistics for the admin dashboard.
    """
    st = load_json()

    users = st.get("users", {})
    procs = st.get("procs", {})

    total_projects = sum(len(u.get("projects", [])) for u in users.values())
    running_scripts = sum(len(v) for v in procs.values())

    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent

    # last backup detection
    backup_time = "No backups yet"
    if os.path.exists("data/backups"):
        zips = [
            os.path.join("data/backups", f)
            for f in os.listdir("data/backups")
            if f.endswith(".zip")
        ]
        if zips:
            zips.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            last = zips[0]
            backup_time = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(os.path.getmtime(last))
            )

    return {
        "total_users": len(users),
        "total_projects": total_projects,
        "running_scripts": running_scripts,
        "cpu": cpu,
        "ram": ram,
        "disk": disk,
        "last_backup": backup_time
    }
