import os, psutil, time
from utils.helpers import load_json

def get_dashboard_data():
    st = load_json()
    users = st.get("users", {})
    procs = st.get("procs", {})
    total_projects = sum(len(u.get("projects", [])) for u in users.values())
    running = sum(len(v) for v in procs.values())
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    last_backup = "N/A"
    if os.path.exists("data/backups"):
        zips = [f for f in os.listdir("data/backups") if f.endswith('.zip')]
        if zips:
            zips.sort(
                key=lambda x: os.path.getmtime(os.path.join("data/backups", x)),
                reverse=True
            )
            last_backup = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(os.path.getmtime(os.path.join("data/backups", zips[0])))
            )
    return {
        "total_users": len(users),
        "total_projects": total_projects,
        "running": running,
        "cpu": cpu,
        "ram": ram,
        "disk": disk,
        "last_backup": last_backup
    }
