import os, shutil, time, zipfile

BACKUP_DIR = "data/backups"

def backup_projects():
    """
    Creates backup ZIP of entire /data/ folder.
    Keeps only the latest 3 backups.
    Returns path of generated ZIP file.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    ts = int(time.time())
    out = os.path.join(BACKUP_DIR, f"backup_{ts}.zip")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk("data"):
            for f in files:
                fp = os.path.join(root, f)
                z.write(fp, os.path.relpath(fp, "data"))

    # Keep only latest 3 backups
    files = sorted(
        [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
        key=os.path.getmtime,
        reverse=True
    )

    for old in files[3:]:
        try: os.remove(old)
        except: pass

    return out
