import os, shutil, time, zipfile

def backup_projects():
    base = "data/users"
    out_root = "data/backups"
    os.makedirs(out_root, exist_ok=True)
    for uid in os.listdir(base):
        udir = os.path.join(base, uid)
        if not os.path.isdir(udir): continue
        for proj in os.listdir(udir):
            pdir = os.path.join(udir, proj)
            if not os.path.isdir(pdir): continue
            ts = int(time.time())
            outdir = os.path.join(out_root, uid)
            os.makedirs(outdir, exist_ok=True)
            shutil.make_archive(os.path.join(outdir, f"{proj}_{ts}"), "zip", pdir)

    # keep only last 3 per user
    for uid in os.listdir(out_root):
        uout = os.path.join(out_root, uid)
        if not os.path.isdir(uout): continue
        zips = sorted([f for f in os.listdir(uout) if f.endswith(".zip")], reverse=True)
        for old in zips[3:]:
            try: os.remove(os.path.join(uout, old))
            except Exception: pass

def _latest_backup_path(uid, proj):
    uout = os.path.join("data/backups", str(uid))
    if not os.path.isdir(uout): return None
    zips = sorted([f for f in os.listdir(uout) if f.startswith(proj + "_") and f.endswith(".zip")], reverse=True)
    if not zips: return None
    return os.path.join(uout, zips[0])

def restore_latest_if_missing(uid, proj):
    """If data/users/<uid>/<proj> doesn't exist, restore from latest backup zip."""
    base = os.path.join("data/users", str(uid), proj)
    if os.path.isdir(base):
        return False
    os.makedirs(base, exist_ok=True)
    latest = _latest_backup_path(uid, proj)
    if not latest:
        return False
    with zipfile.ZipFile(latest, "r") as z:
        z.extractall(base)
    return True
